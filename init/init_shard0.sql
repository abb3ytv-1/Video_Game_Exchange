-- =============================================================================
-- Shard 0 Initialization Script
-- Produces EVEN IDs: 2, 4, 6, 8 ...
-- Routing invariant: id % 2 == 0  =>  shard 0
--
-- Tables are created WITHOUT foreign-key constraints.
-- Cross-shard FK enforcement is handled at the application layer.
-- SQLModel's create_all() will skip these tables (they already exist) and
-- will therefore never back-fill FK constraints.
-- =============================================================================

CREATE TABLE IF NOT EXISTS "user" (
    id   BIGSERIAL PRIMARY KEY,
    name VARCHAR   NOT NULL,
    email    VARCHAR   NOT NULL,
    password VARCHAR   NOT NULL,
    address  VARCHAR   NOT NULL
);

CREATE TABLE IF NOT EXISTS game (
    id       BIGSERIAL PRIMARY KEY,
    title    VARCHAR   NOT NULL,
    platform VARCHAR   NOT NULL,
    owner_id BIGINT    NOT NULL
);

CREATE TABLE IF NOT EXISTS tradeoffer (
    id                 BIGSERIAL PRIMARY KEY,
    offered_game_id    BIGINT    NOT NULL,
    requested_game_id  BIGINT    NOT NULL,
    requester_id       BIGINT    NOT NULL,
    status             VARCHAR   NOT NULL DEFAULT 'pending'
);

CREATE INDEX IF NOT EXISTS ix_tradeoffer_status ON tradeoffer (status);

-- ---- Sequence setup: shard 0 generates even IDs (2, 4, 6, ...) ----
-- INCREMENT BY 2 ensures every subsequent value stays even.
-- setval(..., 2, false) means the NEXT call to nextval() returns 2.
ALTER SEQUENCE user_id_seq      INCREMENT BY 2;
SELECT setval('user_id_seq',      2, false);

ALTER SEQUENCE game_id_seq      INCREMENT BY 2;
SELECT setval('game_id_seq',      2, false);

ALTER SEQUENCE tradeoffer_id_seq INCREMENT BY 2;
SELECT setval('tradeoffer_id_seq', 2, false);
