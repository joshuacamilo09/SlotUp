\connect catalog_db
SET ROLE catalog_user;

CREATE TABLE categories (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name        VARCHAR(100) NOT NULL UNIQUE,
    description TEXT,
    is_active   BOOLEAN NOT NULL DEFAULT TRUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE resources (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    category_id   UUID NOT NULL REFERENCES categories(id),
    name          VARCHAR(150) NOT NULL,
    resource_type VARCHAR(30) NOT NULL,
    description   TEXT,
    capacity      INTEGER NOT NULL DEFAULT 1 CHECK (capacity > 0),
    attributes    JSONB NOT NULL DEFAULT '{}'::jsonb,
    is_active     BOOLEAN NOT NULL DEFAULT TRUE,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (category_id, name)
);

CREATE TABLE availability_rules (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    resource_id UUID NOT NULL REFERENCES resources(id) ON DELETE CASCADE,
    weekday     SMALLINT NOT NULL CHECK (weekday BETWEEN 0 AND 6),
    open_time   TIME NOT NULL,
    close_time  TIME NOT NULL,
    CHECK (close_time > open_time),
    UNIQUE (resource_id, weekday, open_time)
);

CREATE INDEX resources_category_idx ON resources (category_id);

INSERT INTO categories (name, description) VALUES
  ('Coworking', 'Mesas e salas de reunião'),
  ('Estacionamento', 'Vagas de estacionamento'),
  ('Desporto', 'Ginásio com personal trainer e quadra de padel')
ON CONFLICT (name) DO NOTHING;