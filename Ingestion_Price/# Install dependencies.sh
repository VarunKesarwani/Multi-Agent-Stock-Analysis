#!/usr/bin/env bash
# Run from any directory with: bash 'Ingestion_Price/# Install dependencies.sh' [main.py options]
# Example: bash 'Ingestion_Price/# Install dependencies.sh' --start-date 2025-01-01 --end-date 2025-12-31 --skip-company-master --skip-company-market --skip-fo

set -euo pipefail

script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
cd "$script_dir"

if [[ -z "${POSTGRES_CONNECTION_STRING:-}" ]]; then
  echo "Set POSTGRES_CONNECTION_STRING before running ingestion." >&2
  echo "For the Compose database use 127.0.0.1:6543 and URL-encode special characters in the password." >&2
  exit 1
fi

python -m pip install -r requirements.txt
python main.py "$@"
