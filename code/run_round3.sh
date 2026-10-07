#!/usr/bin/env bash
R=../data/tdf/results
U="--unavailable ../data/tdf/unavailable.csv --windows ../data/tdf/windows.csv --alpha-file ../data/tdf/alpha_high.csv"
echo "$(date +%H:%M) round3: start"
python -m models.panel_model ../data/tdf/panel.csv --next-meeting M3 --max-per-member 4 --fairness lexburden --meetings-slack 2 --time-limit 10800 $U --fewest-meetings R02 --out $R/round3 > $R/round3.log 2>&1
echo "$(date +%H:%M) round3: done"; grep -E '^objective|^burden' $R/round3.log
python -m models.check_agenda ../data/tdf/panel.csv $R/round3_agenda.csv --next-meeting M3 --max-per-member 4 $U | tail -1 | sed 's/^/round3 check: /'
echo ALLDONE3
