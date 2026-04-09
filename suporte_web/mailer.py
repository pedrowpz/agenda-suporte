"""
Módulo de envio de e-mail — Jettax Suporte
Usa smtplib puro (sem dependências extras).
Configure via variáveis de ambiente (ver .env.example).
Se SMTP_USER não estiver configurado, apenas loga no console.
"""

import smtplib
import os
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

SMTP_HOST   = os.getenv('SMTP_HOST',   'smtp.gmail.com')
SMTP_PORT   = int(os.getenv('SMTP_PORT', '587'))
SMTP_USER   = os.getenv('SMTP_USER',   '')
SMTP_PASS   = os.getenv('SMTP_PASS',   '')
SMTP_FROM   = os.getenv('SMTP_FROM',   'suporte@jettax.com.br')
SMTP_NAME   = os.getenv('SMTP_NAME',   'Jettax Suporte')
NOTIFY_MAIL = os.getenv('NOTIFY_MAIL', '')   # e-mail interno para notificar novos agendamentos


# ── Utilitário de envio ────────────────────────────────────────────────────────

def _enviar(destinatario: str, assunto: str, html: str) -> bool:
    if not SMTP_USER or not SMTP_PASS:
        print(f"[MAIL] (sem SMTP configurado) Para: {destinatario} | Assunto: {assunto}")
        return False
    try:
        msg = MIMEMultipart('alternative')
        msg['Subject'] = assunto
        msg['From']    = f'{SMTP_NAME} <{SMTP_FROM}>'
        msg['To']      = destinatario
        msg.attach(MIMEText(html, 'html', 'utf-8'))
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as srv:
            srv.ehlo()
            srv.starttls()
            srv.login(SMTP_USER, SMTP_PASS)
            srv.sendmail(SMTP_FROM, destinatario, msg.as_string())
        print(f"[MAIL] Enviado → {destinatario} | {assunto}")
        return True
    except Exception as exc:
        print(f"[MAIL] Erro ao enviar para {destinatario}: {exc}")
        return False


# ── Layout base do e-mail ──────────────────────────────────────────────────────

def _base(conteudo: str) -> str:
    return f"""
<!DOCTYPE html>
<html lang="pt-BR">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Jettax Suporte</title>
</head>
<body style="margin:0;padding:0;background:#EEF3FF;font-family:'Helvetica Neue',Arial,sans-serif;">
  <table width="100%" cellpadding="0" cellspacing="0" style="background:#EEF3FF;padding:32px 16px;">
    <tr><td align="center">
      <table width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;">

        <!-- Header -->
        <tr>
          <td style="background:linear-gradient(135deg,#001846,#002670);border-radius:16px 16px 0 0;padding:28px 36px;text-align:left;">
            <span style="font-size:24px;font-weight:800;color:#fff;letter-spacing:-0.5px;">
              Jettax<span style="color:#00AFFA;">.</span>
            </span>
            <span style="display:block;font-size:12px;color:rgba(255,255,255,0.5);margin-top:2px;">
              Suporte Especializado
            </span>
          </td>
        </tr>

        <!-- Conteúdo -->
        <tr>
          <td style="background:#ffffff;padding:36px;border-left:1px solid #D6E4FF;border-right:1px solid #D6E4FF;">
            {conteudo}
          </td>
        </tr>

        <!-- Footer -->
        <tr>
          <td style="background:#F5F8FF;border:1px solid #D6E4FF;border-top:none;border-radius:0 0 16px 16px;padding:20px 36px;text-align:center;">
            <p style="margin:0;font-size:12px;color:#7A7A7A;">
              Este e-mail foi gerado automaticamente pelo sistema de suporte Jettax.<br>
              Em caso de dúvidas, responda este e-mail ou acesse
              <a href="https://jettax.com.br" style="color:#00AFFA;">jettax.com.br</a>.
            </p>
          </td>
        </tr>

      </table>
    </td></tr>
  </table>
</body>
</html>"""


def _info_row(icone: str, label: str, valor: str) -> str:
    return f"""
    <tr>
      <td style="padding:10px 0;border-bottom:1px solid #EEF3FF;">
        <span style="font-size:16px;">{icone}</span>
        <span style="font-size:12px;font-weight:700;text-transform:uppercase;color:#54595F;
                     letter-spacing:0.5px;margin-left:8px;">{label}</span>
        <span style="display:block;font-weight:600;color:#151E33;font-size:15px;
                     margin-top:2px;padding-left:28px;">{valor}</span>
      </td>
    </tr>"""


def _badge(status: str) -> str:
    cores = {
        'Pendente':   ('FFF3CD', '92600A'),
        'Confirmado': ('D1FAE5', '065F46'),
        'Concluído':  ('DBEAFE', '1E3A8A'),
        'Cancelado':  ('FEE2E2', '991B1B'),
    }
    bg, fg = cores.get(status, ('E5E7EB', '374151'))
    return (f'<span style="background:#{bg};color:#{fg};padding:4px 14px;'
            f'border-radius:99px;font-size:12px;font-weight:700;">{status}</span>')


# ── E-mails específicos ────────────────────────────────────────────────────────

def email_agendamento_criado(ag) -> bool:
    """Envia confirmação ao cliente após criar agendamento."""
    corpo = f"""
    <h2 style="margin:0 0 4px;font-size:22px;font-weight:800;color:#002670;">
      Agendamento recebido! ✅
    </h2>
    <p style="margin:0 0 24px;color:#54595F;font-size:15px;">
      Olá, <strong>{ag['cliente_nome']}</strong>! Seu pedido de atendimento foi registrado
      com sucesso. Em breve entraremos em contato para confirmar.
    </p>

    <div style="background:#EEF3FF;border:2px dashed #00AFFA;border-radius:12px;
                padding:16px 20px;text-align:center;margin-bottom:24px;">
      <div style="font-size:12px;font-weight:700;text-transform:uppercase;color:#54595F;
                  letter-spacing:0.5px;">Código do atendimento</div>
      <div style="font-size:36px;font-weight:800;color:#00AFFA;letter-spacing:6px;
                  margin-top:4px;">{ag['codigo']}</div>
      <div style="font-size:12px;color:#7A7A7A;margin-top:4px;">
        Guarde este código para consultas e cancelamentos.
      </div>
    </div>

    <table width="100%" cellpadding="0" cellspacing="0"
           style="border:1px solid #D6E4FF;border-radius:12px;overflow:hidden;margin-bottom:24px;">
      {_info_row('🎯', 'Módulo',   ag['modulo'])}
      {_info_row('📅', 'Data',     ag['data'])}
      {_info_row('🕐', 'Horário',  ag['horario'])}
      {_info_row('🏢', 'Empresa',  ag['cliente_empresa'])}
    </table>

    <p style="margin:0;font-size:14px;color:#54595F;">
      Qualquer dúvida entre em contato com nossa equipe.<br>
      <strong style="color:#002670;">Equipe Jettax Suporte</strong>
    </p>"""
    return _enviar(ag['cliente_email'],
                   f'✅ Agendamento confirmado — Código {ag["codigo"]} | Jettax',
                   _base(corpo))


def email_status_atualizado(ag) -> bool:
    """Envia notificação ao cliente quando o status do agendamento muda."""
    msgs = {
        'Confirmado': ('Atendimento confirmado! 🗓️',
                       'Ótimas notícias! Seu atendimento foi <strong>confirmado</strong> '
                       'pela nossa equipe. Esteja disponível no horário agendado.'),
        'Cancelado':  ('Atendimento cancelado ❌',
                       'Infelizmente seu atendimento foi <strong>cancelado</strong>. '
                       'Se desejar, acesse o sistema para agendar uma nova sessão.'),
        'Concluído':  ('Atendimento concluído 🏁',
                       'Seu atendimento foi <strong>concluído</strong>. '
                       'Esperamos ter ajudado! Não hesite em agendar novamente quando precisar.'),
    }
    if ag['status'] not in msgs:
        return False

    titulo, descricao = msgs[ag['status']]
    obs_bloco = ''
    if ag.get('observacoes'):
        obs_bloco = f"""
        <div style="background:#F5F8FF;border-left:4px solid #00AFFA;border-radius:0 8px 8px 0;
                    padding:12px 16px;margin:16px 0;font-size:14px;color:#151E33;">
          <strong>Observação do consultor:</strong><br>{ag['observacoes']}
        </div>"""

    corpo = f"""
    <h2 style="margin:0 0 4px;font-size:22px;font-weight:800;color:#002670;">{titulo}</h2>
    <p style="margin:0 0 20px;color:#54595F;font-size:15px;">
      Olá, <strong>{ag['cliente_nome']}</strong>! {descricao}
    </p>

    <table width="100%" cellpadding="0" cellspacing="0"
           style="border:1px solid #D6E4FF;border-radius:12px;overflow:hidden;margin-bottom:16px;">
      {_info_row('🔖', 'Código',  ag['codigo'])}
      {_info_row('🎯', 'Módulo',  ag['modulo'])}
      {_info_row('📅', 'Data',    ag['data'])}
      {_info_row('🕐', 'Horário', ag['horario'])}
      {_info_row('📋', 'Status',  ag['status'])}
    </table>
    {obs_bloco}
    <p style="margin:8px 0 0;font-size:14px;color:#54595F;">
      <strong style="color:#002670;">Equipe Jettax Suporte</strong>
    </p>"""
    return _enviar(ag['cliente_email'],
                   f'Atendimento {ag["status"]} — Código {ag["codigo"]} | Jettax',
                   _base(corpo))


def email_novo_agendamento_interno(ag) -> bool:
    """Notifica a equipe interna sobre novo agendamento."""
    if not NOTIFY_MAIL:
        return False
    corpo = f"""
    <h2 style="margin:0 0 4px;font-size:22px;font-weight:800;color:#002670;">
      Novo agendamento recebido 🔔
    </h2>
    <p style="margin:0 0 20px;color:#54595F;">
      Um novo atendimento foi agendado pelo cliente e aguarda confirmação.
    </p>
    <table width="100%" cellpadding="0" cellspacing="0"
           style="border:1px solid #D6E4FF;border-radius:12px;overflow:hidden;margin-bottom:16px;">
      {_info_row('👤', 'Cliente',  f"{ag['cliente_nome']} — {ag['cliente_empresa']}")}
      {_info_row('✉️', 'E-mail',   ag['cliente_email'])}
      {_info_row('🎯', 'Módulo',   ag['modulo'])}
      {_info_row('📅', 'Data',     ag['data'])}
      {_info_row('🕐', 'Horário',  ag['horario'])}
      {_info_row('📝', 'Dúvida',   ag['descricao'])}
    </table>
    <a href="http://localhost:5000/admin/agendamentos"
       style="display:inline-block;background:linear-gradient(135deg,#002670,#001846);
              color:#fff;padding:12px 28px;border-radius:99px;font-weight:700;
              text-decoration:none;font-size:14px;">
      Ver no painel →
    </a>"""
    return _enviar(NOTIFY_MAIL,
                   f'[Jettax] Novo agendamento — {ag["cliente_nome"]} / {ag["modulo"]}',
                   _base(corpo))
