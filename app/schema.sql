-- Civic Compass canonical schema
-- Design rule: no fact row exists without a source_record. Enforced by NOT NULL + FK,
-- not by application convention. See docs/03-data-model.md.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS source_record (
    id              TEXT PRIMARY KEY,
    organization    TEXT NOT NULL,
    source_url      TEXT NOT NULL,
    source_type     TEXT NOT NULL,
    trust_tier      INTEGER NOT NULL CHECK (trust_tier BETWEEN 1 AND 4),
    jurisdiction_id TEXT,
    election_id     TEXT,
    retrieved_at    TEXT NOT NULL,
    published_at    TEXT,
    last_verified_at TEXT NOT NULL,
    effective_date  TEXT,
    content_hash    TEXT,
    claimed_status  TEXT NOT NULL DEFAULT 'official',
    notes           TEXT,
    CHECK (length(source_url) > 8)
);

CREATE TABLE IF NOT EXISTS jurisdiction (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL CHECK (type IN
                      ('federal','state','county','municipality','school','judicial','special')),
    parent_id       TEXT REFERENCES jurisdiction(id),
    state_code      TEXT,
    ocd_id          TEXT,
    boundary_version TEXT,
    timezone        TEXT NOT NULL DEFAULT 'America/Chicago',
    office_name     TEXT NOT NULL,
    official_url    TEXT NOT NULL,
    office_phone    TEXT,
    office_email    TEXT,
    office_address  TEXT,
    source_record_id TEXT NOT NULL REFERENCES source_record(id)
);

-- Rough postal-code to jurisdiction mapping used only to *start* a lookup.
-- Deliberately treated as low confidence: a ZIP is not a jurisdiction.
CREATE TABLE IF NOT EXISTS postal_hint (
    postal_code     TEXT NOT NULL,
    jurisdiction_id TEXT NOT NULL REFERENCES jurisdiction(id),
    confidence      TEXT NOT NULL CHECK (confidence IN ('exact','likely','ambiguous')),
    PRIMARY KEY (postal_code, jurisdiction_id)
);

CREATE TABLE IF NOT EXISTS district (
    id              TEXT PRIMARY KEY,
    jurisdiction_id TEXT NOT NULL REFERENCES jurisdiction(id),
    type            TEXT NOT NULL,
    name            TEXT NOT NULL,
    number          TEXT,
    boundary_version TEXT,
    source_record_id TEXT NOT NULL REFERENCES source_record(id)
);

CREATE TABLE IF NOT EXISTS election (
    id              TEXT PRIMARY KEY,
    name            TEXT NOT NULL,
    type            TEXT NOT NULL CHECK (type IN
                      ('general','primary','special','runoff','recall','municipal',
                       'school','judicial','measure_only')),
    election_date   TEXT NOT NULL,
    timezone        TEXT NOT NULL,
    jurisdiction_id TEXT NOT NULL REFERENCES jurisdiction(id),
    cycle           TEXT,
    is_demo         INTEGER NOT NULL DEFAULT 1,
    status          TEXT NOT NULL DEFAULT 'official',
    source_record_id TEXT NOT NULL REFERENCES source_record(id)
);

CREATE TABLE IF NOT EXISTS election_jurisdiction (
    election_id     TEXT NOT NULL REFERENCES election(id),
    jurisdiction_id TEXT NOT NULL REFERENCES jurisdiction(id),
    relevance_note  TEXT NOT NULL,
    PRIMARY KEY (election_id, jurisdiction_id)
);

CREATE TABLE IF NOT EXISTS deadline (
    id              TEXT PRIMARY KEY,
    election_id     TEXT NOT NULL REFERENCES election(id),
    jurisdiction_id TEXT NOT NULL REFERENCES jurisdiction(id),
    action          TEXT NOT NULL CHECK (action IN
                      ('register','request_ballot','early_vote_start','early_vote_end',
                       'return_postmark','return_receipt','cure','election_day')),
    occurs_at_utc   TEXT NOT NULL,
    timezone        TEXT NOT NULL,
    is_all_day      INTEGER NOT NULL DEFAULT 0,
    methods         TEXT NOT NULL DEFAULT 'all',
    scope_note      TEXT,
    exception_text  TEXT,
    source_record_id TEXT NOT NULL REFERENCES source_record(id)
);

CREATE TABLE IF NOT EXISTS voting_location (
    id              TEXT PRIMARY KEY,
    election_id     TEXT NOT NULL REFERENCES election(id),
    jurisdiction_id TEXT NOT NULL REFERENCES jurisdiction(id),
    type            TEXT NOT NULL CHECK (type IN ('election_day','early','drop_box','office')),
    name            TEXT NOT NULL,
    address_line    TEXT NOT NULL,
    city            TEXT NOT NULL,
    state_code      TEXT NOT NULL,
    postal_code     TEXT,
    hours_text      TEXT,
    date_range_text TEXT,
    accessibility_text TEXT,
    languages_text  TEXT,
    transit_text    TEXT,
    source_record_id TEXT NOT NULL REFERENCES source_record(id)
);

CREATE TABLE IF NOT EXISTS rule (
    id              TEXT PRIMARY KEY,
    jurisdiction_id TEXT NOT NULL REFERENCES jurisdiction(id),
    category        TEXT NOT NULL CHECK (category IN
                      ('eligibility','id','registration','party','mail','provisional',
                       'assistance','language','uocava')),
    title           TEXT NOT NULL,
    body_text       TEXT NOT NULL,
    effective_date  TEXT,
    source_record_id TEXT NOT NULL REFERENCES source_record(id)
);

CREATE TABLE IF NOT EXISTS contest (
    id              TEXT PRIMARY KEY,
    election_id     TEXT NOT NULL REFERENCES election(id),
    jurisdiction_id TEXT NOT NULL REFERENCES jurisdiction(id),
    district_id     TEXT REFERENCES district(id),
    level           TEXT NOT NULL CHECK (level IN
                      ('federal','state','judicial','county','municipal','education',
                       'special','measure')),
    office_name     TEXT NOT NULL,
    seats           INTEGER NOT NULL DEFAULT 1,
    term_text       TEXT,
    classification  TEXT NOT NULL CHECK (classification IN
                      ('partisan','nonpartisan','retention','measure','unspecified')),
    order_rule      TEXT NOT NULL DEFAULT 'alphabetical'
                      CHECK (order_rule IN ('alphabetical','official_ballot')),
    coverage        TEXT NOT NULL DEFAULT 'official'
                      CHECK (coverage IN ('official','verified','aggregated','partial','pending','none')),
    coverage_note   TEXT,
    why_relevant    TEXT NOT NULL,
    source_record_id TEXT NOT NULL REFERENCES source_record(id)
);

-- No rank / score / featured / promoted / weight column exists here by design.
-- See docs/08 check N3; tests/test_neutral_ordering.py asserts this.
CREATE TABLE IF NOT EXISTS candidate (
    id              TEXT PRIMARY KEY,
    contest_id      TEXT NOT NULL REFERENCES contest(id),
    ballot_name     TEXT NOT NULL,
    sort_key        TEXT NOT NULL,
    ballot_position INTEGER,
    filing_status   TEXT NOT NULL CHECK (filing_status IN
                      ('filed','qualified','withdrawn','disqualified','write_in')),
    party_label_official TEXT,
    incumbent_source TEXT,
    website_url     TEXT,
    filing_url      TEXT,
    bio_text        TEXT,
    bio_provided_by TEXT,
    source_record_id TEXT NOT NULL REFERENCES source_record(id)
);

CREATE TABLE IF NOT EXISTS questionnaire_item (
    id              TEXT PRIMARY KEY,
    contest_id      TEXT NOT NULL REFERENCES contest(id),
    position        INTEGER NOT NULL,
    prompt          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS questionnaire_response (
    id              TEXT PRIMARY KEY,
    candidate_id    TEXT NOT NULL REFERENCES candidate(id),
    item_id         TEXT NOT NULL REFERENCES questionnaire_item(id),
    response_text   TEXT NOT NULL,
    responded_at    TEXT NOT NULL,
    source_record_id TEXT NOT NULL REFERENCES source_record(id),
    UNIQUE (candidate_id, item_id)
);

CREATE TABLE IF NOT EXISTS measure (
    id              TEXT PRIMARY KEY,
    contest_id      TEXT NOT NULL REFERENCES contest(id),
    official_title  TEXT NOT NULL,
    ballot_text     TEXT NOT NULL,
    measure_type    TEXT,
    summary_text    TEXT,
    summary_author  TEXT,
    fiscal_note     TEXT,
    full_text_url   TEXT,
    source_record_id TEXT NOT NULL REFERENCES source_record(id)
);

CREATE TABLE IF NOT EXISTS measure_argument (
    id              TEXT PRIMARY KEY,
    measure_id      TEXT NOT NULL REFERENCES measure(id),
    stance          TEXT NOT NULL CHECK (stance IN ('for','against')),
    body_text       TEXT NOT NULL,
    submitted_by    TEXT NOT NULL,
    source_record_id TEXT NOT NULL REFERENCES source_record(id)
);

CREATE TABLE IF NOT EXISTS result (
    id              TEXT PRIMARY KEY,
    contest_id      TEXT NOT NULL REFERENCES contest(id),
    candidate_id    TEXT REFERENCES candidate(id),
    option_label    TEXT,
    votes           INTEGER NOT NULL,
    precincts_reporting INTEGER,
    precincts_total INTEGER,
    reporting_status TEXT NOT NULL CHECK (reporting_status IN
                      ('unofficial','canvassing','recount','certified','amended')),
    certifying_authority TEXT,
    certified_at    TEXT,
    reported_at     TEXT NOT NULL,
    source_record_id TEXT NOT NULL REFERENCES source_record(id)
);

CREATE TABLE IF NOT EXISTS record_version (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_table    TEXT NOT NULL,
    entity_id       TEXT NOT NULL,
    supersedes_id   INTEGER,
    changed_at      TEXT NOT NULL,
    changed_by      TEXT NOT NULL,
    change_reason   TEXT NOT NULL,
    source_record_id TEXT REFERENCES source_record(id),
    previous_value_json TEXT,
    new_value_json  TEXT
);

CREATE TABLE IF NOT EXISTS audit_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    at              TEXT NOT NULL,
    actor           TEXT NOT NULL,
    action          TEXT NOT NULL,
    entity_table    TEXT,
    entity_id       TEXT,
    source_record_id TEXT,
    note            TEXT
);

CREATE TABLE IF NOT EXISTS correction_report (
    id              TEXT PRIMARY KEY,
    submitted_at    TEXT NOT NULL,
    entity_table    TEXT,
    entity_id       TEXT,
    issue_type      TEXT NOT NULL,
    body_text       TEXT NOT NULL,
    contact_optional TEXT,
    moderation_status TEXT NOT NULL DEFAULT 'new'
                      CHECK (moderation_status IN ('new','triage','confirmed','rejected','fixed')),
    resolution_note TEXT,
    resolved_at     TEXT
);

-- Opaque, expiring, identity-free. No address column exists.
CREATE TABLE IF NOT EXISTS saved_plan (
    token           TEXT PRIMARY KEY,
    created_at      TEXT NOT NULL,
    expires_at      TEXT NOT NULL,
    jurisdiction_id TEXT NOT NULL REFERENCES jurisdiction(id),
    election_id     TEXT NOT NULL REFERENCES election(id),
    method_pref     TEXT,
    checklist_state_json TEXT
);

CREATE TABLE IF NOT EXISTS source_health (
    source_record_id TEXT PRIMARY KEY REFERENCES source_record(id),
    last_check_at   TEXT NOT NULL,
    last_success_at TEXT,
    consecutive_failures INTEGER NOT NULL DEFAULT 0,
    note            TEXT
);

CREATE TABLE IF NOT EXISTS coverage_cell (
    jurisdiction_id TEXT NOT NULL REFERENCES jurisdiction(id),
    data_class      TEXT NOT NULL,
    level           TEXT NOT NULL CHECK (level IN
                      ('official','verified','aggregated','partial','pending','none')),
    note            TEXT,
    PRIMARY KEY (jurisdiction_id, data_class)
);

CREATE INDEX IF NOT EXISTS idx_contest_election ON contest(election_id);
CREATE INDEX IF NOT EXISTS idx_candidate_contest ON candidate(contest_id);
CREATE INDEX IF NOT EXISTS idx_deadline_election ON deadline(election_id);
CREATE INDEX IF NOT EXISTS idx_location_election ON voting_location(election_id);
CREATE INDEX IF NOT EXISTS idx_ej_jurisdiction ON election_jurisdiction(jurisdiction_id);
