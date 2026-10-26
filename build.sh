#!/usr/bin/env bash
# Build build/lambda.zip for the python3.12 x86_64 Lambda runtime.
set -euo pipefail
cd "$(dirname "$0")"

rm -rf build/package build/lambda.zip
mkdir -p build/package

uv export --no-dev --no-hashes --no-emit-project --format requirements-txt > build/requirements.txt
uv pip install \
  --target build/package \
  --python-platform x86_64-manylinux2014 \
  --python-version 3.12 \
  --only-binary :all: \
  -r build/requirements.txt

cp -r jobscout config profile build/package/
(cd build/package && zip -qr ../lambda.zip . -x '*__pycache__*')
echo "Built build/lambda.zip ($(du -h build/lambda.zip | cut -f1))"
