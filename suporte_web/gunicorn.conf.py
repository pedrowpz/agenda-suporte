# Configuração Gunicorn — Jettax Suporte
# Uso: gunicorn -c gunicorn.conf.py app:app

import multiprocessing

bind             = "0.0.0.0:5000"
workers          = multiprocessing.cpu_count() * 2 + 1
worker_class     = "sync"
timeout          = 120
keepalive        = 5
max_requests     = 1000
max_requests_jitter = 100

# Logs
accesslog  = "-"          # stdout
errorlog   = "-"          # stderr
loglevel   = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)sµs'

# Process
proc_name  = "jettax-suporte"
daemon     = False          # systemd cuida do processo
preload_app = True          # carrega app antes de forkar workers
