import hashlib
import json
import uuid
import os
from datetime import datetime, date, timedelta

import bcrypt
import psycopg2
import psycopg2.extras

# ── Conexão ────────────────────────────────────────────────────────────────────
# Configure via variáveis de ambiente ou edite os defaults abaixo.
DB_CONFIG = {
    'host':     os.getenv('PG_HOST',     'localhost'),
    'port':     int(os.getenv('PG_PORT', '5432')),
    'dbname':   os.getenv('PG_DB',       'agendaSuporte'),
    'user':     os.getenv('PG_USER',     'jettax'),
    'password': os.getenv('PG_PASSWORD', 'jettax2024'),
}

HORARIOS_PADRAO = ['09:00', '10:00', '11:00', '14:00', '15:00', '16:00', '17:00']  # fallback se DB vazio

MODULOS_PADRAO = [
    ('Módulo Serviços',         'Configuração e operação do módulo de serviços'),
    ('Módulo Simples Nacional', 'Apuração e obrigações do Simples Nacional'),
    ('Módulo Prevenção',        'Prevenção e análise de riscos fiscais'),
    ('Módulo Federal',          'Obrigações e apurações federais'),
    ('Módulo Geral',            'Configurações e funcionalidades gerais'),
    ('Módulo Serviços Tomados', 'Escrituração de serviços tomados'),
    ('Automações do ICMS',      'Configuração e automações de ICMS'),
    ('Integrações',             'Integrações com sistemas externos e APIs'),
    ('Módulo Área do Cliente',  'Portal e funcionalidades da área do cliente'),
]


def get_conn():
    conn = psycopg2.connect(**DB_CONFIG)
    conn.autocommit = False
    return conn


def hash_senha(senha: str) -> str:
    """Gera hash bcrypt. Aceita também hashes SHA256 legados (migração automática)."""
    return bcrypt.hashpw(senha.encode(), bcrypt.gensalt()).decode()


def verificar_senha(senha: str, hash_armazenado: str) -> bool:
    """Verifica senha contra hash bcrypt ou SHA256 legado."""
    # Hash bcrypt começa com $2b$ ou $2a$
    if hash_armazenado.startswith('$2'):
        return bcrypt.checkpw(senha.encode(), hash_armazenado.encode())
    # Fallback: SHA256 legado (migração transparente)
    return hashlib.sha256(senha.encode()).hexdigest() == hash_armazenado


def init_db():
    conn = get_conn()
    try:
        with conn.cursor() as c:
            c.execute('''
                CREATE TABLE IF NOT EXISTS agendamentos (
                    id               SERIAL PRIMARY KEY,
                    codigo           TEXT UNIQUE NOT NULL,
                    cliente_nome     TEXT NOT NULL,
                    cliente_email    TEXT NOT NULL,
                    cliente_empresa  TEXT NOT NULL,
                    cliente_telefone TEXT,
                    modulo           TEXT NOT NULL,
                    data             TEXT NOT NULL,
                    horario          TEXT NOT NULL,
                    descricao        TEXT NOT NULL,
                    status           TEXT DEFAULT \'Pendente\',
                    funcionario_id   INTEGER,
                    observacoes      TEXT,
                    criado_em        TEXT NOT NULL,
                    atualizado_em    TEXT
                )
            ''')

            c.execute('''
                CREATE TABLE IF NOT EXISTS funcionarios (
                    id     SERIAL PRIMARY KEY,
                    nome   TEXT NOT NULL,
                    email  TEXT UNIQUE NOT NULL,
                    senha  TEXT NOT NULL,
                    cargo  TEXT DEFAULT \'Consultor\',
                    ativo  BOOLEAN DEFAULT TRUE
                )
            ''')

            c.execute('''
                CREATE TABLE IF NOT EXISTS modulos (
                    id        SERIAL PRIMARY KEY,
                    nome      TEXT NOT NULL,
                    descricao TEXT,
                    ativo     BOOLEAN DEFAULT TRUE
                )
            ''')

            c.execute('''
                CREATE TABLE IF NOT EXISTS login_tentativas (
                    id         SERIAL PRIMARY KEY,
                    email      TEXT NOT NULL,
                    ip         TEXT NOT NULL,
                    sucesso    BOOLEAN DEFAULT FALSE,
                    criado_em  TIMESTAMP DEFAULT NOW()
                )
            ''')

            c.execute('''
                CREATE TABLE IF NOT EXISTS configuracoes (
                    chave TEXT PRIMARY KEY,
                    valor TEXT NOT NULL
                )
            ''')

            c.execute('''
                CREATE TABLE IF NOT EXISTS consultor_modulos (
                    funcionario_id INTEGER NOT NULL REFERENCES funcionarios(id) ON DELETE CASCADE,
                    modulo_id      INTEGER NOT NULL REFERENCES modulos(id)      ON DELETE CASCADE,
                    PRIMARY KEY (funcionario_id, modulo_id)
                )
            ''')

            # Seed configurações padrão
            defaults = {
                'horarios':          json.dumps(['09:00','10:00','11:00','14:00','15:00','16:00','17:00']),
                'dias_semana':       json.dumps([0,1,2,3,4]),
                'dias_antecedencia': '12',
            }
            for chave, valor in defaults.items():
                c.execute('''INSERT INTO configuracoes (chave, valor) VALUES (%s,%s)
                             ON CONFLICT (chave) DO NOTHING''', (chave, valor))

            # Seed módulos
            c.execute('SELECT COUNT(*) FROM modulos')
            if c.fetchone()[0] == 0:
                c.executemany(
                    'INSERT INTO modulos (nome, descricao) VALUES (%s, %s)',
                    MODULOS_PADRAO
                )

            # Seed usuários padrão
            c.execute('SELECT COUNT(*) FROM funcionarios')
            if c.fetchone()[0] == 0:
                c.executemany(
                    'INSERT INTO funcionarios (nome, email, senha, cargo) VALUES (%s, %s, %s, %s)',
                    [
                        ('Administrador',  'admin@jettax.com.br',     hash_senha('jettax2024'), 'Administrador'),
                        ('Consultor Demo', 'consultor@jettax.com.br', hash_senha('jettax2024'), 'Consultor'),
                    ]
                )

        conn.commit()
    finally:
        conn.close()


# ── Módulos ────────────────────────────────────────────────────────────────────

def get_modulos():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute('SELECT * FROM modulos WHERE ativo = TRUE ORDER BY nome')
            return c.fetchall()


def get_todos_modulos():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute('SELECT * FROM modulos ORDER BY nome')
            return c.fetchall()


def criar_modulo(nome: str, descricao: str):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute('INSERT INTO modulos (nome, descricao) VALUES (%s, %s)', (nome, descricao))
        conn.commit()


def toggle_modulo(id: int):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute('UPDATE modulos SET ativo = NOT ativo WHERE id = %s', (id,))
        conn.commit()


# ── Configurações ─────────────────────────────────────────────────────────────

def get_config(chave: str):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute('SELECT valor FROM configuracoes WHERE chave = %s', (chave,))
            row = c.fetchone()
    return row[0] if row else None


def set_config(chave: str, valor: str):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute('''INSERT INTO configuracoes (chave, valor) VALUES (%s, %s)
                         ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor''',
                      (chave, valor))
        conn.commit()


def get_horarios_config() -> list:
    raw = get_config('horarios')
    return json.loads(raw) if raw else HORARIOS_PADRAO


def get_dias_semana_config() -> list:
    """Retorna lista de inteiros: 0=seg, 1=ter, 2=qua, 3=qui, 4=sex, 5=sáb, 6=dom."""
    raw = get_config('dias_semana')
    return json.loads(raw) if raw else [0, 1, 2, 3, 4]


def get_dias_antecedencia_config() -> int:
    raw = get_config('dias_antecedencia')
    return int(raw) if raw else 12


# ── Horários ───────────────────────────────────────────────────────────────────

def get_horarios_disponiveis(data_str: str, modulo_nome: str = None):
    horarios = get_horarios_config()
    with get_conn() as conn:
        with conn.cursor() as c:
            if modulo_nome:
                # Consultores ativos designados para este módulo
                c.execute('''
                    SELECT f.id FROM funcionarios f
                    JOIN consultor_modulos cm ON cm.funcionario_id = f.id
                    JOIN modulos m ON m.id = cm.modulo_id
                    WHERE m.nome = %s AND f.ativo = TRUE
                ''', (modulo_nome,))
                consultor_ids = [r[0] for r in c.fetchall()]

                if not consultor_ids:
                    # Sem consultores atribuídos: fallback genérico
                    c.execute(
                        "SELECT horario FROM agendamentos WHERE data = %s AND status != 'Cancelado'",
                        (data_str,)
                    )
                    ocupados = {r[0] for r in c.fetchall()}
                    return [h for h in horarios if h not in ocupados]

                # Horário disponível se pelo menos 1 consultor do módulo estiver livre
                horarios_disponiveis = []
                for h in horarios:
                    c.execute(
                        '''SELECT COUNT(DISTINCT funcionario_id) FROM agendamentos
                           WHERE data = %s AND horario = %s AND status != \'Cancelado\'
                           AND funcionario_id = ANY(%s)''',
                        (data_str, h, consultor_ids)
                    )
                    ocupados = c.fetchone()[0]
                    if ocupados < len(consultor_ids):
                        horarios_disponiveis.append(h)
                return horarios_disponiveis
            else:
                c.execute(
                    "SELECT horario FROM agendamentos WHERE data = %s AND status != 'Cancelado'",
                    (data_str,)
                )
                ocupados = {r[0] for r in c.fetchall()}
                return [h for h in horarios if h not in ocupados]


# ── Agendamentos ───────────────────────────────────────────────────────────────

def get_consultor_disponivel(modulo_nome: str, data_str: str, horario: str):
    """Retorna o id do consultor disponível (menos ocupado no dia) para o módulo/horário."""
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute('''
                SELECT f.id FROM funcionarios f
                JOIN consultor_modulos cm ON cm.funcionario_id = f.id
                JOIN modulos m ON m.id = cm.modulo_id
                WHERE m.nome = %s AND f.ativo = TRUE
            ''', (modulo_nome,))
            consultor_ids = [r[0] for r in c.fetchall()]

            if not consultor_ids:
                return None

            # Consultores já ocupados neste slot
            c.execute(
                '''SELECT DISTINCT funcionario_id FROM agendamentos
                   WHERE data = %s AND horario = %s AND status != \'Cancelado\'
                   AND funcionario_id = ANY(%s)''',
                (data_str, horario, consultor_ids)
            )
            ocupados_ids = {r[0] for r in c.fetchall() if r[0] is not None}
            livres = [cid for cid in consultor_ids if cid not in ocupados_ids]

            if not livres:
                return None

            # Balanceamento: consultor com menos agendamentos no dia
            c.execute(
                '''SELECT funcionario_id, COUNT(*) FROM agendamentos
                   WHERE data = %s AND status != \'Cancelado\'
                   AND funcionario_id = ANY(%s)
                   GROUP BY funcionario_id''',
                (data_str, livres)
            )
            carga = {r[0]: r[1] for r in c.fetchall()}
            return min(livres, key=lambda cid: carga.get(cid, 0))


def criar_agendamento(dados) -> str:
    codigo  = str(uuid.uuid4())[:8].upper()
    agora   = datetime.now().strftime('%d/%m/%Y %H:%M')
    modulo  = dados.get('modulo', '')
    data    = dados.get('data', '')
    horario = dados.get('horario', '')

    # Auto-atribuição de consultor disponível
    func_id = get_consultor_disponivel(modulo, data, horario)

    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                '''INSERT INTO agendamentos
                   (codigo, cliente_nome, cliente_email, cliente_empresa, cliente_telefone,
                    modulo, data, horario, descricao, criado_em, funcionario_id)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                (codigo,
                 dados['nome'], dados['email'], dados['empresa'], dados.get('telefone', ''),
                 modulo, data, horario, dados['descricao'], agora, func_id)
            )
        conn.commit()
    return codigo


def get_agendamento_by_codigo(codigo: str):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute('SELECT * FROM agendamentos WHERE codigo = %s', (codigo,))
            return c.fetchone()


def get_todos_agendamentos(status=None, modulo=None, data=None):
    query  = '''SELECT a.*, f.nome AS funcionario_nome
                FROM agendamentos a
                LEFT JOIN funcionarios f ON a.funcionario_id = f.id
                WHERE 1=1'''
    params = []
    if status:
        query  += ' AND a.status = %s';  params.append(status)
    if modulo:
        query  += ' AND a.modulo = %s';  params.append(modulo)
    if data:
        query  += ' AND a.data = %s';    params.append(data)
    query += ' ORDER BY a.data ASC, a.horario ASC'

    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(query, params)
            return c.fetchall()


def atualizar_status(codigo: str, status: str,
                     funcionario_id=None, observacoes=None):
    agora = datetime.now().strftime('%d/%m/%Y %H:%M')
    with get_conn() as conn:
        with conn.cursor() as c:
            if funcionario_id:
                c.execute(
                    'UPDATE agendamentos SET status=%s, funcionario_id=%s, observacoes=%s, atualizado_em=%s WHERE codigo=%s',
                    (status, funcionario_id, observacoes, agora, codigo)
                )
            else:
                c.execute(
                    'UPDATE agendamentos SET status=%s, observacoes=%s, atualizado_em=%s WHERE codigo=%s',
                    (status, observacoes, agora, codigo)
                )
        conn.commit()


# ── Funcionários ───────────────────────────────────────────────────────────────

def get_funcionario_by_email(email: str):
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(
                'SELECT * FROM funcionarios WHERE email = %s AND ativo = TRUE', (email,)
            )
            return c.fetchone()


def migrar_senha_para_bcrypt(funcionario_id: int, nova_senha_hash: str):
    """Substitui hash SHA256 legado por bcrypt após login bem-sucedido."""
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute('UPDATE funcionarios SET senha = %s WHERE id = %s',
                      (nova_senha_hash, funcionario_id))
        conn.commit()


# ── Rate limiting de login ─────────────────────────────────────────────────────

MAX_TENTATIVAS = 5      # tentativas falhas permitidas
JANELA_MINUTOS = 15     # janela de tempo


def registrar_tentativa(email: str, ip: str, sucesso: bool):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                'INSERT INTO login_tentativas (email, ip, sucesso) VALUES (%s, %s, %s)',
                (email, ip, sucesso)
            )
        conn.commit()


def ip_bloqueado(ip: str) -> bool:
    """Retorna True se o IP tiver >= MAX_TENTATIVAS falhas nos últimos JANELA_MINUTOS."""
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                '''SELECT COUNT(*) FROM login_tentativas
                   WHERE ip = %s AND sucesso = FALSE
                   AND criado_em > NOW() - INTERVAL '%s minutes' ''',
                (ip, JANELA_MINUTOS)
            )
            return c.fetchone()[0] >= MAX_TENTATIVAS


def tentativas_restantes(ip: str) -> int:
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                '''SELECT COUNT(*) FROM login_tentativas
                   WHERE ip = %s AND sucesso = FALSE
                   AND criado_em > NOW() - INTERVAL '%s minutes' ''',
                (ip, JANELA_MINUTOS)
            )
            usadas = c.fetchone()[0]
    return max(0, MAX_TENTATIVAS - usadas)


def get_todos_funcionarios():
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute('SELECT id, nome, email, cargo, ativo FROM funcionarios ORDER BY nome')
            return c.fetchall()


def criar_funcionario(nome: str, email: str, senha: str, cargo: str) -> bool:
    with get_conn() as conn:
        try:
            with conn.cursor() as c:
                c.execute(
                    'INSERT INTO funcionarios (nome, email, senha, cargo) VALUES (%s, %s, %s, %s)',
                    (nome, email, hash_senha(senha), cargo)
                )
            conn.commit()
            return True
        except psycopg2.errors.UniqueViolation:
            conn.rollback()
            return False


def toggle_funcionario(id: int):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute('UPDATE funcionarios SET ativo = NOT ativo WHERE id = %s', (id,))
        conn.commit()


# ── Consultor ↔ Módulos ────────────────────────────────────────────────────────

def get_modulos_consultor(funcionario_id: int):
    """Retorna lista de módulos (id, nome) atribuídos a um consultor."""
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute('''
                SELECT m.id, m.nome FROM modulos m
                JOIN consultor_modulos cm ON cm.modulo_id = m.id
                WHERE cm.funcionario_id = %s ORDER BY m.nome
            ''', (funcionario_id,))
            return c.fetchall()


def set_modulos_consultor(funcionario_id: int, modulo_ids: list):
    """Substitui todos os módulos atribuídos ao consultor."""
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute('DELETE FROM consultor_modulos WHERE funcionario_id = %s', (funcionario_id,))
            if modulo_ids:
                c.executemany(
                    'INSERT INTO consultor_modulos (funcionario_id, modulo_id) VALUES (%s, %s)',
                    [(funcionario_id, mid) for mid in modulo_ids]
                )
        conn.commit()


# ── Stats ──────────────────────────────────────────────────────────────────────

def get_stats() -> dict:
    with get_conn() as conn:
        # cursor simples para queries escalares (fetchone()[0])
        with conn.cursor() as cs:
            def scalar(q, p=()):
                cs.execute(q, p)
                return cs.fetchone()[0]

            total       = scalar('SELECT COUNT(*) FROM agendamentos')
            pendentes   = scalar("SELECT COUNT(*) FROM agendamentos WHERE status='Pendente'")
            confirmados = scalar("SELECT COUNT(*) FROM agendamentos WHERE status='Confirmado'")
            concluidos  = scalar("SELECT COUNT(*) FROM agendamentos WHERE status='Concluído'")
            cancelados  = scalar("SELECT COUNT(*) FROM agendamentos WHERE status='Cancelado'")

        # cursor dict para queries com múltiplas colunas
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as c:
            c.execute(
                "SELECT modulo, COUNT(*) AS total FROM agendamentos WHERE status != 'Cancelado' "
                "GROUP BY modulo ORDER BY total DESC LIMIT 8"
            )
            por_modulo = [dict(r) for r in c.fetchall()]

            c.execute("SELECT status, COUNT(*) AS total FROM agendamentos GROUP BY status")
            por_status = [dict(r) for r in c.fetchall()]

        with conn.cursor() as cs:
            def scalar(q, p=()):
                cs.execute(q, p)
                return cs.fetchone()[0]

            ultimos_7 = []
            for i in range(6, -1, -1):
                d = (date.today() - timedelta(days=i)).strftime('%d/%m/%Y')
                n = scalar("SELECT COUNT(*) FROM agendamentos WHERE criado_em LIKE %s", (d + '%',))
                ultimos_7.append({'data': d[-5:], 'total': n})   # DD/MM

    return {
        'total':       total,
        'pendentes':   pendentes,
        'confirmados': confirmados,
        'concluidos':  concluidos,
        'cancelados':  cancelados,
        'por_modulo':  por_modulo,
        'por_status':  por_status,
        'ultimos_7':   ultimos_7,
    }
