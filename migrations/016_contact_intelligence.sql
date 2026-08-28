-- Contact intelligence is an evaluation layer over public_contacts.
-- Keep the discovered public contact as source-of-truth and persist
-- the direct-outreach assessment separately so rules can evolve.

CREATE TABLE public_contact_intelligence (
    id INTEGER PRIMARY KEY,
    public_contact_id INTEGER NOT NULL,
    score REAL NOT NULL,
    label TEXT NOT NULL,
    role_hint TEXT,
    context TEXT,
    source_kind TEXT NOT NULL,
    rule_version TEXT NOT NULL,
    evaluated_at TEXT NOT NULL,
    FOREIGN KEY (public_contact_id)
        REFERENCES public_contacts(id)
        ON DELETE CASCADE,
    UNIQUE (public_contact_id),
    CHECK (
        score >= 0
        AND score <= 100
    )
);

CREATE INDEX idx_public_contact_intelligence_score
    ON public_contact_intelligence(score DESC);

CREATE INDEX idx_public_contact_intelligence_rule
    ON public_contact_intelligence(rule_version);
