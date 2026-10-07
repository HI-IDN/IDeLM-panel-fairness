#!/usr/bin/env bash
R=../data/tdf/results
U="--unavailable ../data/tdf/unavailable.csv --windows ../data/tdf/windows.csv --alpha-file ../data/tdf/alpha_tiers.csv"
echo "$(date +%H:%M) round4: start"
python -m models.panel_model ../data/tdf/panel.csv --next-meeting M3 --max-per-member 4 --start $R/round3_agenda.csv --fairness lexburden --meetings-slack 2 --time-limit 10800 $U --fewest-meetings R02 --out $R/round4 > $R/round4.log 2>&1
echo "$(date +%H:%M) round4: done"; grep -E '^objective|^burden' $R/round4.log
python -m models.check_agenda ../data/tdf/panel.csv $R/round4_agenda.csv --next-meeting M3 --max-per-member 4 $U | tail -1 | sed 's/^/round4 check: /'
echo ALLDONE4
