#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v auth_pw="$AUTH_DB_PASSWORD" \
     -v catalog_pw="$CATALOG_DB_PASSWORD" \
     -v reservation_pw="$RESERVATION_DB_PASSWORD" <<'EOSQL'
CREATE ROLE auth_user        LOGIN PASSWORD :'auth_pw';
CREATE ROLE catalog_user     LOGIN PASSWORD :'catalog_pw';
CREATE ROLE reservation_user LOGIN PASSWORD :'reservation_pw';

CREATE DATABASE auth_db        OWNER auth_user;
CREATE DATABASE catalog_db     OWNER catalog_user;
CREATE DATABASE reservation_db OWNER reservation_user;

REVOKE CONNECT ON DATABASE auth_db        FROM PUBLIC;
REVOKE CONNECT ON DATABASE catalog_db     FROM PUBLIC;
REVOKE CONNECT ON DATABASE reservation_db FROM PUBLIC;
EOSQL