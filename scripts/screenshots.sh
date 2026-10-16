#!/usr/bin/env bash
# Regenerate the README screenshots (Hyprland only). Calls the real models.
set -euo pipefail
cd "$(dirname "$0")/.."
out=docs/screenshots
hyprctl eval 'hl.config({ cursor = { invisible = true } })' >/dev/null
trap "hyprctl eval 'hl.config({ cursor = { invisible = false } })' >/dev/null" EXIT
for shot in palette result translate settings; do
  /usr/bin/python3 -I scripts/screenshots.py "$out" "$shot"
done
ADW_DEBUG_COLOR_SCHEME=prefer-light /usr/bin/python3 -I scripts/screenshots.py "$out" result-light
