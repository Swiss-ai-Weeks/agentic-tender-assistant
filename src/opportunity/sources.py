"""Immutable raw source storage with tender versioning.

A changed tender becomes a new version; an unchanged source keeps its version.
Qualification results can therefore always name the exact tender version they
evaluated.
"""
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / 'data' / 'raw'


def store_version(tender_id: str, raw: bytes, url: str) -> dict:
    digest = hashlib.sha256(raw).hexdigest()
    base = RAW / 'simap' / f'tender_{tender_id}'
    if base.exists():
        for vdir in sorted(base.glob('version_*')):
            meta_path = vdir / 'meta.json'
            if meta_path.exists() and json.loads(meta_path.read_text()).get('sha256') == digest:
                return json.loads(meta_path.read_text())
    existing = sorted(base.glob('version_*')) if base.exists() else []
    version = len(existing) + 1
    vdir = base / f'version_{version:03d}'
    vdir.mkdir(parents=True, exist_ok=True)
    (vdir / 'payload.json').write_bytes(raw)
    meta = {'tender_id': tender_id, 'version': version, 'sha256': digest, 'url': url,
            'retrieved_at': datetime.now(UTC).isoformat(timespec='seconds')}
    (vdir / 'meta.json').write_text(json.dumps(meta, indent=2) + '\n')
    return meta
