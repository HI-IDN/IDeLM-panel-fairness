#!/usr/bin/env bash
# Run one round of the panel schedule model with the round's real constraints, then check the agenda.
# Run from code/.
#
#   ./run_round.sh <name> [start-name] [time-limit-seconds]
#
# Writes $R/<name>_agenda.csv etc. and $R/<name>.log (R = ../data/tdf/results). With start-name the run
# starts from $R/<start-name>_agenda.csv. Several rounds that depend on each other are chained in one
# call, so each waits for the one before it and stops if one fails:
#
#   ./run_round.sh r1 "" 600 && ./run_round.sh r2 r1 10800
#
# Environment: CLOSED (last closed meeting, default M3), MAXPER (hard cap, default 4),
# FEWEST (member who wants the fewest meetings, optional), MODEL_OPTIONS (extra model options).
set -eu
name=${1:?usage: run_round.sh <name> [start-name] [time-limit-seconds]}
start=${2:-}
limit=${3:-10800}
D=../data/tdf
R=${RESULTS:-$D/results}
CLOSED=${CLOSED:-M3}
MAXPER=${MAXPER:-4}
mkdir -p "$R"

OPTS="--fix-meetings M1 M2 M3 --fairness lexburden --meetings-slack 2 --max-per-member $MAXPER"
CHECK="--closed $CLOSED --max-per-member $MAXPER"
[ -f $D/unavailable.csv ] && { OPTS="$OPTS --unavailable $D/unavailable.csv"; CHECK="$CHECK --unavailable $D/unavailable.csv"; }
[ -f $D/windows.csv ] && { OPTS="$OPTS --windows $D/windows.csv"; CHECK="$CHECK --windows $D/windows.csv"; }
[ -f $D/alpha_tiers.csv ] && OPTS="$OPTS --alpha-file $D/alpha_tiers.csv"
[ -n "${FEWEST:-}" ] && OPTS="$OPTS --fewest-meetings $FEWEST"
[ -n "$start" ] && OPTS="$OPTS --start $R/${start}_agenda.csv"

echo "$(date +%H:%M) $name: start"
# shellcheck disable=SC2086  # the option strings are lists of options
python -m models.panel_model $D/panel.csv ${MODEL_OPTIONS:-} $OPTS --time-limit "$limit" --out "$R/$name" > "$R/$name.log" 2>&1
echo "$(date +%H:%M) $name: done"; grep -E '^objective|^burden|infeas' "$R/$name.log" || true
python -m models.check_agenda $D/panel.csv "$R/${name}_agenda.csv" $CHECK | tail -3 | sed "s/^/$name check: /"
