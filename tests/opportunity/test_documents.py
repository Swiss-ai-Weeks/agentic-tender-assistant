"""Focused tests for the local tender document pack importer."""

import json
import subprocess
import sys
from pathlib import Path

from src.opportunity import documents
from src.opportunity.compiler import compile_clause
from src.opportunity.documents import compiler_inputs, import_pack


def _write(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


def _make_pdf_bytes(pages: list[list[str]]) -> bytes:
    """Build a minimal single-font PDF; text lines are WinAnsi (latin-1) encodable."""

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
        if lines:
            parts = [b"BT /F1 12 Tf 72 720 Td 14 TL"]
            for i, line in enumerate(lines):
                parts.append(b"(" + esc(line) + b") Tj")
                if i < len(lines) - 1:
                    parts.append(b"T*")
            parts.append(b"ET")
            streams[stream_obj] = b" ".join(parts)
        else:
            streams[stream_obj] = b""
        obj += 2
    bodies[font_obj] = (
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    )
    pdf = b"%PDF-1.4\n"
    offsets = {}
    for num in sorted({*bodies, *streams}):
        if num in streams:
            body = b"<< /Length %d >>\nstream\n" % len(streams[num]) + streams[num] + b"\nendstream"
        else:
            body = bodies[num]
        offsets[num] = len(pdf)
        pdf += f"{num} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_at = len(pdf)
    size = max(offsets) + 1
    pdf += f"xref\n0 {size}\n".encode() + b"0000000000 65535 f \n"
    for num in range(1, size):
        pdf += f"{offsets[num]:010d} 00000 n \n".encode()
    pdf += f"trailer\n<< /Size {size} /Root 1 0 R >>\nstartxref\n{xref_at}\n%%EOF".encode()
    return pdf


def test_text_unicode_preserved_with_exact_quotes(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    text = (
        "Le soumissionnaire doit fournir trois références comparables.\n"
        "\n"
        "Der Bieter muss eine gültige ISO 27001 Zertifizierung haben.\n"
        "\n"
        "L'offerente deve disporre di un'assicurazione responsabilità di CHF 5M.\n"
    )
    _write(pack / "avis.txt", text)
    result = import_pack(pack, "T-1", source_uri="pack://local/T-1")
    assert result.complete_documents is False
    assert len(result.clauses) == 3
    assert "références comparables" in result.clauses[0].text
    assert "gültige" in result.clauses[1].text
    assert "assicurazione" in result.clauses[2].text
    raw = (pack / "avis.txt").read_bytes()
    digest = __import__("hashlib").sha256(raw).hexdigest()
    for clause in result.clauses:
        assert clause.source.sha256 == digest
        assert clause.source.quote == clause.text
        assert clause.source.quote in text
        assert clause.source.trust == "VERIFIED_INTERNAL"
    assert result.clauses[1].line == 3
    assert result.clauses[2].line == 5


def test_actual_pdf_text_extraction_with_pypdf(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "notice.pdf").write_bytes(
        _make_pdf_bytes([["The bidder must hold ISO 27001."], ["Second paragraph here."]])
    )
    result = import_pack(pack, "T-PDF")
    assert result.files[0].status == "EXTRACTED"
    assert result.files[0].page_count == 2
    assert len(result.clauses) == 2
    assert [c.page for c in result.clauses] == [1, 2]
    assert "ISO 27001" in result.clauses[0].text
    assert result.clauses[0].source.quote == result.clauses[0].text


def test_empty_text_file_needs_review(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    _write(pack / "empty.txt", "   \n  \n")
    result = import_pack(pack, "T-E")
    assert result.files[0].status == "EMPTY"
    assert result.clauses == []
    assert any("EMPTY" in item for item in result.needs_review)


def test_scanned_pdf_marked_via_mock(tmp_path, monkeypatch):
    class Page:
        def extract_text(self):
            return "   \n"

    class Reader:
        is_encrypted = False

        def __init__(self, *args, **kwargs):
            self.pages = [Page(), Page()]

    monkeypatch.setattr(documents, "PdfReader", Reader)
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "scan.pdf").write_bytes(b"%PDF-1.4 fake")
    result = import_pack(pack, "T-S")
    assert result.files[0].status == "SCANNED"
    assert result.clauses == []


def test_encrypted_pdf_marked_via_mock(tmp_path, monkeypatch):
    class Reader:
        is_encrypted = True

        def __init__(self, *args, **kwargs):
            self.pages = []

        def decrypt(self, password):
            return 0

    monkeypatch.setattr(documents, "PdfReader", Reader)
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "locked.pdf").write_bytes(b"%PDF-1.4 fake-encrypted")
    result = import_pack(pack, "T-X")
    assert result.files[0].status == "ENCRYPTED"
    assert result.clauses == []


def test_unsupported_suffix_and_oversize(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    (pack / "photo.png").write_bytes(b"\x89PNG fake")
    _write(pack / "big.txt", "x" * 100)
    result = import_pack(pack, "T-L", max_file_bytes=10)
    by_name = {d.name: d for d in result.files}
    assert by_name["photo.png"].status == "UNSUPPORTED"
    assert by_name["big.txt"].status == "OVERSIZE"


def test_manifest_path_escape_rejected(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    _write(pack / "a.txt", "hello")
    (pack / "manifest.json").write_text(json.dumps({"tender_id": "T-M", "files": ["../evil.txt"]}))
    try:
        import_pack(pack, "T-M")
    except ValueError as exc:
        assert "escapes" in str(exc)
    else:
        raise AssertionError("path traversal manifest entry was not rejected")


def test_symlink_rejected_without_following(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    outside = tmp_path / "secret.txt"
    _write(outside, "secret content")
    (pack / "link.txt").symlink_to(outside)
    _write(pack / "real.txt", "real paragraph here.")
    (pack / "manifest.json").write_text(
        json.dumps({"tender_id": "T-SYM", "files": ["link.txt", "real.txt"]})
    )
    result = import_pack(pack, "T-SYM")
    by_name = {d.name: d for d in result.files}
    assert by_name["link.txt"].status == "UNSUPPORTED"
    assert "secret content" not in " ".join(c.text for c in result.clauses)
    assert any(c.document == "real.txt" for c in result.clauses)


def test_completeness_never_inferred_from_extraction(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    _write(pack / "a.txt", "Clean paragraph one.\n\nClean paragraph two.")
    ok = import_pack(pack, "T-C")
    assert ok.complete_documents is False
    assert any("COMPLETE SET UNVERIFIED" in item for item in ok.needs_review)
    flagged = import_pack(pack, "T-C", complete_set_reviewed=True, reviewed_by=None)
    assert flagged.complete_documents is False
    reviewed = import_pack(pack, "T-C", complete_set_reviewed=True, reviewed_by="j.doe@example.ch")
    assert reviewed.complete_documents is True
    assert reviewed.reviewed_by == "j.doe@example.ch"


def test_unhandled_text_preserved_and_compiler_compatible(tmp_path):
    pack = tmp_path / "pack"
    pack.mkdir()
    _write(
        pack / "mix.txt",
        "The bidder must hold a valid ISO 27001 certification.\n\n"
        "General project background with no rule pattern at all.",
    )
    result = import_pack(pack, "T-K")
    assert len(result.clauses) == 2
    inputs = compiler_inputs(result)
    assert len(inputs) == 2
    rules = [compile_clause(text, source, ident) for ident, text, source in inputs]
    assert rules[0].status == "VERIFIED"
    assert rules[1].status == "UNSUPPORTED"
    assert rules[1].raw_clause == result.clauses[1].text


def test_cli_writes_new_output_and_refuses_overwrite(tmp_path, monkeypatch):
    import os

    pack = tmp_path / "pack"
    pack.mkdir()
    _write(pack / "a.txt", "First paragraph.\n\nSecond paragraph.")
    out = tmp_path / "out"
    script = Path("scripts/import_tender_documents.py").resolve()
    root = Path("pyproject.toml").resolve().parent
    env = {**os.environ, "PYTHONPATH": str(root) + os.pathsep + os.environ.get("PYTHONPATH", "")}
    first = subprocess.run(
        [sys.executable, str(script), str(pack), "--tender-id", "T-CLI", "--out", str(out)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert first.returncode == 0, first.stderr
    payload = json.loads((out / "imported_pack.json").read_text(encoding="utf-8"))
    assert payload["tender_id"] == "T-CLI"
    assert payload["complete_documents"] is False
    assert len(payload["clauses"]) == 2
    second = subprocess.run(
        [sys.executable, str(script), str(pack), "--tender-id", "T-CLI", "--out", str(out)],
        capture_output=True,
        text=True,
        env=env,
        check=False,
    )
    assert second.returncode == 2
