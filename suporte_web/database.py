import hashlib
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

HORARIOS_PADRAO = ['09:00', '10:00', '11:00', '14:00', '15:00', '16:00', '17:00']

MODULOS_PADRAO = [
    ('Fiscal / NF-e',               'Emissão, transmissão e correção de notas fiscais'),
    ('Financeiro',                   'Contas a pagar, receber e fluxo de caixa'),
    ('Estoque / WMS',               'Controle de estoque e movimentações'),
    ('Compras',                      'Pedidos de compra e fornecedores'),
    ('Vendas / Pedidos',            'Pedidos de venda e faturamento'),
    ('RH / Folha de Pagamento',     'Folha de pagamento e gestão de pessoas'),
    ('Contabilidade',               'Lançamentos e fechamento contábil'),
    ('Relatórios / BI',             'Dashboards e relatórios gerenciais'),
    ('Configurações',               'Parametrização e configurações do sistema'),
    ('Integração / API',            'Integrações com sistemas externos'),
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


# ── Horários ───────────────────────────────────────────────────────────────────

def get_horarios_disponiveis(data_str: str):
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                "SELECT horario FROM agendamentos WHERE data = %s AND status != 'Cancelado'",
                (data_str,)
            )
            ocupados = {r[0] for r in c.fetchall()}
    return [h for h in HORARIOS_PADRAO if h not in ocupados]


# ── Agendamentos ───────────────────────────────────────────────────────────────

def criar_agendamento(dados) -> str:
    codigo = str(uuid.uuid4())[:8].upper()
    agora  = datetime.now().strftime('%d/%m/%Y %H:%M')
    with get_conn() as conn:
        with conn.cursor() as c:
            c.execute(
                '''INSERT INTO agendamentos
                   (codigo, cliente_nome, cliente_email, cliente_empresa, cliente_telefone,
                    modulo, data, horario, descricao, criado_em)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)''',
                (codigo,
                 dados['nome'], dados['email'], dados['empresa'], dados.get('telefone', ''),
                 dados['modulo'], dados['data'], dados['horario'], dados['descricao'], agora)
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
