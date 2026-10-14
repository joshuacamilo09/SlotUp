\connect reservation_db
SET ROLE reservation_user;
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE TABLE reservations (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id      UUID NOT NULL,
    resource_id  UUID NOT NULL,
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
    resource_id      UUID NOT NULL,
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