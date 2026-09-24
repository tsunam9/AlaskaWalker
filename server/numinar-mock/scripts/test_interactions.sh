#!/usr/bin/env bash
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
python3 "$here/test_api.py" interactions "${1:-http://127.0.0.1:19002}"
