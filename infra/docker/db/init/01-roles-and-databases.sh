#!/bin/bash
set -e

psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
     -v auth_pw="$AUTH_DB_PASSWORD" \
     -v booking_pw="$BOOKING_DB_PASSWORD" <<'EOSQL'
CREATE ROLE auth_user        LOGIN PASSWORD :'auth_pw';
CREATE ROLE booking_user     LOGIN PASSWORD :'booking_pw';

CREATE DATABASE auth_db        OWNER auth_user;
CREATE DATABASE booking_db     OWNER booking_user;

REVOKE CONNECT ON DATABASE auth_db        FROM PUBLIC;
REVOKE CONNECT ON DATABASE booking_db     FROM PUBLIC;
EOSQL