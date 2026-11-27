#!/usr/bin/env bash
# Builds the folder that is uploaded to the Hugging Face Space: the Space files plus api/ and
# worker/ (Python and requirements only). Usage: deploy/hf-space/assemble.sh OUT_DIR
set -euo pipefail
out="${1:?usage: assemble.sh OUT_DIR}"
rm -rf "$out" && mkdir -p "$out"
cp deploy/hf-space/README.md deploy/hf-space/app.py deploy/hf-space/requirements.txt "$out/"
cp -r api worker "$out/"
find "$out" -name '__pycache__' -type d -prune -exec rm -rf {} +
