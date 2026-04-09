import os
import threading
from datetime import date, timedelta, datetime, timezone

from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, flash, g)
from flask_wtf.csrf import CSRFProtect, CSRFError

import database as db
import mailer

app = Flask(__name__)

# ── Configuração segura ────────────────────────────────────────────────────────
app.secret_key = os.getenv('SECRET_KEY', os.urandom(32))
app.config.update(
    SESSION_COOKIE_HTTPONLY  = True,
    SESSION_COOKIE_SAMESITE  = 'Lax',
    SESSION_COOKIE_SECURE    = os.getenv('FLASK_ENV') == 'production',
    PERMANENT_SESSION_LIFETIME = 28800,   # 8 horas
    WTF_CSRF_TIME_LIMIT      = 3600,
)

csrf = CSRFProtect(app)

db.init_db()


# ── Helpers ────────────────────────────────────────────────────────────────────

def proximos_dias_uteis(n=12):
    dias, d = [], date.today() + timedelta(days=1)
    while len(dias) < n:
        if d.weekday() < 5:
            dias.append(d.strftime('%d/%m/%Y'))
        d += timedelta(days=1)
    return dias


def get_ip():
    return request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()


def enviar_async(fn, *args):
    """Dispara e-mail em thread separada para não bloquear a resposta."""
    threading.Thread(target=fn, args=args, daemon=True).start()


# ── Erros ──────────────────────────────────────────────────────────────────────

@app.errorhandler(CSRFError)
def csrf_error(e):
    flash('Sessão expirada. Tente novamente.', 'error')
    return redirect(request.referrer or url_for('cliente'))


@app.errorhandler(404)
def not_found(e):
    return render_template('erro.html', codigo=404,
                           msg='Página não encontrada.'), 404


@app.errorhandler(500)
def server_error(e):
    return render_template('erro.html', codigo=500,
                           msg='Erro interno. Tente novamente.'), 500


# ── Cliente ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    return redirect(url_for('cliente'))


@app.route('/cliente')
def cliente():
    modulos = db.get_modulos()
    dias    = proximos_dias_uteis()
    return render_template('cliente.html', modulos=modulos, dias=dias)


@app.route('/api/horarios')
def api_horarios():
    data = request.args.get('data', '')
    if not data:
        return jsonify([])
    return jsonify(db.get_horarios_disponiveis(data))


@app.route('/cliente/agendar', methods=['POST'])
def agendar():
    codigo = db.criar_agendamento(request.form)
    ag     = db.get_agendamento_by_codigo(codigo)
    # E-mail ao cliente + notificação interna (assíncronos)
    enviar_async(mailer.email_agendamento_criado, ag)
    enviar_async(mailer.email_novo_agendamento_interno, ag)
    return redirect(url_for('confirmacao', codigo=codigo))


@app.route('/cliente/confirmacao/<codigo>')
def confirmacao(codigo):
    ag = db.get_agendamento_by_codigo(codigo)
    if not ag:
        return redirect(url_for('cliente'))
    return render_template('confirmacao.html', ag=ag)


# ── Funcionário ────────────────────────────────────────────────────────────────

@app.route('/funcionario')
def funcionario():
    if 'func_id' in session:
        return redirect(url_for('func_dashboard'))
    return render_template('funcionario.html', page='login',
                           flash_msg=session.pop('flash', None))


@app.route('/funcionario/login', methods=['POST'])
def func_login():
    ip    = get_ip()
    email = request.form.get('email', '').strip().lower()
    senha = request.form.get('senha', '')

    if db.ip_bloqueado(ip):
        session['flash'] = (f'Muitas tentativas. Aguarde {db.JANELA_MINUTOS} minutos.')
        return redirect(url_for('funcionario'))

    f = db.get_funcionario_by_email(email)
    if f and db.verificar_senha(senha, f['senha']):
        # Migração transparente SHA256 → bcrypt
        if not f['senha'].startswith('$2'):
            db.migrar_senha_para_bcrypt(f['id'], db.hash_senha(senha))
        db.registrar_tentativa(email, ip, sucesso=True)
        session.permanent = True
        session['func_id']    = f['id']
        session['func_nome']  = f['nome']
        session['func_cargo'] = f['cargo']
        return redirect(url_for('func_dashboard'))

    db.registrar_tentativa(email, ip, sucesso=False)
    restantes = db.tentativas_restantes(ip)
    session['flash'] = (f'E-mail ou senha incorretos. '
                        f'Tentativas restantes: {restantes}.')
    return redirect(url_for('funcionario'))


@app.route('/funcionario/dashboard')
def func_dashboard():
    if 'func_id' not in session:
        return redirect(url_for('funcionario'))
    status_f     = request.args.get('status', '')
    hoje         = date.today().strftime('%d/%m/%Y')
    agendamentos = db.get_todos_agendamentos(status=status_f or None)
    return render_template('funcionario.html', page='dashboard',
                           agendamentos=agendamentos, hoje=hoje,
                           status_filter=status_f)


@app.route('/funcionario/atualizar', methods=['POST'])
def func_atualizar():
    if 'func_id' not in session:
        return jsonify({'ok': False}), 401
    codigo = request.form.get('codigo')
    status = request.form.get('status')
    obs    = request.form.get('observacoes', '')
    db.atualizar_status(codigo, status, session['func_id'], obs)
    ag = db.get_agendamento_by_codigo(codigo)
    enviar_async(mailer.email_status_atualizado, ag)
    return jsonify({'ok': True})


@app.route('/funcionario/logout')
def func_logout():
    session.clear()
    return redirect(url_for('funcionario'))


# ── Admin ──────────────────────────────────────────────────────────────────────

def admin_required():
    return 'admin_id' in session


@app.route('/admin')
def admin():
    if admin_required():
        return redirect(url_for('admin_dashboard'))
    return render_template('admin.html', page='login',
                           flash_msg=session.pop('flash', None))


@app.route('/admin/login', methods=['POST'])
def admin_login():
    ip    = get_ip()
    email = request.form.get('email', '').strip().lower()
    senha = request.form.get('senha', '')

    if db.ip_bloqueado(ip):
        session['flash'] = (f'Muitas tentativas. Aguarde {db.JANELA_MINUTOS} minutos.')
        return redirect(url_for('admin'))

    f = db.get_funcionario_by_email(email)
    if f and f['cargo'] == 'Administrador' and db.verificar_senha(senha, f['senha']):
        if not f['senha'].startswith('$2'):
            db.migrar_senha_para_bcrypt(f['id'], db.hash_senha(senha))
        db.registrar_tentativa(email, ip, sucesso=True)
        session.permanent = True
        session['admin_id']   = f['id']
        session['admin_nome'] = f['nome']
        return redirect(url_for('admin_dashboard'))

    db.registrar_tentativa(email, ip, sucesso=False)
    restantes = db.tentativas_restantes(ip)
    session['flash'] = (f'Credenciais inválidas ou sem permissão. '
                        f'Tentativas restantes: {restantes}.')
    return redirect(url_for('admin'))


@app.route('/admin/dashboard')
def admin_dashboard():
    if not admin_required():
        return redirect(url_for('admin'))
    stats   = db.get_stats()
    recentes = db.get_todos_agendamentos()[:10]
    return render_template('admin.html', page='dashboard',
                           stats=stats, recentes=recentes)


@app.route('/admin/agendamentos')
def admin_agendamentos():
    if not admin_required():
        return redirect(url_for('admin'))
    sf = request.args.get('status', '')
    mf = request.args.get('modulo', '')
    df = request.args.get('data',   '')
    agendamentos = db.get_todos_agendamentos(
        status=sf or None, modulo=mf or None, data=df or None)
    modulos = db.get_modulos()
    return render_template('admin.html', page='agendamentos',
                           agendamentos=agendamentos, modulos=modulos,
                           sf=sf, mf=mf, df=df)


@app.route('/admin/atualizar', methods=['POST'])
def admin_atualizar():
    if not admin_required():
        return jsonify({'ok': False}), 401
    codigo = request.form.get('codigo')
    status = request.form.get('status')
    obs    = request.form.get('observacoes', '')
    db.atualizar_status(codigo, status, observacoes=obs)
    ag = db.get_agendamento_by_codigo(codigo)
    enviar_async(mailer.email_status_atualizado, ag)
    return jsonify({'ok': True})


@app.route('/admin/funcionarios')
def admin_funcionarios():
    if not admin_required():
        return redirect(url_for('admin'))
    funcionarios = db.get_todos_funcionarios()
    return render_template('admin.html', page='funcionarios',
                           funcionarios=funcionarios,
                           flash_msg=session.pop('flash', None))


@app.route('/admin/funcionarios/criar', methods=['POST'])
def admin_criar_funcionario():
    if not admin_required():
        return redirect(url_for('admin'))
    ok = db.criar_funcionario(
        request.form['nome'], request.form['email'],
        request.form['senha'], request.form['cargo'])
    if not ok:
        session['flash'] = 'E-mail já cadastrado.'
    return redirect(url_for('admin_funcionarios'))


@app.route('/admin/funcionarios/toggle/<int:id>')
def admin_toggle_funcionario(id):
    if not admin_required():
        return redirect(url_for('admin'))
    db.toggle_funcionario(id)
    return redirect(url_for('admin_funcionarios'))


@app.route('/admin/modulos')
def admin_modulos():
    if not admin_required():
        return redirect(url_for('admin'))
    return render_template('admin.html', page='modulos',
                           modulos=db.get_todos_modulos())


@app.route('/admin/modulos/criar', methods=['POST'])
def admin_criar_modulo():
    if not admin_required():
        return redirect(url_for('admin'))
    db.criar_modulo(request.form['nome'], request.form.get('descricao', ''))
    return redirect(url_for('admin_modulos'))


@app.route('/admin/modulos/toggle/<int:id>')
def admin_toggle_modulo(id):
    if not admin_required():
        return redirect(url_for('admin'))
    db.toggle_modulo(id)
    return redirect(url_for('admin_modulos'))


@app.route('/api/stats')
def api_stats():
    if not admin_required():
        return jsonify({}), 401
    return jsonify(db.get_stats())


@app.route('/admin/logout')
def admin_logout():
    session.clear()
    return redirect(url_for('admin'))


if __name__ == '__main__':
    app.run(debug=True, port=5000)
