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

def proximos_dias_uteis(n=None):
    dias_semana = db.get_dias_semana_config()
    n = n or db.get_dias_antecedencia_config()
    dias, d = [], date.today() + timedelta(days=1)
    while len(dias) < n:
        if d.weekday() in dias_semana:
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


# ── Login unificado (consultor + admin) ───────────────────────────────────────

@app.route('/login', methods=['GET', 'POST'])
def login():
    # Redireciona quem já está logado
    if 'admin_id' in session:
        return redirect(url_for('admin_dashboard'))
    if 'func_id' in session:
        return redirect(url_for('func_dashboard'))

    if request.method == 'GET':
        return render_template('login.html',
                               flash_msg=session.pop('flash', None),
                               email_anterior=session.pop('email_anterior', None))

    ip    = get_ip()
    email = request.form.get('email', '').strip().lower()
    senha = request.form.get('senha', '')

    if db.ip_bloqueado(ip):
        session['flash'] = f'Muitas tentativas. Aguarde {db.JANELA_MINUTOS} minutos.'
        return redirect(url_for('login'))

    f = db.get_funcionario_by_email(email)
    if f and db.verificar_senha(senha, f['senha']):
        # Migração transparente SHA256 → bcrypt
        if not f['senha'].startswith('$2'):
            db.migrar_senha_para_bcrypt(f['id'], db.hash_senha(senha))
        db.registrar_tentativa(email, ip, sucesso=True)
        session.permanent = True

        if f['cargo'] == 'Administrador':
            session['admin_id']   = f['id']
            session['admin_nome'] = f['nome']
            return redirect(url_for('admin_dashboard'))
        else:
            session['func_id']    = f['id']
            session['func_nome']  = f['nome']
            session['func_cargo'] = f['cargo']
            return redirect(url_for('func_dashboard'))

    db.registrar_tentativa(email, ip, sucesso=False)
    restantes = db.tentativas_restantes(ip)
    session['flash']          = f'E-mail ou senha incorretos. Tentativas restantes: {restantes}.'
    session['email_anterior'] = email
    return redirect(url_for('login'))


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


# Rotas legadas — mantém compatibilidade com links antigos
@app.route('/funcionario')
def funcionario():
    if 'func_id' in session:
        return redirect(url_for('func_dashboard'))
    return redirect(url_for('login'))


@app.route('/admin')
def admin():
    if 'admin_id' in session:
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('login'))


# ── Funcionário ────────────────────────────────────────────────────────────────

@app.route('/funcionario/dashboard')
def func_dashboard():
    if 'func_id' not in session:
        return redirect(url_for('login'))
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


# ── Admin ──────────────────────────────────────────────────────────────────────

def admin_required():
    return 'admin_id' in session


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


@app.route('/admin/disponibilidade', methods=['GET', 'POST'])
def admin_disponibilidade():
    if not admin_required():
        return redirect(url_for('admin'))

    if request.method == 'POST':
        # Horários: checkboxes com name="horario" value="09:00" etc.
        horarios_sel = request.form.getlist('horario')
        # Novo horário avulso
        novo_h = request.form.get('novo_horario', '').strip()
        if novo_h and novo_h not in horarios_sel:
            horarios_sel.append(novo_h)
        horarios_sel = sorted(set(horarios_sel))

        # Dias da semana: checkboxes com name="dia" value="0"…"6"
        dias_sel = [int(d) for d in request.form.getlist('dia')]

        # Antecedência
        antecedencia = int(request.form.get('antecedencia', 12))

        import json as _json
        db.set_config('horarios',          _json.dumps(horarios_sel))
        db.set_config('dias_semana',       _json.dumps(dias_sel))
        db.set_config('dias_antecedencia', str(antecedencia))

        session['flash_disp'] = 'Configurações salvas com sucesso!'
        return redirect(url_for('admin_disponibilidade'))

    import json as _json
    horarios_ativos   = db.get_horarios_config()
    dias_ativos       = db.get_dias_semana_config()
    antecedencia      = db.get_dias_antecedencia_config()
    flash_disp        = session.pop('flash_disp', None)

    # Todos os slots possíveis (08:00 – 19:00 de hora em hora)
    todos_horarios = [f'{h:02d}:00' for h in range(8, 20)]

    return render_template('admin.html', page='disponibilidade',
                           horarios_ativos=horarios_ativos,
                           todos_horarios=todos_horarios,
                           dias_ativos=dias_ativos,
                           antecedencia=antecedencia,
                           flash_disp=flash_disp)


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
