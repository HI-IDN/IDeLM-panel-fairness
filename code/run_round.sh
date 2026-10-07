#!/usr/bin/env bash
R=../data/tdf/results
U="--unavailable ../data/tdf/unavailable.csv --windows ../data/tdf/windows.csv"
echo "$(date +%H:%M) round: start"
python -m models.panel_model ../data/tdf/panel.csv --next-meeting M3 --fairness lexburden --meetings-slack 2 --time-limit 10800 $U --fewest-meetings R02 --out $R/round > $R/round.log 2>&1
echo "$(date +%H:%M) round: done"; grep -E '^objective' $R/round.log
python -m models.check_agenda ../data/tdf/panel.csv $R/round_agenda.csv --next-meeting M3 --max-per-member 5 $U | tail -1 | sed 's/^/round check: /'
echo "$(date +%H:%M) scratch: start"
python -m models.panel_model ../data/tdf/panel.csv --from-scratch --fairness lexburden --meetings-slack 2 --time-limit 10800 $U --fewest-meetings R02 --out $R/round_scratch > $R/round_scratch.log 2>&1
echo "$(date +%H:%M) scratch: done"; grep -E '^objective' $R/round_scratch.log
python -m models.check_agenda ../data/tdf/panel.csv $R/round_scratch_agenda.csv --from-scratch --max-per-member 5 --first-meeting-rule $U | tail -1 | sed 's/^/scratch check: /'
echo ALLDONE
