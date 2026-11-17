#!/usr/bin/env bash
set -euo pipefail
mkdir -p "$1"
cd "$1"
{ printf '%s\n' 202601 202512 202511; for y in 2024 2025; do for m in $(seq -w 1 12); do [[ "$y$m" == 202512 || "$y$m" == 202511 ]] || printf '%s\n' "$y$m"; done; done; } |
xargs -P 6 -n 1 bash -c 'month=$0; file="$month.zip"; if [[ ! -f "$file" ]]; then curl -fsSL --retry 3 --connect-timeout 15 --max-time 700 "https://s3.amazonaws.com/tripdata/$month-citibike-tripdata.zip" -o "$file.part" && mv "$file.part" "$file"; fi'
