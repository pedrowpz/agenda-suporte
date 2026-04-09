-- Criação do banco e usuário para o sistema Jettax Suporte
-- Execute como: sudo -u postgres psql -f setup_db.sql

CREATE DATABASE "agendaSuporte"
    WITH ENCODING 'UTF8'
    LC_COLLATE 'pt_BR.UTF-8'
    LC_CTYPE   'pt_BR.UTF-8'
    TEMPLATE template0;

CREATE USER jettax WITH ENCRYPTED PASSWORD 'jettax2024';

GRANT ALL PRIVILEGES ON DATABASE "agendaSuporte" TO jettax;

\connect "agendaSuporte"
GRANT ALL ON SCHEMA public TO jettax;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES    TO jettax;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO jettax;
