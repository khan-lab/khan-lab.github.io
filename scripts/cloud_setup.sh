#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p .scratch/{sources,logs,builds,screenshots,tmp,cache}
if ! command -v pixi >/dev/null 2>&1; then
  echo 'Install Pixi 0.83.0 using https://pixi.sh, then rerun this script.' >&2
  exit 1
fi
pixi --version
pixi install --locked
pixi run check
printf 'Setup complete. Run pixi run preview to view the site. No deployment enabled.\n'
