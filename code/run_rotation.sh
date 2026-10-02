#!/usr/bin/env bash
# Rotation rule (--rotate-wait) on scenario 2, for docs/data/experiments/ (export_docs_data.py,
# EXPERIMENTS) and issue #7. Run from code/ after run_panel_scenarios.sh, which writes the start plan
# (current_agenda.csv). 60 minutes each, all from the same start: without the rule, the members of
# the last proposal of a meeting skip the next meeting (-1), or wait at most 2 proposals there.
set -u
P=../data/tdf/panel.csv; R=${RESULTS:-../data/tdf/results}; O=$R/rotation
mkdir -p "$O"
for v in none:x skip:-1 wait2:2; do
  name=free_${v%%:*}; wait=${v#*:}
  rule=(); [ "$wait" != x ] && rule=(--rotate-wait "$wait")
  echo "$(date +%H:%M) $name: start"
  python -m models.panel_model $P --next-meeting M3 --start "$R/current_agenda.csv" --time-limit 3600 \
    "${rule[@]}" --out "$O/$name" > "$O/$name.log" 2>&1
  echo "$(date +%H:%M) $name: $(grep -E '^objective' "$O/$name.log")"
  python -m models.check_agenda $P "$O/${name}_agenda.csv" --next-meeting M3 --max-per-member 5 | tail -1
done
