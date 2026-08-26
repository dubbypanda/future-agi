#!/usr/bin/env bash

set -Eeuo pipefail

if [[ $# -ne 2 ]]; then
  echo "usage: $0 <ee-checkout-root> <ee-cloud-package-target>" >&2
  exit 2
fi

checkout_root="$1"
package_target="$2"

if [[ -f "${checkout_root}/cloud/__init__.py" ]]; then
  package_source="${checkout_root}/cloud"
  package_layout="legacy cloud subdirectory"
elif [[ -f "${checkout_root}/__init__.py" ]]; then
  package_source="${checkout_root}"
  package_layout="package root"
else
  echo "::error::EE checkout has neither cloud/__init__.py nor __init__.py" >&2
  exit 1
fi

mkdir -p "${package_target}"
rsync -a --delete \
  --exclude='.git' \
  --exclude='__pycache__' \
  "${package_source}/" "${package_target}/"

test -f "${package_target}/__init__.py"
test -f "${package_target}/telemetry/schema.py"
test ! -d "${package_target}/cloud"

echo "::notice::Normalized EE ${package_layout} into ${package_target}"
