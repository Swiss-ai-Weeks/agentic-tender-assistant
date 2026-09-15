"""Tests for the explicit bidder evidence-pack loader.

Missing, unreviewed, or mismatched evidence stays in review (UNKNOWN
downstream) — it is never fabricated into a PASS and never borrowed from the
synthetic demo fixtures.
"""

import hashlib
import json
from pathlib import Path

import pytest

from src.opportunity.bidder import as_evidence, load_bidder_pack


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _write_pack(
    pack: Path,
    rows: list[dict],
    company="Muster AG",
    reviewed_by="r.muster@example.ch",
    reviewed_at="2026-09-15",
) -> Path:
    pack.mkdir(parents=True, exist_ok=True)
    manifest = {
        "company": {"name": company},
        "reviewed_by": reviewed_by,
        "reviewed_at": reviewed_at,
        "evidence": rows,
    }
    (pack / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    return pack


def _text_row(
    pack: Path,
    name: str,
    content: str,
    field="insurance",
    value=5000000,
    unit="CHF",
    line=1,
    valid_until="2027-06-30",
    quote=None,
) -> dict:
    (pack / name).write_text(content, encoding="utf-8")
    digest = _sha((pack / name).read_bytes())
    lines = content.splitlines()
    return {
        "field": field,
        "value": value,
        "unit": unit,
        "valid_until": valid_until,
        "file": name,
        "line": line,
        "quote": quote if quote is not None else lines[line - 1],
        "sha256": digest,
    }


def _make_pdf_bytes(pages: list[list[str]]) -> bytes:
    def esc(line: str) -> bytes:
        return line.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)").encode("latin-1")

    bodies: dict[int, bytes] = {1: b"<< /Type /Catalog /Pages 2 0 R >>"}
    kids = []
    obj = 3
    streams: dict[int, bytes] = {}
    for lines in pages:
        page_obj, stream_obj = obj, obj + 1
        kids.append(f"{page_obj} 0 R")
        obj += 2
    font_obj = obj
    bodies[2] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(pages)} >>".encode()
    obj = 3
    for lines in pages:
        page_obj, stream_obj = obj, obj + 1
        bodies[page_obj] = (
            f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] "
            f"/Resources << /Font << /F1 {font_obj} 0 R >> >> "
            f"/Contents {stream_obj} 0 R >>"
        ).encode()
        parts = [b"BT /F1 12 Tf 72 720 Td 14 TL"]
        for i, line in enumerate(lines):
            parts.append(b"(" + esc(line) + b") Tj")
            if i < len(lines) - 1:
                parts.append(b"T*")
        parts.append(b"ET")
        streams[stream_obj] = b" ".join(parts)
        obj += 2
    bodies[font_obj] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"
    pdf = b"%PDF-1.4\n"
    offsets = {}
    for num in sorted({*bodies, *streams}):
        body = (
            b"<< /Length %d >>\nstream\n" % len(streams[num]) + streams[num] + b"\nendstream"
            if num in streams
            else bodies[num]
        )
        offsets[num] = len(pdf)
        pdf += f"{num} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(pdf)
    size = max(offsets) + 1
    pdf += f"xref\n0 {size}\n".encode() + b"0000000000 65535 f \n"
    for num in range(1, size):
        pdf += f"{offsets[num]:010d} 00000 n \n".encode()
    return pdf + f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF".encode()


def test_valid_reviewed_text_evidence_is_verified(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    content = "Police d'assurance responsabilite civile.\nCouverture: CHF 5'000'000.\n"
    row = _text_row(pack, "insurance.txt", content, line=2, quote="Couverture: CHF 5'000'000.")
    _write_pack(pack, [row])
    result = load_bidder_pack(pack)
    assert result.issues == []
    assert len(result.evidence) == 1
    ev = result.evidence[0]
    assert ev.trust == "VERIFIED_INTERNAL"
    assert ev.source.trust == "VERIFIED_INTERNAL"
    assert ev.source.line == 2
    assert ev.source.quote == "Couverture: CHF 5'000'000."
    assert ev.source.sha256 == _sha((pack / "insurance.txt").read_bytes())
    assert len(as_evidence(result)) == 1


def test_wrong_quote_stays_in_review(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    row = _text_row(
        pack, "insurance.txt", "Couverture: CHF 5'000'000.\n", quote="Couverture: CHF 10'000'000."
    )
    _write_pack(pack, [row])
    result = load_bidder_pack(pack)
    assert result.evidence == []
    assert any("does not match line" in issue for issue in result.issues)


def test_wrong_hash_stays_in_review(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    row = _text_row(pack, "insurance.txt", "Couverture: CHF 5'000'000.\n")
    (pack / "insurance.txt").write_text("Couverture: CHF 1.\n", encoding="utf-8")
    _write_pack(pack, [row])
    result = load_bidder_pack(pack)
    assert result.evidence == []
    assert any("sha256 does not match" in issue for issue in result.issues)


def test_missing_file_stays_in_review(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    row = {
        "field": "insurance",
        "value": 1,
        "unit": "CHF",
        "valid_until": "2027-01-01",
        "file": "gone.txt",
        "line": 1,
        "quote": "hello",
        "sha256": "0" * 64,
    }
    _write_pack(pack, [row])
    result = load_bidder_pack(pack)
    assert result.evidence == []
    assert any("missing from the pack" in issue for issue in result.issues)


def test_missing_attestation_verifies_nothing(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    row = _text_row(pack, "insurance.txt", "Couverture: CHF 5'000'000.\n")
    _write_pack(pack, [row], reviewed_by="", reviewed_at="")
    result = load_bidder_pack(pack)
    assert result.evidence == []
    assert any("attestation" in issue for issue in result.issues)


def test_invalid_dates_rejected(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    row = _text_row(
        pack,
        "a.txt",
        "word\n",
        field="references",
        value=3,
        unit="projects",
        valid_until="not-a-date",
    )
    row["valid_from"] = "2027-01-01"
    _write_pack(pack, [row])
    result = load_bidder_pack(pack)
    assert result.evidence == []
    assert any("not a valid ISO date" in issue for issue in result.issues)


def test_expiry_before_start_rejected(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    row = _text_row(
        pack,
        "a.txt",
        "word\n",
        field="references",
        value=3,
        unit="projects",
        valid_until="2026-01-01",
    )
    row["valid_from"] = "2026-06-01"
    _write_pack(pack, [row])
    result = load_bidder_pack(pack)
    assert result.evidence == []
    assert any("precedes valid_from" in issue for issue in result.issues)


def test_path_traversal_rejected(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    (tmp_path / "evil.txt").write_text("evil\n", encoding="utf-8")
    row = {
        "field": "insurance",
        "value": 1,
        "unit": "CHF",
        "valid_until": "2027-01-01",
        "file": "../evil.txt",
        "line": 1,
        "quote": "evil",
        "sha256": "0" * 64,
    }
    _write_pack(pack, [row])
    result = load_bidder_pack(pack)
    assert result.evidence == []
    assert any("escapes the pack root" in issue for issue in result.issues)


def test_symlink_rejected_without_reading_target(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    outside = tmp_path / "secret.txt"
    outside.write_text("secret payload\n", encoding="utf-8")
    (pack / "link.txt").symlink_to(outside)
    row = {
        "field": "insurance",
        "value": 1,
        "unit": "CHF",
        "valid_until": "2027-01-01",
        "file": "link.txt",
        "line": 1,
        "quote": "secret payload",
        "sha256": _sha(b"secret payload\n"),
    }
    _write_pack(pack, [row])
    result = load_bidder_pack(pack)
    assert result.evidence == []
    assert all(
        "secret payload" not in (ev.source.quote if ev.source else "") for ev in result.evidence
    )


def test_no_fallback_to_demo_fixtures(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    row = {
        "field": "insurance",
        "value": 1,
        "unit": "CHF",
        "valid_until": "2027-01-01",
        "file": "data/demo/evidence/insurance_renewal_2026.txt",
        "line": 1,
        "quote": "x",
        "sha256": "0" * 64,
    }
    _write_pack(pack, [row])
    result = load_bidder_pack(pack)
    assert result.evidence == []
    # The demo path is never read: it is either outside the pack or missing inside it.
    assert any(
        "escapes the pack root" in issue or "missing from the pack" in issue
        for issue in result.issues
    )


def test_pdf_evidence_with_page_location(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    pdf = _make_pdf_bytes([["Cover page."], ["ISO 27001 certificate valid until 2027-03-31."]])
    (pack / "cert.pdf").write_bytes(pdf)
    row = {
        "field": "certifications",
        "value": ["ISO 27001"],
        "unit": "names",
        "valid_until": "2027-03-31",
        "file": "cert.pdf",
        "page": 2,
        "quote": "ISO 27001 certificate valid until 2027-03-31.",
        "sha256": _sha(pdf),
    }
    _write_pack(pack, [row])
    result = load_bidder_pack(pack)
    assert result.issues == []
    assert len(result.evidence) == 1
    assert result.evidence[0].source.page == 2


def test_list_and_string_values_accepted(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    row_list = _text_row(
        pack,
        "langs.txt",
        "Französisch, Deutsch\n",
        field="languages",
        value=["French", "German"],
        unit="languages",
        valid_until="2027-01-01",
        quote="Französisch, Deutsch",
    )
    row_str = _text_row(
        pack,
        "cert.txt",
        "ISO 27001\n",
        field="certifications",
        value="ISO 27001",
        unit="names",
        valid_until="2027-01-01",
        quote="ISO 27001",
    )
    _write_pack(pack, [row_list, row_str])
    result = load_bidder_pack(pack)
    assert result.issues == []
    assert len(result.evidence) == 2


def test_empty_pack_reports_unknown_not_pass(tmp_path):
    pack = tmp_path / "pack"
    _write_pack(pack, [])
    result = load_bidder_pack(pack)
    assert result.evidence == []
    assert any("must stay UNKNOWN" in issue for issue in result.issues)


def test_missing_manifest_raises(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    with pytest.raises(ValueError, match="manifest.json is missing"):
        load_bidder_pack(pack)
