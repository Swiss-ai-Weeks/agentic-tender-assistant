-- Authoritative Evidence and Provenance Database Schema
-- Compatible with PostgreSQL and SQLite

CREATE TABLE IF NOT EXISTS organizations (
    id TEXT PRIMARY KEY,
    canonical_name TEXT NOT NULL,
    registry_id TEXT,
    domain TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS organization_aliases (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    alias TEXT NOT NULL,
    alias_type TEXT DEFAULT 'trading_as',
    UNIQUE(organization_id, alias)
);

CREATE TABLE IF NOT EXISTS tenders (
    id TEXT PRIMARY KEY,
    external_id TEXT,
    title TEXT NOT NULL,
    buyer TEXT NOT NULL,
    location TEXT,
    summary TEXT,
    deadline TEXT,
    contract_value REAL,
    value_currency TEXT DEFAULT 'CHF',
    value_basis TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS tender_versions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tender_id TEXT NOT NULL REFERENCES tenders(id),
    version_number INTEGER NOT NULL,
    sha256_hash TEXT NOT NULL,
    source_url TEXT,
    raw_payload_path TEXT,
    retrieved_at TEXT NOT NULL,
    UNIQUE(tender_id, version_number)
);

CREATE TABLE IF NOT EXISTS documents (
    id TEXT PRIMARY KEY,
    tender_version_id INTEGER REFERENCES tender_versions(id),
    organization_id TEXT REFERENCES organizations(id),
    document_name TEXT NOT NULL,
    document_type TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    sha256_hash TEXT NOT NULL,
    page_count INTEGER,
    retrieved_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS requirements (
    id TEXT PRIMARY KEY,
    tender_version_id INTEGER REFERENCES tender_versions(id),
    code TEXT NOT NULL,
    raw_clause TEXT NOT NULL,
    field TEXT NOT NULL,
    operator TEXT NOT NULL,
    expected_value TEXT NOT NULL,
    unit TEXT DEFAULT '',
    mandatory BOOLEAN NOT NULL DEFAULT 1,
    compile_status TEXT NOT NULL,
    compile_reason TEXT,
    window_years INTEGER,
    source_document TEXT,
    source_section TEXT,
    source_line INTEGER,
    source_url TEXT
);

CREATE TABLE IF NOT EXISTS evidence (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    document_id TEXT REFERENCES documents(id),
    field TEXT NOT NULL,
    value_json TEXT NOT NULL,
    unit TEXT DEFAULT '',
    valid_from TEXT,
    valid_until TEXT NOT NULL,
    observed_at TEXT,
    trust_class TEXT NOT NULL,
    verification_status TEXT NOT NULL,
    quote TEXT NOT NULL,
    line INTEGER,
    page INTEGER,
    section TEXT,
    source_url TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS organization_facts (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    evidence_id TEXT REFERENCES evidence(id),
    predicate TEXT NOT NULL,
    value_json TEXT NOT NULL,
    unit TEXT DEFAULT '',
    valid_from TEXT,
    valid_until TEXT NOT NULL,
    trust_class TEXT NOT NULL,
    verification_status TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS observations (
    id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    observation_type TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    buyer TEXT,
    event_date TEXT,
    contract_value REAL,
    currency TEXT DEFAULT 'CHF',
    cpv_code TEXT,
    source_document TEXT,
    source_quote TEXT,
    source_url TEXT,
    observed_at TEXT NOT NULL,
    trust_class TEXT NOT NULL DEFAULT 'VERIFIED_PUBLIC'
);

CREATE TABLE IF NOT EXISTS derived_facts (
    id TEXT PRIMARY KEY,
    observation_id TEXT NOT NULL REFERENCES observations(id),
    organization_id TEXT NOT NULL REFERENCES organizations(id),
    requirement_id TEXT REFERENCES requirements(id),
    predicate TEXT NOT NULL,
    claim_summary TEXT NOT NULL,
    comparability_rationale TEXT,
    confidence REAL DEFAULT 1.0,
    trust_class TEXT NOT NULL DEFAULT 'INFERRED',
    is_supported BOOLEAN NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS awards (
    id TEXT PRIMARY KEY,
    winner_org_id TEXT NOT NULL REFERENCES organizations(id),
    winner_name_raw TEXT NOT NULL,
    buyer TEXT NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    award_date TEXT NOT NULL,
    contract_value REAL,
    currency TEXT DEFAULT 'CHF',
    cpv_code TEXT,
    number_of_bids INTEGER,
    source_document TEXT,
    source_quote TEXT,
    source_url TEXT
);

CREATE TABLE IF NOT EXISTS qualification_runs (
    id TEXT PRIMARY KEY,
    mode TEXT NOT NULL,
    status TEXT NOT NULL,
    profile_version TEXT,
    rule_compiler_version TEXT,
    engine_version TEXT,
    started_at TEXT NOT NULL,
    completed_at TEXT,
    elapsed_seconds REAL DEFAULT 0.0,
    total_discovered INTEGER DEFAULT 0,
    total_relevant INTEGER DEFAULT 0,
    total_investigated INTEGER DEFAULT 0,
    total_qualified INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS qualification_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES qualification_runs(id),
    tender_id TEXT NOT NULL REFERENCES tenders(id),
    requirement_id TEXT NOT NULL REFERENCES requirements(id),
    status TEXT NOT NULL,
    evidence_id TEXT REFERENCES evidence(id),
    derived_fact_id TEXT REFERENCES derived_facts(id),
    verdict_reason TEXT NOT NULL,
    action_text TEXT,
    proof_chain_json TEXT,
    simulated BOOLEAN DEFAULT 0
);

CREATE TABLE IF NOT EXISTS candidate_evidence_index (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    organization_id TEXT REFERENCES organizations(id),
    document_id TEXT REFERENCES documents(id),
    content_snippet TEXT NOT NULL,
    tags_json TEXT,
    embedding_vector TEXT
);
