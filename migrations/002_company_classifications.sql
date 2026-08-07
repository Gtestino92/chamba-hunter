CREATE TABLE company_classifications (
    id INTEGER PRIMARY KEY,

    company_id INTEGER NOT NULL,

    company_type TEXT NOT NULL,
    confidence REAL NOT NULL,

    method TEXT NOT NULL,
    source_url TEXT,

    evidence_json TEXT,

    created_at TEXT NOT NULL,

    FOREIGN KEY (company_id)
        REFERENCES companies(id)
        ON DELETE CASCADE
);

CREATE INDEX idx_company_classifications_company_id
    ON company_classifications(company_id);

CREATE INDEX idx_company_classifications_company_type
    ON company_classifications(company_type);