#!/usr/bin/env bash
# Builds the folder that is uploaded to the Hugging Face Space: README, app.py, a flattened
# requirements.txt, and api/ and worker/ without caches. Usage: deploy/hf-space/assemble.sh OUT_DIR
set -euo pipefail
out="${1:?usage: assemble.sh OUT_DIR}"
py="${PYTHON:-python3}"
rm -rf "$out" && mkdir -p "$out"
cp deploy/hf-space/README.md deploy/hf-space/app.py "$out/"
"$py" deploy/hf-space/flatten_requirements.py deploy/hf-space/requirements.txt "$out/requirements.txt"
cp -r api worker "$out/"
find "$out" -name '__pycache__' -type d -prune -exec rm -rf {} +
