#!/usr/bin/env bash
# Rotation rule (--rotate-wait) on the best scenario-2 plan, for docs/data/experiments/
# (export_docs_data.py, EXPERIMENTS) and issue #7. Run from code/ after run_panel_scenarios.sh,
# which writes current_agenda.csv (the staff's meetings) and free_noworse_agenda.csv (scenario 2d).
#
# The base is scenario 2d (leximin after a step that keeps every member at most as burdened as in
# the staff's plan) with slack 2 on the meetings step, improved in turn from 2d's 20-minute plan:
# 1 hour as 2d, 1 hour with the slack, then 3 more hours. The rule is then added, 60 minutes each
# from that plan: the members of the last proposal of a meeting skip the next meeting (-1), or wait
# at most 0, 1 or 2 proposals of others there.
set -u
P=../data/tdf/panel.csv; R=${RESULTS:-../data/tdf/results}; L=$R/long
mkdir -p "$L"
NW=(--next-meeting M3 --fairness leximin --no-worse-than "$R/current_agenda.csv")

run() {  # run <name> <model options...>
  local name=$1; shift
  echo "$(date +%H:%M) $name: start"
  python -m models.panel_model $P "${NW[@]}" "$@" --out "$L/$name" > "$L/$name.log" 2>&1
  echo "$(date +%H:%M) $name: $(grep -E '^objective' "$L/$name.log")"
  python -m models.check_agenda $P "$L/${name}_agenda.csv" --next-meeting M3 --max-per-member 5 | tail -1
}
run free_noworse --start "$R/free_noworse_agenda.csv" --time-limit 3600
run free_noworse_slack2 --meetings-slack 2 --start "$L/free_noworse_agenda.csv" --time-limit 3600
run best_long --meetings-slack 2 --start "$L/free_noworse_slack2_agenda.csv" --time-limit 10800
for v in skip:-1 wait0:0 wait1:1 wait2:2; do
  run best_${v%%:*} --meetings-slack 2 --rotate-wait "${v#*:}" --start "$L/best_long_agenda.csv" --time-limit 3600
done
