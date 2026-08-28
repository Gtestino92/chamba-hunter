CREATE TABLE IF NOT EXISTS company_aliases (
    alias_company_id INTEGER PRIMARY KEY,
    canonical_company_id INTEGER NOT NULL,
    reason TEXT,
    created_at TEXT NOT NULL,
    FOREIGN KEY (alias_company_id)
        REFERENCES companies(id)
        ON DELETE CASCADE,
    FOREIGN KEY (canonical_company_id)
        REFERENCES companies(id)
        ON DELETE CASCADE,
    CHECK (alias_company_id != canonical_company_id)
);

CREATE INDEX IF NOT EXISTS idx_company_aliases_canonical
    ON company_aliases(canonical_company_id);
