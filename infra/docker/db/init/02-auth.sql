\connect auth_db
SET ROLE auth_user;

CREATE TABLE users (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name                  VARCHAR(100) NOT NULL,
    email                 VARCHAR(255) NOT NULL,
    password_hash         TEXT NOT NULL,
    role                  VARCHAR(10) NOT NULL DEFAULT 'USER'
                          CHECK (role IN ('ADMIN', 'USER')),
    is_active             BOOLEAN NOT NULL DEFAULT TRUE,
    two_fa_enabled        BOOLEAN NOT NULL DEFAULT FALSE,
    totp_secret_encrypted BYTEA,
    totp_last_used_step   BIGINT,
    failed_login_attempts INTEGER NOT NULL DEFAULT 0
                          CHECK (failed_login_attempts >= 0),
    locked_until          TIMESTAMPTZ,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT users_2fa_requires_secret
        CHECK (NOT two_fa_enabled OR totp_secret_encrypted IS NOT NULL)
);

CREATE UNIQUE INDEX users_email_lower_key ON users (lower(email));