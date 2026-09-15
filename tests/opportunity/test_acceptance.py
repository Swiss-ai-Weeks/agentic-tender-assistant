"""End-to-end acceptance: pack import → cited rules → bidder evidence → briefing.

Uses controlled synthetic packs (FR/DE/IT) plus a versioned amendment. Real
SIMAP notices and real bidder evidence are not present in this environment;
those paths stay explicitly unverified (see IMPLEMENTATION_STATUS.md).
"""

import hashlib
import json
from datetime import date
from pathlib import Path

from src.opportunity.bidder import as_evidence, load_bidder_pack
from src.opportunity.compiler import compile_clause
from src.opportunity.corrigendum import recompile_diff
from src.opportunity.documents import compiler_inputs, import_pack
from src.opportunity.engine import decide, evaluate
from src.opportunity.models import Opportunity, Source

AS_OF = date(2026, 9, 15)
DEADLINE = "2027-06-30"

CLAUSES_V1 = {
    "fr.txt": "Le soumissionnaire doit démontrer au moins trois projets comparables "
    "achevés au cours des cinq dernières années.\n",
    "de.txt": "Der Bieter muss eine Haftpflichtversicherung mit einer Deckung von "
    "mindestens CHF 10'000'000 nachweisen.\n",
    "it.txt": "L'offerente deve possedere la certificazione ISO 27001.\n",
}

EVIDENCE_FILES = {
    "references.txt": "3 vergleichbare Projekte, 2021-2025\n",
    "insurance.txt": "Deckung: CHF 10'000'000 Haftpflicht\n",
    "cert.txt": "ISO 27001\n",
}


def _write(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _make_tender_pack(root: Path, clauses: dict[str, str], version: int, reviewed: bool) -> object:
    root.mkdir(parents=True, exist_ok=True)
    for name, text in clauses.items():
        _write(root / name, text)
    return import_pack(
        root,
        "ACME-2026-001",
        tender_version=version,
        source_uri="pack://acceptance/ACME-2026-001",
        complete_set_reviewed=reviewed,
        reviewed_by="acceptance@example.ch",
    )


def _make_bidder_pack(root: Path, rows: list[dict]) -> object:
    root.mkdir(parents=True, exist_ok=True)
    manifest = {
        "company": {"name": "Acme Systems AG"},
        "reviewed_by": "r.acme@example.ch",
        "reviewed_at": "2026-09-10",
        "evidence": rows,
    }
    (root / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return load_bidder_pack(root)


def _bidder_row(
    root: Path, name: str, content: str, field: str, value, unit: str, line: int, quote: str
) -> dict:
    _write(root / name, content)
    return {
        "field": field,
        "value": value,
        "unit": unit,
        "valid_until": "2028-01-01",
        "file": name,
        "line": line,
        "quote": quote,
        "sha256": hashlib.sha256((root / name).read_bytes()).hexdigest(),
    }


def _briefing(requirements, evidence, complete_documents: bool) -> Opportunity:
    checks = [evaluate(req, evidence, AS_OF, DEADLINE) for req in requirements]
    op = Opportunity(
        id="ACME-2026-001",
        title="Acceptance tender",
        buyer="Test buyer",
        location="Bern",
        deadline=DEADLINE,
        summary="Acceptance walkthrough.",
        mode="demo",
        source=Source(
            id="acceptance/pack",
            document="pack",
            quote="acceptance pack",
            url="pack://acceptance",
            trust="VERIFIED_INTERNAL",
        ),
        checks=checks,
        complete_documents=complete_documents,
    )
    return decide(op, AS_OF)


def test_full_chain_go_when_all_mandatory_pass(tmp_path):
    tender = _make_tender_pack(tmp_path / "tender", dict(CLAUSES_V1), 1, True)
    assert tender.complete_documents is True
    assert len(tender.clauses) == 3
    # Every clause carries an exact quote citation back to its source file.
    for clause in tender.clauses:
        assert clause.source.quote == clause.text
        assert clause.source.sha256

    requirements = [
        compile_clause(text, source, ident).to_requirement()
        for ident, text, source in compiler_inputs(tender)
    ]
    by_doc = {req.source.document: req for req in requirements}
    assert by_doc["fr.txt"].compile_status == "VERIFIED"
    assert by_doc["de.txt"].compile_status == "VERIFIED"
    assert by_doc["it.txt"].compile_status == "VERIFIED"

    bidder_root = tmp_path / "bidder"
    bidder_root.mkdir()
    rows = [
        _bidder_row(
            bidder_root,
            "references.txt",
            EVIDENCE_FILES["references.txt"],
            "references",
            3,
            "projects",
            1,
            "3 vergleichbare Projekte, 2021-2025",
        ),
        _bidder_row(
            bidder_root,
            "insurance.txt",
            EVIDENCE_FILES["insurance.txt"],
            "insurance",
            10000000,
            "CHF",
            1,
            "Deckung: CHF 10'000'000 Haftpflicht",
        ),
        _bidder_row(
            bidder_root,
            "cert.txt",
            EVIDENCE_FILES["cert.txt"],
            "certifications",
            ["ISO 27001"],
            "names",
            1,
            "ISO 27001",
        ),
    ]
    bidder = _make_bidder_pack(bidder_root, rows)
    assert bidder.issues == []
    evidence = as_evidence(bidder)

    op = _briefing(requirements, evidence, tender.complete_documents)
    assert [c.status for c in op.checks] == ["PASS", "PASS", "PASS"]
    assert op.recommendation == "GO"
    assert op.blockers == 0


def test_missing_bidder_evidence_stays_unknown_not_no_go(tmp_path):
    tender = _make_tender_pack(tmp_path / "tender", dict(CLAUSES_V1), 1, True)
    requirements = [
        compile_clause(text, source, ident).to_requirement()
        for ident, text, source in compiler_inputs(tender)
    ]
    bidder_root = tmp_path / "bidder"
    bidder_root.mkdir()
    rows = [
        _bidder_row(
            bidder_root,
            "cert.txt",
            EVIDENCE_FILES["cert.txt"],
            "certifications",
            ["ISO 27001"],
            "names",
            1,
            "ISO 27001",
        )
    ]
    evidence = as_evidence(_make_bidder_pack(bidder_root, rows))
    op = _briefing(requirements, evidence, tender.complete_documents)
    # Missing evidence is reported honestly: UNKNOWN checks, no fabricated FAIL.
    by_field = {c.requirement.field: c for c in op.checks}
    assert by_field["insurance"].status == "UNKNOWN"
    assert by_field["references"].status == "UNKNOWN"
    assert by_field["certifications"].status == "PASS"
    assert op.recommendation in ("UNKNOWN", "CONDITIONAL GO")
    assert op.recommendation != "GO"
    assert len(op.blocking_set) == 2


def test_insufficient_evidence_is_no_go_with_citation(tmp_path):
    tender = _make_tender_pack(tmp_path / "tender", dict(CLAUSES_V1), 1, True)
    requirements = [
        compile_clause(text, source, ident).to_requirement()
        for ident, text, source in compiler_inputs(tender)
    ]
    bidder_root = tmp_path / "bidder"
    bidder_root.mkdir()
    rows = [
        _bidder_row(
            bidder_root,
            "references.txt",
            "1 vergleichbares Projekt\n",
            "references",
            1,
            "projects",
            1,
            "1 vergleichbares Projekt",
        ),
        _bidder_row(
            bidder_root,
            "insurance.txt",
            EVIDENCE_FILES["insurance.txt"],
            "insurance",
            10000000,
            "CHF",
            1,
            "Deckung: CHF 10'000'000 Haftpflicht",
        ),
        _bidder_row(
            bidder_root,
            "cert.txt",
            EVIDENCE_FILES["cert.txt"],
            "certifications",
            ["ISO 27001"],
            "names",
            1,
            "ISO 27001",
        ),
    ]
    evidence = as_evidence(_make_bidder_pack(bidder_root, rows))
    op = _briefing(requirements, evidence, tender.complete_documents)
    by_field = {c.requirement.field: c for c in op.checks}
    assert by_field["references"].status == "FAIL"
    assert op.recommendation == "NO-GO"
    assert by_field["references"].evidence is not None
    assert by_field["references"].evidence.source.quote


def test_amendment_recompilation_detects_added_rule(tmp_path):
    v1 = _make_tender_pack(tmp_path / "v1", dict(CLAUSES_V1), 1, True)
    v2_clauses = dict(CLAUSES_V1)
    v2_clauses["amendment.txt"] = (
        "The bidder must demonstrate annual turnover of at least CHF 5,000,000.\n"
    )
    v2 = _make_tender_pack(tmp_path / "v2", v2_clauses, 2, True)
    old = {c.id: c.text for c in v1.clauses}
    # Clause ids restart per import; align by document+text for the diff instead.
    old_by_text = {c.text: c.id for c in v1.clauses}
    aligned_new = {}
    for clause in v2.clauses:
        aligned_new[old_by_text.get(clause.text, f"NEW-{clause.document}")] = clause.text
    source = Source(
        id="acceptance/diff",
        document="diff",
        quote="amendment diff",
        url="pack://acceptance",
        trust="VERIFIED_INTERNAL",
    )
    diff = recompile_diff(old, aligned_new, source)
    assert diff["changed"] is True
    added = [c for c in diff["changes"] if c["kind"] == "ADDED"]
    assert len(added) == 1
    assert "revenue" in added[0]["new"]
    # The added rule compiles and, with no bidder evidence, evaluates UNKNOWN.
    added_req = compile_clause(added[0]["clause"], source, "ACME-R-NEW").to_requirement()
    check = evaluate(added_req, [], AS_OF, DEADLINE)
    assert check.status == "UNKNOWN"


def test_unreviewed_document_set_never_reports_go(tmp_path):
    tender = _make_tender_pack(tmp_path / "tender", dict(CLAUSES_V1), 1, False)
    assert tender.complete_documents is False
    requirements = [
        compile_clause(text, source, ident).to_requirement()
        for ident, text, source in compiler_inputs(tender)
    ]
    bidder_root = tmp_path / "bidder"
    bidder_root.mkdir()
    rows = [
        _bidder_row(
            bidder_root,
            "references.txt",
            EVIDENCE_FILES["references.txt"],
            "references",
            3,
            "projects",
            1,
            "3 vergleichbare Projekte, 2021-2025",
        ),
        _bidder_row(
            bidder_root,
            "insurance.txt",
            EVIDENCE_FILES["insurance.txt"],
            "insurance",
            10000000,
            "CHF",
            1,
            "Deckung: CHF 10'000'000 Haftpflicht",
        ),
        _bidder_row(
            bidder_root,
            "cert.txt",
            EVIDENCE_FILES["cert.txt"],
            "certifications",
            ["ISO 27001"],
            "names",
            1,
            "ISO 27001",
        ),
    ]
    evidence = as_evidence(_make_bidder_pack(bidder_root, rows))
    op = _briefing(requirements, evidence, tender.complete_documents)
    assert all(c.status == "PASS" for c in op.checks)
    assert op.recommendation != "GO"
    assert any("not been verified" in risk for risk in op.risks)
