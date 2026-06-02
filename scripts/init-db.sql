-- APEX database init (run as postgres superuser)
-- Creates/resets user apex (password: apex) and database apexdb

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'apex') THEN
        CREATE ROLE apex WITH LOGIN PASSWORD 'apex' CREATEDB;
    ELSE
        ALTER ROLE apex WITH LOGIN PASSWORD 'apex' CREATEDB;
    END IF;
END
$$;

SELECT 'CREATE DATABASE apexdb OWNER apex'
WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'apexdb')\gexec

GRANT ALL PRIVILEGES ON DATABASE apexdb TO apex;

\connect apexdb
GRANT ALL ON SCHEMA public TO apex;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO apex;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO apex;
