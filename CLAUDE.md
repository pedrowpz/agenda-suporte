# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repositório

**GitHub:** https://github.com/pedrowpz/agenda-suporte  
**Regra:** toda alteração no código deve ser commitada e enviada ao GitHub ao final da tarefa.

```bash
git add .
git commit -m "descrição da alteração"
git push
```

## Rodar o sistema

```bash
cd suporte_web
./start.sh          # desenvolvimento (Flask debug)
./start.sh prod     # produção (Gunicorn)
```

Dependências ficam em `suporte_web/.venv/`. Instalar com:
```bash
cd suporte_web && .venv/bin/pip install -r requirements.txt
```

## Arquitetura

```
suporte_web/
├── app.py          ← rotas Flask (cliente / funcionário / admin)
├── database.py     ← PostgreSQL via psycopg2 (todas as queries)
├── mailer.py       ← envio de e-mail SMTP (smtplib)
├── gunicorn.conf.py
├── jettax-suporte.service  ← systemd para produção
├── start.sh
├── static/css/style.css    ← design system Jettax
└── templates/
    ├── cliente.html         ← wizard 4 passos (público)
    ├── confirmacao.html     ← pós-agendamento
    ├── funcionario.html     ← portal do consultor (login + dashboard)
    └── admin.html           ← painel admin (login + dashboard + configurações)
```

**Banco:** PostgreSQL `agendaSuporte` — tabelas `agendamentos`, `funcionarios`, `modulos`, `login_tentativas`.  
Conexão configurada via variáveis de ambiente em `suporte_web/.env` (ver `.env.example`).

**Fluxo de autenticação:** bcrypt para senhas, migração automática de hashes SHA256 legados no login. Rate limiting: 5 tentativas / 15 min por IP na tabela `login_tentativas`. CSRF via Flask-WTF com auto-inject JS em todos os formulários.

**E-mails disparados assincronamente (thread):** agendamento criado → cliente; status alterado → cliente; novo agendamento → equipe interna (`NOTIFY_MAIL`).

## Cores Jettax

```css
--primary: #002670   /* navy */
--accent:  #00AFFA   /* cyan */
--accent-2: #0BE3CC  /* teal */
```
Fontes: `Exo` (títulos) e `Nunito` (corpo) via Google Fonts.

## Credenciais demo

- Admin: `admin@jettax.com.br` / `jettax2024`  
- Consultor: `consultor@jettax.com.br` / `jettax2024`  
- Banco: usuário `jettax` / senha `jettax2024`
