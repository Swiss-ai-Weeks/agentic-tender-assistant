"""Explicit local bidder evidence-pack loader.

Reads one explicitly selected company evidence directory plus its manifest.
Nothing is scanned outside that directory, and nothing is inferred: only
human-reviewed rows whose exact quote, location and SHA-256 match the source
file become ``VERIFIED_INTERNAL`` evidence. Everything else becomes a review
issue, which downstream evaluation treats as UNKNOWN, never as PASS.

``VERIFIED_INTERNAL`` here means source-backed human attestation (a reviewer
confirmed the quote against the file), not independently verified issuer
authenticity. Synthetic demonstration evidence (``data/demo``) is never
consumed here.
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime
from pathlib import Path

from pydantic import BaseModel, Field

from src.opportunity.models import Evidence, Source

VERSION = "bidder/0.1"

TEXT_SUFFIXES = {".txt", ".md"}
SUPPORTED_SUFFIXES = TEXT_SUFFIXES | {".pdf"}

MAX_ROWS = 500
MAX_FILE_BYTES = 8 * 1024 * 1024
MAX_QUOTE_CHARS = 2000
MAX_FIELD_CHARS = 64


class BidderCompany(BaseModel):
    name: str
    uid: str | None = None


class BidderPack(BaseModel):
    company: BidderCompany
    reviewed_by: str
    reviewed_at: str
    evidence: list[Evidence] = Field(default_factory=list)
    issues: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    loader_version: str = VERSION


def _today() -> str:
    return datetime.now(UTC).date().isoformat()


def _iso_day(raw: object, label: str, issues: list[str]) -> date | None:
    if not isinstance(raw, str) or not raw.strip():
        issues.append(f"{label} is missing or not a date string.")
        return None
    try:
        return date.fromisoformat(raw.strip())
    except ValueError:
        issues.append(f"{label} {raw!r} is not a valid ISO date (YYYY-MM-DD).")
        return None


def _resolve(pack_root: Path, rel: str) -> Path:
    if not rel or rel.startswith(("/", "\\")) or ".." in Path(rel).parts:
        raise ValueError(f"Evidence file escapes the pack root: {rel!r}")
    target = pack_root / rel
    if target.is_symlink():
        raise ValueError(f"Evidence file is a symlink and is rejected: {rel!r}")
    resolved = target.resolve()
    try:
        resolved.relative_to(pack_root.resolve())
    except ValueError:
        raise ValueError(f"Evidence file escapes the pack root: {rel!r}")
    return resolved


def _read_text_file(path: Path) -> tuple[str | None, str]:
    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, f"Evidence file cannot be read: {exc}"
    if len(raw) > MAX_FILE_BYTES:
        return None, f"Evidence file exceeds the bounded limit of {MAX_FILE_BYTES} bytes."
    for encoding in ("utf-8-sig", "cp1252"):
        try:
            return raw.decode(encoding), ""
        except UnicodeDecodeError:
            continue
    return None, "Evidence file bytes are not decodable text."


def _read_pdf_pages(path: Path) -> tuple[list[str] | None, str, str]:
    """Return (page texts, sha256, problem). No OCR; scanned PDFs are reported."""
    from pypdf import PdfReader

    try:
        raw = path.read_bytes()
    except OSError as exc:
        return None, "", f"Evidence file cannot be read: {exc}"
    if len(raw) > MAX_FILE_BYTES:
        return (
            None,
            hashlib.sha256(raw).hexdigest(),
            (f"Evidence file exceeds the bounded limit of {MAX_FILE_BYTES} bytes."),
        )
    digest = hashlib.sha256(raw).hexdigest()
    try:
        import io

        reader = PdfReader(io.BytesIO(raw))
        if getattr(reader, "is_encrypted", False):
            return None, digest, "PDF evidence is encrypted; human review required."
        texts = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # noqa: BLE001
        return None, digest, f"PDF evidence cannot be parsed ({exc}); human review required."
    if not "".join(texts).strip():
        return (
            None,
            digest,
            "PDF evidence holds no extractable text (likely scanned); human review required.",
        )
    return texts, digest, ""


def load_bidder_pack(pack_root: Path) -> BidderPack:
    """Load and validate one explicit bidder evidence pack. No network, no model."""
    root = Path(pack_root)
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"Pack root must be a real local directory: {pack_root}")
    resolved = root.resolve()
    manifest_path = resolved / "manifest.json"
    if manifest_path.is_symlink() or not manifest_path.is_file():
        raise ValueError("Pack manifest manifest.json is missing; cannot invent company evidence.")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except Exception as exc:  # noqa: BLE001
        raise ValueError(f"manifest.json is not valid JSON: {exc}")
    if not isinstance(manifest, dict):
        raise TypeError("manifest.json must be a JSON object.")

    issues: list[str] = []
    warnings: list[str] = []
    company_raw = manifest.get("company")
    company_name = company_raw.get("name") if isinstance(company_raw, dict) else None
    if not company_name or not str(company_name).strip():
        raise ValueError("manifest company.name is required; refusing to attribute evidence.")
    company = BidderCompany(
        name=str(company_name).strip(),
        uid=(str(company_raw.get("uid")).strip() or None) if company_raw.get("uid") else None,
    )
    reviewed_by = manifest.get("reviewed_by")
    reviewed_at = manifest.get("reviewed_at")
    attested = bool(
        isinstance(reviewed_by, str)
        and reviewed_by.strip()
        and isinstance(reviewed_at, str)
        and reviewed_at.strip()
    )
    if isinstance(reviewed_at, str) and reviewed_at.strip():
        try:
            date.fromisoformat(reviewed_at.strip())
        except ValueError:
            issues.append(f"reviewed_at {reviewed_at!r} is not a valid ISO date (YYYY-MM-DD).")
            attested = False
    if not attested:
        issues.append(
            "Human-review attestation (reviewed_by/reviewed_at) is missing or invalid: "
            "no row in this pack can qualify a real bidder."
        )
    rows = manifest.get("evidence")
    if not isinstance(rows, list):
        raise TypeError("manifest evidence must be a list of evidence rows.")
    if len(rows) > MAX_ROWS:
        raise ValueError(f"Pack lists {len(rows)} rows; bounded limit is {MAX_ROWS}.")

    pack = BidderPack(
        company=company,
        reviewed_by=str(reviewed_by or "").strip(),
        reviewed_at=str(reviewed_at or "").strip(),
    )
    for index, row in enumerate(rows):
        label = f"row {index}"
        if not isinstance(row, dict):
            issues.append(f"{label}: not an object; skipped.")
            continue
        field = row.get("field")
        if not isinstance(field, str) or not field.strip() or len(field) > MAX_FIELD_CHARS:
            issues.append(
                f"{label}: field must be a non-empty string (<= {MAX_FIELD_CHARS} chars)."
            )
            continue
        field = field.strip()
        label = f"row {index} ({field})"
        value = row.get("value")
        if not isinstance(value, (int, float, str, list)) or (
            isinstance(value, list) and not all(isinstance(v, str) for v in value)
        ):
            issues.append(f"{label}: value must be a number, string, or list of strings.")
            continue
        if isinstance(value, str) and (not value.strip() or len(value) > 512):
            issues.append(f"{label}: value string must be non-empty (<= 512 chars).")
            continue
        unit = row.get("unit", "")
        if not isinstance(unit, str) or len(unit) > 32:
            issues.append(f"{label}: unit must be a string (<= 32 chars).")
            continue
        row_issues: list[str] = []
        valid_from = (
            _iso_day(row.get("valid_from"), f"{label} valid_from", row_issues)
            if row.get("valid_from")
            else None
        )
        valid_until = _iso_day(row.get("valid_until"), f"{label} valid_until", row_issues)
        if valid_from and valid_until and valid_until < valid_from:
            row_issues.append(
                f"{label}: valid_until {valid_until} precedes valid_from {valid_from}."
            )
        quote = row.get("quote")
        if not isinstance(quote, str) or not quote.strip() or len(quote) > MAX_QUOTE_CHARS:
            row_issues.append(
                f"{label}: quote must be an exact non-empty source excerpt "
                f"(<= {MAX_QUOTE_CHARS} chars)."
            )
            quote = ""
        else:
            quote = quote.strip()
        rel = row.get("file")
        if not isinstance(rel, str) or not rel.strip():
            row_issues.append(f"{label}: file must be a relative path inside the pack.")
            rel = ""
        location_line = row.get("line")
        location_page = row.get("page")
        if location_line is not None and location_page is not None:
            row_issues.append(f"{label}: set exactly one of line (text) or page (PDF).")
        elif location_line is None and location_page is None:
            row_issues.append(
                f"{label}: a source location is required: line for text, page for PDF."
            )
        elif location_line is not None and (
            not isinstance(location_line, int) or location_line < 1
        ):
            row_issues.append(f"{label}: line must be a 1-based line number.")
        elif location_page is not None and (
            not isinstance(location_page, int) or location_page < 1
        ):
            row_issues.append(f"{label}: page must be a 1-based page number.")
        claimed_sha = row.get("sha256")
        if not isinstance(claimed_sha, str) or not claimed_sha.strip():
            row_issues.append(f"{label}: sha256 of the source file is required.")
        if row_issues:
            issues.extend(row_issues)
            continue

        try:
            path = _resolve(resolved, rel.strip())
        except ValueError as exc:
            issues.append(f"{label}: {exc}")
            continue
        if not path.is_file():
            issues.append(f"{label}: source file {rel!r} is missing from the pack.")
            continue
        suffix = path.suffix.lower()
        if suffix not in SUPPORTED_SUFFIXES:
            issues.append(
                f"{label}: suffix {suffix or '(none)'} is not supported "
                "(.txt/.md/.pdf with extractable text only)."
            )
            continue
        if suffix == ".pdf" and location_line is not None:
            issues.append(f"{label}: PDF evidence needs a page location, not a line number.")
            continue
        if suffix in TEXT_SUFFIXES and location_page is not None:
            issues.append(f"{label}: text evidence needs a line location, not a page number.")
            continue

        if suffix in TEXT_SUFFIXES:
            text, problem = _read_text_file(path)
            if text is None:
                issues.append(f"{label}: {problem}")
                continue
            actual_sha = hashlib.sha256(path.read_bytes()).hexdigest()
            if actual_sha != claimed_sha.strip().lower():
                issues.append(f"{label}: sha256 does not match {rel!r}; the file may have changed.")
                continue
            lines = text.splitlines()
            if location_line > len(lines) or quote not in lines[location_line - 1]:
                issues.append(f"{label}: quote does not match line {location_line} of {rel!r}.")
                continue
            if quote not in text:
                issues.append(f"{label}: quote not found verbatim in {rel!r}.")
                continue
            source = Source(
                id=f"bidder/{company.name}/{rel.strip()}#l{location_line}",
                document=path.name,
                quote=quote,
                line=location_line,
                url=f"pack://bidder/{company.name}/{rel.strip()}#l{location_line}",
                trust="VERIFIED_INTERNAL",
                retrieved_at=_today(),
                sha256=actual_sha,
            )
            evidence = Evidence(
                field=field,
                value=value,
                unit=unit.strip(),
                valid_until=valid_until.isoformat(),
                valid_from=valid_from.isoformat() if valid_from else None,
                observed_at=reviewed_at.strip() if attested else None,
                source=source,
                trust="VERIFIED_INTERNAL",
            )
        else:
            pages, actual_sha, problem = _read_pdf_pages(path)
            if pages is None:
                issues.append(f"{label}: {problem}")
                continue
            if actual_sha != claimed_sha.strip().lower():
                issues.append(f"{label}: sha256 does not match {rel!r}; the file may have changed.")
                continue
            if location_page > len(pages) or quote not in pages[location_page - 1]:
                issues.append(f"{label}: quote does not match page {location_page} of {rel!r}.")
                continue
            source = Source(
                id=f"bidder/{company.name}/{rel.strip()}#p{location_page}",
                document=path.name,
                quote=quote,
                page=location_page,
                url=f"pack://bidder/{company.name}/{rel.strip()}#p{location_page}",
                trust="VERIFIED_INTERNAL",
                retrieved_at=_today(),
                sha256=actual_sha,
            )
            evidence = Evidence(
                field=field,
                value=value,
                unit=unit.strip(),
                valid_until=valid_until.isoformat(),
                valid_from=valid_from.isoformat() if valid_from else None,
                observed_at=reviewed_at.strip() if attested else None,
                source=source,
                trust="VERIFIED_INTERNAL",
            )
        if not attested:
            issues.append(f"{label}: pack lacks human-review attestation; row stays in review.")
            continue
        pack.evidence.append(evidence)

    pack.issues.extend(issues)
    pack.warnings.extend(warnings)
    if not pack.evidence:
        pack.issues.append(
            "No verified bidder evidence in this pack: qualification must stay UNKNOWN."
        )
    return pack


def as_evidence(pack: BidderPack) -> list[Evidence]:
    """Evidence list ready for ``engine.evaluate``. Empty means UNKNOWN, never PASS."""
    return list(pack.evidence)
