#!/usr/bin/env bash
# Run all review-panel scenarios of the book (docs/scenarios.qmd and docs/assign.qmd). Run from code/.
# Each scenario writes <name>_agenda.csv, <name>_members.csv, <name>_coi_present.csv,
# <name>_fairness.csv (fairness measures), <name>_levels.csv (value, bound and gap of each step) and a log to
# ../data/tdf/results/. Each scenario starts from the solution of the one before (--start).
#
# Optional environment variables, e.g. to try another objective without touching the book's results:
#   RESULTS        results folder (default ../data/tdf/results)
#   MODEL_OPTIONS  extra options for every model run, e.g. "--fairness lex --postpone-penalty 3"
#   ONLY           scenario names to run, e.g. "current free" (default: all)
#   PANEL          panel file for a run (default ../data/tdf/panel.csv); set per run below
set -u
P=../data/tdf/panel.csv
R=${RESULTS:-../data/tdf/results}
mkdir -p "$R"

wanted() { [ -z "${ONLY:-}" ] || [[ " $ONLY " == *" $1 "* ]]; }

run() {  # run <name> <model options...>
  local name=$1; shift
  wanted "$name" || return 0
  echo "$(date +%H:%M) $name: start"
  # MODEL_OPTIONS come first, so options given for one run below take precedence.
  # shellcheck disable=SC2086  # MODEL_OPTIONS is a list of options
  if python -m models.panel_model "${PANEL:-$P}" ${MODEL_OPTIONS:-} "$@" --out "$R/$name" > "$R/$name.log" 2>&1; then
    echo "$(date +%H:%M) $name: $(grep -E '^objective' "$R/$name.log")"
  else
    echo "$(date +%H:%M) $name: FAILED (see $R/$name.log)"
  fi
}

check() {  # check <name> <check options...>: the agenda follows the rules of its scenario
  local name=$1; shift
  wanted "$name" || return 0
  python -m models.check_agenda "${PANEL:-$P}" "$R/${name}_agenda.csv" "$@" | tail -1 | sed "s/^/  $name check: /"
}

roles() {  # roles <name> <role model options...>: reviewers and roles (models/role_model.py)
  local name=$1; shift
  wanted "$name" || return 0
  echo "$(date +%H:%M) $name: start"
  if python -m models.role_model "${PANEL:-$P}" "$@" --out "$R/$name" > "$R/$name.log" 2>&1; then
    echo "$(date +%H:%M) $name: $(grep -E '^objective' "$R/$name.log")"
  else
    echo "$(date +%H:%M) $name: FAILED (see $R/$name.log)"
  fi
}

# Own proposals per meeting: at most 5 in meetings not yet held (panel_model.yml). Scenario 1 keeps
# the staff's meetings, which have up to 6, so it is checked against 6.
# 1. The staff's meetings, fair order within each meeting.
run current --keep-meetings --fix-meetings M3 --time-limit 300
check current --closed M3 --max-per-member 6 --keep-meetings
# 2. Next meeting (M3) fixed, later meetings re-optimised.
run free --next-meeting M3 --start "$R/current_agenda.csv" --time-limit 1200
check free --next-meeting M3 --max-per-member 5
# 2 for comparison: no fairness step, the fewest meetings and then the least total waiting.
run free_sum --next-meeting M3 --fairness lexsum --start "$R/free_agenda.csv" --time-limit 1200
check free_sum --next-meeting M3 --max-per-member 5
# 2 with leximin of the burden instead of only the worst-off member, and with a first step that
# keeps every member at most as burdened as in scenario 1 (the staff's meetings) where possible.
run free_leximin --next-meeting M3 --fairness leximin --start "$R/free_agenda.csv" --time-limit 1200
check free_leximin --next-meeting M3 --max-per-member 5
run free_noworse --next-meeting M3 --fairness leximin --no-worse-than "$R/current_agenda.csv" \
  --start "$R/free_leximin_agenda.csv" --time-limit 1200
check free_noworse --next-meeting M3 --max-per-member 5
# 3. As 2, at most 4 own proposals per meeting.
run free_max4 --next-meeting M3 --max-per-member 4 --start "$R/free_agenda.csv" --time-limit 1200
check free_max4 --next-meeting M3 --max-per-member 4
# 4. The whole round planned from the start (nothing fixed).
run scratch --from-scratch --start "$R/free_max4_agenda.csv" --time-limit 1800
check scratch --from-scratch --max-per-member 5
# Chapter 6: who of the three is editor, on the staff's reviewers. Equal pay per proposal on the
# staff's meetings, and pay per slot sat through (which rewards waiting) on those and on scenario 2.
roles roles --mode roles --agenda "$R/current_agenda.csv" --time-limit 300
roles roles_presence --mode roles --pay-per presence --agenda "$R/current_agenda.csv" --time-limit 300
roles roles_presence_free --mode roles --pay-per presence --agenda "$R/free_agenda.csv" --time-limit 300
# Chapter 7: everyone can review every proposal. Reviewers and roles from scratch (at most two
# new members on a proposal), then meetings and order from scratch for that assignment, with new
# members editing only from the middle of the round.
roles assign --mode assign --from-scratch --agenda "$R/current_agenda.csv" --time-limit 300
PANEL="$R/assign_panel.csv" run assign_schedule --from-scratch --new-editor-from M5   --start "$R/assign_start_agenda.csv" --time-limit 1800
PANEL="$R/assign_panel.csv" check assign_schedule --from-scratch --max-per-member 5 --new-editor-from M5
