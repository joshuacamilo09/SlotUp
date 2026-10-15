\connect booking_db
SET ROLE booking_user;
CREATE EXTENSION IF NOT EXISTS btree_gist;

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

CREATE TABLE reservations (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL,
    user_email   VARCHAR(255) NOT NULL,
    resource_id  UUID NOT NULL REFERENCES resources(id),
    start_at     TIMESTAMPTZ NOT NULL,
    end_at       TIMESTAMPTZ NOT NULL,
    status       VARCHAR(10) NOT NULL DEFAULT 'CONFIRMED'
                 CHECK (status IN ('HELD', 'CONFIRMED', 'CANCELLED')),
    hold_expires_at TIMESTAMPTZ,
    version      INTEGER NOT NULL DEFAULT 1,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    cancelled_at TIMESTAMPTZ,
    CONSTRAINT reservations_held_has_deadline
        CHECK (status <> 'HELD' OR hold_expires_at IS NOT NULL),
    CONSTRAINT reservations_valid_interval CHECK (end_at > start_at),
    CONSTRAINT reservations_cancelled_has_date
        CHECK ((status = 'CANCELLED') = (cancelled_at IS NOT NULL)),
    CONSTRAINT reservations_no_overlap
        EXCLUDE USING gist (
            resource_id WITH =,
            tstzrange(start_at, end_at) WITH &&
        ) WHERE (status IN ('HELD', 'CONFIRMED'))
);

CREATE INDEX reservations_user_idx ON reservations (user_id, start_at);
CREATE INDEX reservations_hold_expiry_idx ON reservations (hold_expires_at)
    WHERE status = 'HELD';

CREATE TABLE waitlist_entries (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id          UUID NOT NULL,
    user_email       VARCHAR(255) NOT NULL,
    resource_id      UUID NOT NULL REFERENCES resources(id),
    desired_start    TIMESTAMPTZ NOT NULL,
    desired_end      TIMESTAMPTZ NOT NULL,
    status           VARCHAR(10) NOT NULL DEFAULT 'WAITING'
                     CHECK (status IN ('WAITING','OFFERED','ACCEPTED','EXPIRED','CANCELLED')),
    reservation_id   UUID REFERENCES reservations(id),
    version          INTEGER NOT NULL DEFAULT 1,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT waitlist_valid_interval CHECK (desired_end > desired_start),
    CONSTRAINT waitlist_offer_has_reservation
        CHECK (status NOT IN ('OFFERED', 'ACCEPTED') OR reservation_id IS NOT NULL)
);

CREATE INDEX waitlist_queue_idx ON waitlist_entries (resource_id, created_at)
    WHERE status = 'WAITING';
CREATE UNIQUE INDEX waitlist_one_active_per_slot
    ON waitlist_entries (user_id, resource_id, desired_start, desired_end)
    WHERE status IN ('WAITING','OFFERED');

CREATE TABLE notifications (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id                 UUID NOT NULL,
    recipient_email         VARCHAR(255) NOT NULL,
    type                    VARCHAR(30) NOT NULL
                            CHECK (type IN ('RESERVATION_CREATED', 'RESERVATION_CANCELLED',
                                            'WAITLIST_JOINED', 'WAITLIST_OFFERED')),
    reservation_id          UUID REFERENCES reservations(id),
    waitlist_entry_id       UUID REFERENCES waitlist_entries(id),
    payload                 JSONB NOT NULL DEFAULT '{}'::jsonb,
    status                  VARCHAR(10) NOT NULL DEFAULT 'PENDING'
                            CHECK (status IN ('PENDING', 'SENT', 'FAILED')),
    attempts                INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    last_error              TEXT,
    next_attempt_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    sent_at                 TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT notifications_has_reference
        CHECK (reservation_id IS NOT NULL OR waitlist_entry_id IS NOT NULL),
    CONSTRAINT notifications_sent_has_date
        CHECK ((status = 'SENT') = (sent_at IS NOT NULL))
);

CREATE INDEX notifications_pending_idx ON notifications (next_attempt_at)
    WHERE status = 'PENDING';

CREATE UNIQUE INDEX notifications_once_per_reservation
    ON notifications (type, reservation_id)
    WHERE waitlist_entry_id IS NULL;

CREATE UNIQUE INDEX notifications_once_per_waitlist_entry
    ON notifications (type, waitlist_entry_id)
    WHERE waitlist_entry_id IS NOT NULL;

INSERT INTO categories (name, description) VALUES
  ('Coworking', 'Mesas e salas de reunião'),
  ('Estacionamento', 'Vagas de estacionamento'),
  ('Desporto', 'Ginásio com personal trainer e quadra de padel')
ON CONFLICT (name) DO NOTHING;