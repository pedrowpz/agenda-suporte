#!/bin/bash
# Script de inicialização — Jettax Suporte
# Uso: ./start.sh [dev|prod]
# Padrão: dev

set -e
cd "$(dirname "$0")"

# Carrega variáveis de ambiente se existir .env
if [ -f .env ]; then
  export $(grep -v '^#' .env | xargs)
fi

MODE="${1:-dev}"

if [ "$MODE" = "prod" ]; then
  echo "[Jettax] Iniciando em modo PRODUÇÃO (Gunicorn)..."
  export FLASK_ENV=production
  .venv/bin/gunicorn -c gunicorn.conf.py app:app
else
  echo "[Jettax] Iniciando em modo DESENVOLVIMENTO (Flask debug)..."
  export FLASK_ENV=development
  PGPASSWORD="${PG_PASSWORD:-jettax2024}" .venv/bin/python3 app.py
fi
