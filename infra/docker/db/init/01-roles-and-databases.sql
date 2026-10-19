-- Cria os usuários e os bancos de cada microserviço.
-- As senhas vêm das variáveis de ambiente do contentor (definidas no .env).
-- \getenv é um comando do psql (versão 15+): copia uma variável de ambiente
-- para uma variável do psql, sem precisar de bash nem de permissão de execução.
\getenv auth_pw AUTH_DB_PASSWORD
\getenv booking_pw BOOKING_DB_PASSWORD

CREATE ROLE auth_user    LOGIN PASSWORD :'auth_pw';
CREATE ROLE booking_user LOGIN PASSWORD :'booking_pw';

CREATE DATABASE auth_db    OWNER auth_user;
CREATE DATABASE booking_db OWNER booking_user;

-- Isolamento: só o dono de cada banco consegue conectar
REVOKE CONNECT ON DATABASE auth_db    FROM PUBLIC;
REVOKE CONNECT ON DATABASE booking_db FROM PUBLIC;