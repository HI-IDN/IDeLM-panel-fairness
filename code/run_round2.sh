#!/usr/bin/env bash
R=../data/tdf/results
U="--unavailable ../data/tdf/unavailable.csv --windows ../data/tdf/windows.csv"
echo "$(date +%H:%M) round2: start"
python -m models.panel_model ../data/tdf/panel.csv --next-meeting M3 --fairness lexburden --meetings-slack 2 --time-limit 10800 $U --fewest-meetings R02 --out $R/round2 > $R/round2.log 2>&1
echo "$(date +%H:%M) round2: done"; grep -E '^objective' $R/round2.log
python -m models.check_agenda ../data/tdf/panel.csv $R/round2_agenda.csv --next-meeting M3 --max-per-member 5 $U | tail -1 | sed 's/^/round2 check: /'
echo "$(date +%H:%M) scratch2: start"
python -m models.panel_model ../data/tdf/panel.csv --from-scratch --fairness lexburden --meetings-slack 2 --time-limit 10800 $U --fewest-meetings R02 --out $R/round2_scratch > $R/round2_scratch.log 2>&1
echo "$(date +%H:%M) scratch2: done"; grep -E '^objective' $R/round2_scratch.log
python -m models.check_agenda ../data/tdf/panel.csv $R/round2_scratch_agenda.csv --from-scratch --max-per-member 5 --first-meeting-rule $U | tail -1 | sed 's/^/scratch2 check: /'
echo ALLDONE2
