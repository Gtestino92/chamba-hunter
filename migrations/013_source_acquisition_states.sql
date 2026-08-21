CREATE TABLE source_acquisition_states (
    source_type TEXT NOT NULL,
    scope_key TEXT NOT NULL,

    last_successful_started_at TEXT NOT NULL,
    last_successful_finished_at TEXT NOT NULL,

    last_backfill_finished_at TEXT,

    metadata_json TEXT NOT NULL,

    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,

    PRIMARY KEY (
        source_type,
        scope_key
    )
);

CREATE INDEX idx_source_acquisition_states_finished
    ON source_acquisition_states (
        source_type,
        last_successful_finished_at
    );
