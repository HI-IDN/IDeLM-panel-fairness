#!/usr/bin/env bash
# Run all review-panel scenarios of the book (docs/scenarios.qmd). Run from code/.
# Each scenario writes <name>_agenda.csv, <name>_members.csv, <name>_coi_present.csv and a log to
# ../data/tdf/results/. Each scenario starts from the solution of the one before (--start).
set -u
P=../data/tdf/panel.csv
R=../data/tdf/results
mkdir -p "$R"

run() {  # run <name> <model options...>
  local name=$1; shift
  echo "$(date +%H:%M) $name: start"
  if python -m models.panel_model "$P" "$@" --out "$R/$name" > "$R/$name.log" 2>&1; then
    echo "$(date +%H:%M) $name: $(grep -E '^objective' "$R/$name.log")"
  else
    echo "$(date +%H:%M) $name: FAILED (see $R/$name.log)"
  fi
}

check() {  # check <name> <check options...>: the agenda follows the rules of its scenario
  local name=$1; shift
  python -m models.check_agenda "$P" "$R/${name}_agenda.csv" "$@" | tail -1 | sed "s/^/  $name check: /"
}

# 1. The staff's meetings, fair order within each meeting.
run current --keep-meetings --fix-meetings M3 --time-limit 300
check current --closed M3 --max-per-member 6
# 2. Next meeting (M3) fixed, later meetings re-optimised.
run free --next-meeting M3 --start "$R/current_agenda.csv" --time-limit 1200
check free --next-meeting M3 --max-per-member 6
# 3. As 2, at most 5 own proposals per meeting.
run free_max4 --next-meeting M3 --max-per-member 4 --start "$R/free_agenda.csv" --time-limit 1200
check free_max4 --next-meeting M3 --max-per-member 4
# 4. As 2, soft target of own proposals per meeting (experienced / new).
run free_target --next-meeting M3 --target --start "$R/free_max4_agenda.csv" --time-limit 1200
check free_target --next-meeting M3 --max-per-member 6
# 5. The whole round planned from the start (nothing fixed).
run scratch --from-scratch --start "$R/free_target_agenda.csv" --time-limit 1800
check scratch --from-scratch --max-per-member 6
