"""Authoritative Evidence and Provenance Database for Swiss Public Procurement.

Implements the evidence-first data architecture:
PostgreSQL / SQLite relational tables:
- organizations & organization_aliases (entity resolution)
- tenders & tender_versions (immutable versioning)
- documents (raw source preservation)
- requirements (Tender-as-Code IR with clause provenance)
- evidence & organization_facts (facts separate from evidence)
- observations & derived_facts (observations separate from claims)
- awards (SIMAP award evidence)
- qualification_runs & qualification_results (reproducible snapshots)
- candidate_evidence_index (lexical / candidate retrieval index)
"""
import hashlib
import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _db_path() -> Path:
    override = os.getenv("TENDER_DB_PATH", "").strip()
    return Path(override) if override else ROOT / "data" / "evidence_provenance.db"


DB_PATH = _db_path()
SCHEMA_SQL_PATH = ROOT / "data" / "schema.sql"

SCHEMA_SQL = """-- Authoritative Evidence and Provenance Database Schema
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
"""


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path())
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    """Create all relational tables and write schema.sql if not existing."""
    path = _db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    SCHEMA_SQL_PATH.write_text(SCHEMA_SQL)
    with get_connection() as conn:
        conn.executescript(SCHEMA_SQL)
    seed_initial_data()


def seed_initial_data():
    """Seed initial organizations, aliases, competitor awards, and documents."""
    demo_dir = ROOT / "data" / "demo"
    if not (demo_dir / "company.json").exists():
        return

    company_data = json.loads((demo_dir / "company.json").read_text())
    comp_data = json.loads((demo_dir / "competitors" / "registry.json").read_text())

    with get_connection() as conn:
        # 1. Insert Our Company
        conn.execute(
            """INSERT OR IGNORE INTO organizations (id, canonical_name, registry_id, domain, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                "alpine-digital",
                company_data.get("name", "Alpine Digital SA"),
                "CHE-109.845.221",
                "alpine-digital.ch",
                datetime.now(UTC).isoformat(),
            ),
        )
        conn.execute(
            """INSERT OR IGNORE INTO organization_aliases (organization_id, alias, alias_type)
               VALUES (?, ?, ?)""",
            ("alpine-digital", "Alpine Digital", "brand_name"),
        )
        conn.execute(
            """INSERT OR IGNORE INTO organization_aliases (organization_id, alias, alias_type)
               VALUES (?, ?, ?)""",
            ("alpine-digital", "AD Group", "historical_name"),
        )

        # 2. Insert Hewlett Packard Enterprise (HPE)
        conn.execute(
            """INSERT OR IGNORE INTO organizations (id, canonical_name, registry_id, domain, created_at)
               VALUES (?, ?, ?, ?, ?)""",
            (
                "hpe",
                "Hewlett Packard Enterprise Switzerland GmbH",
                "CHE-105.856.321",
                "hpe.com",
                datetime.now(UTC).isoformat(),
            ),
        )
        for alias in ["Hewlett Packard Enterprise", "HPE", "HP Enterprise"]:
            conn.execute(
                """INSERT OR IGNORE INTO organization_aliases (organization_id, alias, alias_type)
                   VALUES (?, ?, ?)""",
                ("hpe", alias, "trading_as"),
            )

        # 3. Insert Competitors from registry.json
        for org in comp_data.get("orgs", []):
            conn.execute(
                """INSERT OR IGNORE INTO organizations (id, canonical_name, registry_id, domain, created_at)
                   VALUES (?, ?, ?, ?, ?)""",
                (
                    org["id"],
                    org["name"],
                    org.get("registry_id"),
                    f"{org['id']}.ch",
                    datetime.now(UTC).isoformat(),
                ),
            )
            for alias in org.get("aliases", []):
                conn.execute(
                    """INSERT OR IGNORE INTO organization_aliases (organization_id, alias, alias_type)
                       VALUES (?, ?, ?)""",
                    (org["id"], alias, "trading_as"),
                )

        # 4. Insert Awards & Observations
        for award in comp_data.get("awards", []):
            award_id = hashlib.sha256(
                f"{award['org']}:{award['title']}:{award['date']}".encode()
            ).hexdigest()[:16]

            # Resolve canonical org id
            cur = conn.execute(
                """SELECT organization_id FROM organization_aliases WHERE lower(alias) = lower(?)
                   UNION SELECT id FROM organizations WHERE lower(canonical_name) = lower(?)""",
                (award["org"], award["org"]),
            )
            row = cur.fetchone()
            org_id = row["organization_id"] if row else "unknown-org"

            conn.execute(
                """INSERT OR IGNORE INTO awards
                   (id, winner_org_id, winner_name_raw, buyer, title, description, award_date, contract_value, currency, source_document, source_quote, source_url)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    award_id,
                    org_id,
                    award["org"],
                    award["buyer"],
                    award["title"],
                    award.get("description", ""),
                    award["date"],
                    award.get("value_chf"),
                    "CHF",
                    award["source"]["document"],
                    award["source"]["quote"],
                    f"/api/sources/competitors/{award['source']['document']}",
                ),
            )

            # Record formal Observation
            obs_id = f"obs-{award_id}"
            conn.execute(
                """INSERT OR IGNORE INTO observations
                   (id, organization_id, observation_type, title, description, buyer, event_date, contract_value, currency, source_document, source_quote, source_url, observed_at, trust_class)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    obs_id,
                    org_id,
                    "simap_award",
                    award["title"],
                    award.get("description", ""),
                    award["buyer"],
                    award["date"],
                    award.get("value_chf"),
                    "CHF",
                    award["source"]["document"],
                    award["source"]["quote"],
                    f"/api/sources/competitors/{award['source']['document']}",
                    datetime.now(UTC).isoformat(),
                    "VERIFIED_PUBLIC",
                ),
            )


def record_qualification_run(run, opportunities):
    """Persist a complete qualification run and its proof results to the database."""
    init_db()
    with get_connection() as conn:
        conn.execute(
            """INSERT OR REPLACE INTO qualification_runs
               (id, mode, status, profile_version, rule_compiler_version, engine_version, started_at, completed_at, elapsed_seconds, total_discovered, total_relevant, total_investigated, total_qualified)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                run.id,
                run.mode,
                run.status,
                run.profile_version,
                run.rule_compiler_version,
                run.engine_version,
                datetime.now(UTC).isoformat(),
                datetime.now(UTC).isoformat(),
                run.elapsed_seconds,
                run.discovered,
                run.relevant,
                run.investigated,
                sum(1 for o in opportunities if o.recommendation == "GO"),
            ),
        )

        for op in opportunities:
            # 1. Tender
            conn.execute(
                """INSERT OR REPLACE INTO tenders
                   (id, external_id, title, buyer, location, summary, deadline, contract_value, value_currency, value_basis, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    op.id,
                    op.id,
                    op.title,
                    op.buyer,
                    op.location,
                    op.summary,
                    op.deadline,
                    op.contract_value,
                    op.value_currency or "CHF",
                    op.value_basis,
                    datetime.now(UTC).isoformat(),
                ),
            )

            # 2. Tender Version
            version_num = op.tender_version or 1
            cur = conn.execute(
                """SELECT id FROM tender_versions WHERE tender_id = ? AND version_number = ?""",
                (op.id, version_num),
            )
            v_row = cur.fetchone()
            if not v_row:
                cur = conn.execute(
                    """INSERT INTO tender_versions
                       (tender_id, version_number, sha256_hash, source_url, raw_payload_path, retrieved_at)
                       VALUES (?, ?, ?, ?, ?, ?)""",
                    (
                        op.id,
                        version_num,
                        op.sha256 or hashlib.sha256(op.title.encode()).hexdigest(),
                        op.source.url,
                        op.source.document,
                        op.retrieved_at or datetime.now(UTC).isoformat(),
                    ),
                )
                tender_version_id = cur.lastrowid
            else:
                tender_version_id = v_row["id"]

            # 3. Requirements, Evidence, Facts, and Results
            for check in op.checks:
                req = check.requirement
                conn.execute(
                    """INSERT OR REPLACE INTO requirements
                       (id, tender_version_id, code, raw_clause, field, operator, expected_value, unit, mandatory, compile_status, compile_reason, window_years, source_document, source_section, source_line, source_url)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        req.id,
                        tender_version_id,
                        req.id,
                        req.raw_clause or req.source.quote,
                        req.field,
                        req.operator,
                        str(req.expected),
                        req.unit,
                        1 if req.mandatory else 0,
                        req.compile_status or "UNSUPPORTED",
                        req.compile_reason,
                        req.window_years,
                        req.source.document,
                        req.source.section,
                        req.source.line,
                        req.source.url,
                    ),
                )

                evidence_id = None
                if check.evidence:
                    ev = check.evidence
                    evidence_id = hashlib.sha256(
                        f"ev:{op.id}:{req.field}:{ev.source.document}:{ev.source.line}".encode()
                    ).hexdigest()[:16]
                    val_json = json.dumps(ev.value)
                    conn.execute(
                        """INSERT OR REPLACE INTO evidence
                           (id, organization_id, field, value_json, unit, valid_from, valid_until, observed_at, trust_class, verification_status, quote, line, page, section, source_url)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            evidence_id,
                            "alpine-digital",
                            ev.field,
                            val_json,
                            ev.unit,
                            ev.valid_from,
                            ev.valid_until,
                            ev.observed_at,
                            ev.trust,
                            "VERIFIED" if check.status == "PASS" else "UNVERIFIED",
                            ev.source.quote,
                            ev.source.line,
                            ev.source.page,
                            ev.source.section,
                            ev.source.url,
                        ),
                    )

                    # Also store organization fact
                    fact_id = f"fact-{evidence_id}"
                    conn.execute(
                        """INSERT OR REPLACE INTO organization_facts
                           (id, organization_id, evidence_id, predicate, value_json, unit, valid_from, valid_until, trust_class, verification_status)
                           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            fact_id,
                            "alpine-digital",
                            evidence_id,
                            ev.field,
                            val_json,
                            ev.unit,
                            ev.valid_from,
                            ev.valid_until,
                            ev.trust,
                            "VERIFIED" if check.status == "PASS" else "UNVERIFIED",
                        ),
                    )

                # Qualification Result
                proof_json = json.dumps([p.model_dump() for p in check.proof])
                conn.execute(
                    """INSERT INTO qualification_results
                       (run_id, tender_id, requirement_id, status, evidence_id, verdict_reason, action_text, proof_chain_json, simulated)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        run.id,
                        op.id,
                        req.id,
                        check.status,
                        evidence_id,
                        check.reason,
                        check.action,
                        proof_json,
                        1 if check.simulated else 0,
                    ),
                )


def get_db_stats() -> dict:
    """Return entity and record counts from the provenance database."""
    init_db()
    with get_connection() as conn:
        tables = [
            "organizations",
            "organization_aliases",
            "tenders",
            "tender_versions",
            "documents",
            "requirements",
            "organization_facts",
            "evidence",
            "observations",
            "derived_facts",
            "awards",
            "qualification_runs",
            "qualification_results",
        ]
        counts = {}
        for table in tables:
            cur = conn.execute(f"SELECT COUNT(*) as c FROM {table}")  # noqa: S608
            counts[table] = cur.fetchone()["c"]
        return {
            "database": "SQLite authoritative provenance store (PostgreSQL-equivalent schema)",
            "schema_file": str(SCHEMA_SQL_PATH.relative_to(ROOT)),
            "tables": counts,
            "total_records": sum(counts.values()),
        }
