"""Local completion records for PDF conversion; no database service required."""

import hashlib
import json
import os
from pathlib import Path
import tempfile
from threading import RLock


# Bound memory use while serializing identical documents in the threaded runner.
_LOCKS = [RLock() for _ in range(64)]


def file_sha256(path):
    digest = hashlib.sha256()
    with open(path, "rb") as source:
        for block in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def atomic_write(path, text):
    """Publish a complete file, leaving the previous output intact on failure."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=path.parent, suffix=".tmp", delete=False
        ) as handle:
            temporary = handle.name
            handle.write(text)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)


class ConversionCache:
    def __init__(self, output_dir, source_hash, symbol, year, period):
        self.output_dir = Path(output_dir)
        self.source_hash = source_hash
        identity = json.dumps([str(symbol), str(year), period, source_hash])
        key = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        self.path = self.output_dir / ".pdf_conversion_cache" / (key + ".json")
        self.lock = _LOCKS[int(key[:8], 16) % len(_LOCKS)]

    def completed(self):
        """A record alone is insufficient: verify the entire saved output."""
        try:
            record = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(record, dict) or record.get("version") != 1:
                return None
            if record.get("source_sha256") != self.source_hash:
                return None
            name = record.get("output_file")
            if not isinstance(name, str) or Path(name).name != name:
                return None
            output = self.output_dir / name
            if not output.is_file() or output.stat().st_size == 0:
                return None
            if file_sha256(output) != record.get("output_sha256"):
                return None
            return record
        except (OSError, ValueError, TypeError):
            return None

    def record_success(self, output_file, parsed_by):
        output = self.output_dir / output_file
        atomic_write(self.path, json.dumps({
            "version": 1,
            "source_sha256": self.source_hash,
            "output_file": output_file,
            "output_sha256": file_sha256(output),
            "parsed_by": parsed_by,
        }, indent=2))
