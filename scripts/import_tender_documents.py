"""Import a local tender document pack to a NEW output directory. No fetching."""

import argparse
import sys
from pathlib import Path

from src.opportunity.documents import import_pack


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Import a local tender document pack.")
    parser.add_argument("pack", help="Local pack directory (never modified).")
    parser.add_argument("--tender-id", required=True)
    parser.add_argument("--tender-version", type=int, default=1)
    parser.add_argument("--source-uri", default="")
    parser.add_argument("--out", required=True, help="NEW output directory; refuses to overwrite.")
    parser.add_argument(
        "--complete-set-reviewed",
        action="store_true",
        help="Human attests the document set is complete.",
    )
    parser.add_argument("--reviewed-by", default=None)
    parser.add_argument("--max-file-bytes", type=int, default=8 * 1024 * 1024)
    parser.add_argument("--max-files", type=int, default=50)
    parser.add_argument("--max-pages", type=int, default=200)
    args = parser.parse_args(argv)

    out = Path(args.out)
    if out.exists():
        print(f"Refusing to overwrite existing output: {out}", file=sys.stderr)
        return 2
    try:
        pack = import_pack(
            Path(args.pack),
            args.tender_id,
            tender_version=args.tender_version,
            source_uri=args.source_uri,
            complete_set_reviewed=args.complete_set_reviewed,
            reviewed_by=args.reviewed_by,
            max_file_bytes=args.max_file_bytes,
            max_files=args.max_files,
            max_pages=args.max_pages,
        )
    except ValueError as exc:
        print(f"Invalid pack: {exc}", file=sys.stderr)
        return 2
    out.mkdir(parents=True)
    (out / "imported_pack.json").write_text(
        pack.model_dump_json(indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )

    counts: dict[str, int] = {}
    for doc in pack.files:
        counts[doc.status] = counts.get(doc.status, 0) + 1
    print(
        f"Tender {pack.tender_id} v{pack.tender_version}: "
        f"{len(pack.files)} files, {len(pack.clauses)} clauses."
    )
    for status in sorted(counts):
        names = [d.name for d in pack.files if d.status == status]
        print(f"  {status} ({counts[status]}): {', '.join(names)}")
    print(f"  complete_documents={pack.complete_documents} (reviewed_by={pack.reviewed_by or '—'})")
    for item in pack.needs_review:
        print(f"  REVIEW: {item}")
    for warning in pack.warnings:
        print(f"  WARNING: {warning}")
    print(f"Wrote {out / 'imported_pack.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
