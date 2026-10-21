#!/bin/sh
# Calculeaza versiunea si reconstruieste containerul.
set -e
cd "$(dirname "$0")/.."
python3 tools/version.py
docker compose up -d --build
