"""Local tender document pack importer.

Reads a bounded local directory (PDF + UTF-8 text), preserves original bytes
(SHA-256), and emits exact page/line-level quoted clauses as typed
``Source`` objects compatible with ``compile_clause``.

Never claims the document set is complete from extraction success alone:
``complete_documents`` stays False unless the caller passes an explicit
human-reviewed flag with reviewer provenance.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from pydantic import BaseModel, Field
from pypdf import PdfReader

from src.opportunity.models import Source

VERSION = "documents/0.1"

TEXT_SUFFIXES = {".txt", ".md"}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | {".pdf"}

MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_FILES = 50
MAX_PAGES = 200
MAX_CLAUSES_PER_FILE = 2000

FileStatus = str  # EXTRACTED | EMPTY | SCANNED | ENCRYPTED | UNSUPPORTED | OVERSIZE


class ImportedClause(BaseModel):
    id: str
    text: str
    source: Source
    document: str
    page: int | None = None
    line: int | None = None


class ImportedDocument(BaseModel):
    name: str
    sha256: str
    size_bytes: int
    status: str
    reason: str = ""
    page_count: int | None = None
    char_count: int = 0
    clause_ids: list[str] = Field(default_factory=list)


class ImportedPack(BaseModel):
    tender_id: str
    tender_version: int = 1
    source_uri: str = ""
    complete_documents: bool = False
    reviewed_by: str | None = None
    files: list[ImportedDocument] = Field(default_factory=list)
    clauses: list[ImportedClause] = Field(default_factory=list)
    needs_review: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    importer_version: str = VERSION


def _utc_today() -> str:
    return datetime.now(UTC).date().isoformat()


def _split_paragraphs(text: str) -> list[tuple[str, int]]:
    """Split conservatively on blank lines; return (exact quote, 1-based start line)."""
    out: list[tuple[str, int]] = []
    for match in re.finditer(r"(?:[^\n][\s\S]*?)(?=\n\s*\n|\Z)", text):
        raw = match.group(0)
        quote = raw.strip()
        if not quote.strip():
            continue
        start_line = text.count("\n", 0, match.start()) + 1
        out.append((quote, start_line))
    return out


def _clause_source(
    tender_id: str,
    version: int,
    source_uri: str,
    name: str,
    quote: str,
    sha256: str,
    page: int | None,
    line: int | None,
    index: int,
) -> Source:
    anchor = f"p{page}" if page is not None else "txt"
    anchor += f"l{line}" if line is not None else ""
    url_base = source_uri or f"pack://{tender_id}/v{version}/{name}"
    return Source(
        id=f"{tender_id}/v{version}/{name}#{anchor}-{index}",
        document=name,
        quote=quote,
        line=line,
        page=page,
        url=f"{url_base}#{anchor}-{index}",
        trust="VERIFIED_INTERNAL",
        retrieved_at=_utc_today(),
        sha256=sha256,
    )


def _read_text_bytes(raw: bytes) -> tuple[str | None, str]:
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding), encoding
        except UnicodeDecodeError:
            continue
    return None, ""


def _import_text_file(
    name: str,
    raw: bytes,
    sha256: str,
    tender_id: str,
    version: int,
    source_uri: str,
    clause_seq: int,
) -> tuple[ImportedDocument, list[ImportedClause]]:
    if not raw.strip():
        doc = ImportedDocument(
            name=name,
            sha256=sha256,
            size_bytes=len(raw),
            status="EMPTY",
            reason="File has no readable text.",
        )
        return doc, []
    decoded, _ = _read_text_bytes(raw)
    if decoded is None:
        doc = ImportedDocument(
            name=name,
            sha256=sha256,
            size_bytes=len(raw),
            status="UNSUPPORTED",
            reason="Bytes are not decodable text.",
        )
        return doc, []
    if not decoded.strip():
        doc = ImportedDocument(
            name=name,
            sha256=sha256,
            size_bytes=len(raw),
            status="EMPTY",
            reason="File has no readable text.",
        )
        return doc, []
    clauses: list[ImportedClause] = []
    for i, (quote, line) in enumerate(_split_paragraphs(decoded)):
        if len(clauses) >= MAX_CLAUSES_PER_FILE:
            break
        ident = f"{tender_id}-C{clause_seq + len(clauses) + 1:04d}"
        clauses.append(
            ImportedClause(
                id=ident,
                text=quote,
                source=_clause_source(
                    tender_id, version, source_uri, name, quote, sha256, None, line, len(clauses)
                ),
                document=name,
                page=None,
                line=line,
            )
        )
    doc = ImportedDocument(
        name=name,
        sha256=sha256,
        size_bytes=len(raw),
        status="EXTRACTED",
        char_count=len(decoded),
        clause_ids=[c.id for c in clauses],
    )
    return doc, clauses


def _import_pdf_file(
    name: str,
    raw: bytes,
    sha256: str,
    tender_id: str,
    version: int,
    source_uri: str,
    clause_seq: int,
    max_pages: int,
) -> tuple[ImportedDocument, list[ImportedClause]]:
    import io

    try:
        reader = PdfReader(io.BytesIO(raw))
    except Exception as exc:  # noqa: BLE001
        msg = str(exc).lower()
        status = "ENCRYPTED" if "encrypt" in msg else "UNSUPPORTED"
        reason = f"PDF could not be opened ({status.lower()}); human review required."
        return ImportedDocument(
            name=name, sha256=sha256, size_bytes=len(raw), status=status, reason=reason
        ), []
    try:
        if getattr(reader, "is_encrypted", False):
            try:
                ok = reader.decrypt("")
            except Exception:  # noqa: BLE001
                ok = 0
            if not ok:
                return ImportedDocument(
                    name=name,
                    sha256=sha256,
                    size_bytes=len(raw),
                    status="ENCRYPTED",
                    reason="PDF is encrypted; password-protected content needs human review.",
                ), []
    except Exception as exc:  # noqa: BLE001
        return ImportedDocument(
            name=name, sha256=sha256, size_bytes=len(raw), status="ENCRYPTED", reason=str(exc)[:200]
        ), []
    try:
        pages = list(reader.pages)
    except Exception as exc:  # noqa: BLE001
        return ImportedDocument(
            name=name,
            sha256=sha256,
            size_bytes=len(raw),
            status="UNSUPPORTED",
            reason=f"PDF pages unreadable: {exc}"[:200],
        ), []
    if not pages:
        return ImportedDocument(
            name=name,
            sha256=sha256,
            size_bytes=len(raw),
            status="EMPTY",
            reason="PDF has no pages.",
        ), []
    if len(pages) > max_pages:
        return ImportedDocument(
            name=name,
            sha256=sha256,
            size_bytes=len(raw),
            status="OVERSIZE",
            reason=f"{len(pages)} pages exceeds the bounded limit of {max_pages}.",
            page_count=len(pages),
        ), []
    texts: list[str] = []
    try:
        for page in pages:
            texts.append(page.extract_text() or "")
    except Exception as exc:  # noqa: BLE001
        return ImportedDocument(
            name=name,
            sha256=sha256,
            size_bytes=len(raw),
            status="UNSUPPORTED",
            reason=f"PDF text extraction failed: {exc}"[:200],
            page_count=len(pages),
        ), []
    if not "".join(texts).strip():
        return ImportedDocument(
            name=name,
            sha256=sha256,
            size_bytes=len(raw),
            status="SCANNED",
            reason="PDF holds no extractable text (likely scanned images); OCR/human review required.",
            page_count=len(pages),
        ), []
    clauses: list[ImportedClause] = []
    for pnum, text in enumerate(texts, 1):
        for quote, line in _split_paragraphs(text):
            if len(clauses) >= MAX_CLAUSES_PER_FILE:
                break
            ident = f"{tender_id}-C{clause_seq + len(clauses) + 1:04d}"
            clauses.append(
                ImportedClause(
                    id=ident,
                    text=quote,
                    source=_clause_source(
                        tender_id,
                        version,
                        source_uri,
                        name,
                        quote,
                        sha256,
                        pnum,
                        line,
                        len(clauses),
                    ),
                    document=name,
                    page=pnum,
                    line=line,
                )
            )
    doc = ImportedDocument(
        name=name,
        sha256=sha256,
        size_bytes=len(raw),
        status="EXTRACTED",
        page_count=len(pages),
        char_count=len("".join(texts)),
        clause_ids=[c.id for c in clauses],
    )
    return doc, clauses


def _safe_join(pack_root: Path, rel: str) -> Path:
    raw = pack_root / rel
    if raw.is_symlink():
        return raw  # symlink rejection is handled by the caller, not raised here
    candidate = raw
    resolved = (
        candidate.resolve()
        if candidate.exists() or candidate.is_symlink()
        else (pack_root / rel).absolute()
    )
    try:
        resolved.relative_to(pack_root.resolve())
    except ValueError:
        raise ValueError(f"Manifest entry escapes the pack root: {rel!r}")
    return resolved


def _load_manifest(pack_root: Path) -> dict | None:
    path = pack_root / "manifest.json"
    if not path.exists() or path.is_symlink():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"manifest.json is not valid JSON: {exc}")
    if not isinstance(data, dict):
        raise ValueError("manifest.json must be a JSON object.")
    return data


def import_pack(
    pack_root: Path,
    tender_id: str,
    tender_version: int = 1,
    source_uri: str = "",
    complete_set_reviewed: bool = False,
    reviewed_by: str | None = None,
    max_file_bytes: int = MAX_FILE_BYTES,
    max_files: int = MAX_FILES,
    max_pages: int = MAX_PAGES,
) -> ImportedPack:
    """Import one local tender document pack. No network, no model calls."""
    if not tender_id or not tender_id.strip():
        raise ValueError("tender_id is required.")
    root = Path(pack_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"Pack root must be a real local directory: {pack_root}")
    resolved = root.resolve()

    manifest = _load_manifest(resolved)
    wanted: list[str] | None = None
    if manifest is not None:
        if manifest.get("tender_id") and manifest["tender_id"] != tender_id:
            raise ValueError("manifest tender_id does not match the requested tender_id.")
        if manifest.get("version") is not None:
            try:
                tender_version = int(manifest["version"])
            except (TypeError, ValueError):
                raise ValueError("manifest version must be an integer.")
        if manifest.get("source_uri"):
            source_uri = manifest["source_uri"]
        files_field = manifest.get("files")
        if files_field is not None:
            if not isinstance(files_field, list) or not all(
                isinstance(f, str) for f in files_field
            ):
                raise ValueError("manifest files must be a list of relative path strings.")
            for entry in files_field:
                if not entry or entry.startswith(("/", "\\")):
                    raise ValueError(f"Manifest entry is not a relative path: {entry!r}")
                if ".." in Path(entry).parts:
                    raise ValueError(f"Manifest entry escapes the pack root: {entry!r}")
            wanted = sorted(set(files_field))

    if wanted is not None:
        candidates = [_safe_join(resolved, rel) for rel in wanted]
    else:
        candidates = sorted(
            (p for p in resolved.rglob("*") if p.is_file() and p.name != "manifest.json"),
            key=lambda p: p.relative_to(resolved).as_posix(),
        )
    if len(candidates) > max_files:
        raise ValueError(f"Pack lists {len(candidates)} files; bounded limit is {max_files}.")

    pack = ImportedPack(tender_id=tender_id, tender_version=tender_version, source_uri=source_uri)
    seq = 0
    on_disk = {p.relative_to(resolved).as_posix() for p in resolved.rglob("*") if p.is_file()}
    if wanted is not None:
        for extra in sorted(on_disk - set(wanted) - {"manifest.json"}):
            pack.warnings.append(f"Unlisted file present in pack (not imported): {extra}")
            pack.needs_review.append(f"{extra}: UNLISTED — confirm whether it belongs to the set.")

    for path in candidates:
        rel = path.relative_to(resolved).as_posix()
        if path.is_symlink():
            pack.files.append(
                ImportedDocument(
                    name=rel,
                    sha256="",
                    size_bytes=0,
                    status="UNSUPPORTED",
                    reason="Symlink rejected; only real files inside the pack root are imported.",
                )
            )
            pack.needs_review.append(f"{rel}: SYMLINK REJECTED — human review required.")
            continue
        try:
            path.relative_to(resolved)
            target = path.resolve()
            target.relative_to(resolved)
        except ValueError:
            pack.files.append(
                ImportedDocument(
                    name=rel,
                    sha256="",
                    size_bytes=0,
                    status="UNSUPPORTED",
                    reason="Path escapes the pack root; rejected.",
                )
            )
            pack.needs_review.append(f"{rel}: PATH ESCAPE REJECTED — human review required.")
            continue
        if not path.is_file():
            pack.files.append(
                ImportedDocument(
                    name=rel,
                    sha256="",
                    size_bytes=0,
                    status="UNSUPPORTED",
                    reason="Manifest entry is missing from the pack.",
                )
            )
            pack.needs_review.append(f"{rel}: MISSING — human review required.")
            continue
        raw = path.read_bytes()
        sha256 = hashlib.sha256(raw).hexdigest()
        suffix = path.suffix.lower()
        if len(raw) > max_file_bytes:
            pack.files.append(
                ImportedDocument(
                    name=rel,
                    sha256=sha256,
                    size_bytes=len(raw),
                    status="OVERSIZE",
                    reason=f"{len(raw)} bytes exceeds the bounded limit of {max_file_bytes}.",
                )
            )
            pack.needs_review.append(f"{rel}: OVERSIZE — human review required.")
            continue
        if suffix == ".pdf":
            doc, new_clauses = _import_pdf_file(
                rel, raw, sha256, tender_id, tender_version, source_uri, seq, max_pages
            )
        elif suffix in TEXT_SUFFIXES:
            doc, new_clauses = _import_text_file(
                rel, raw, sha256, tender_id, tender_version, source_uri, seq
            )
        else:
            doc, new_clauses = (
                ImportedDocument(
                    name=rel,
                    sha256=sha256,
                    size_bytes=len(raw),
                    status="UNSUPPORTED",
                    reason=f"Suffix {suffix or '(none)'} is not a supported document type (.pdf/.txt/.md).",
                ),
                [],
            )
        pack.files.append(doc)
        pack.clauses.extend(new_clauses)
        seq += len(new_clauses)
        if doc.status != "EXTRACTED":
            pack.needs_review.append(f"{rel}: {doc.status} — {doc.reason}")

    # Completeness is a human attestation, never inferred from extraction success.
    if complete_set_reviewed and reviewed_by and reviewed_by.strip():
        pack.complete_documents = True
        pack.reviewed_by = reviewed_by.strip()
    else:
        pack.complete_documents = False
        if complete_set_reviewed and not (reviewed_by and reviewed_by.strip()):
            pack.warnings.append("complete_set_reviewed ignored: reviewer provenance is required.")
        pack.needs_review.append(
            "COMPLETE SET UNVERIFIED — extraction success alone never marks the set complete."
        )
    return pack


def compiler_inputs(pack: ImportedPack) -> list[tuple[str, str, Source]]:
    """Return (clause_id, text, source) triples ready for ``compile_clause``."""
    return [(c.id, c.text, c.source) for c in pack.clauses]
