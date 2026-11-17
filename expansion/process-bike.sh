#!/usr/bin/env bash
set -euo pipefail
directory=$1
{ printf '%s\n' 202601 202512 202511; for y in 2024 2025; do for m in $(seq -w 1 12); do [[ "$y$m" == 202512 || "$y$m" == 202511 ]] || printf '%s\n' "$y$m"; done; done; } |
xargs -P 5 -n 1 bash -c 'month=$1; if [[ -s "$0/$month.json" ]]; then exit 0; fi; until [[ -s "$0/$month.zip" ]]; do sleep 3; done; python expansion/build_bike.py "$0/$month.zip" "$0/$month.json"' "$directory"
