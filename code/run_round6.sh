#!/usr/bin/env bash
R=../data/tdf/results
U="--unavailable ../data/tdf/unavailable.csv --windows ../data/tdf/windows.csv --alpha-file ../data/tdf/alpha_tiers.csv --fix-meetings M1 M2 M3 --max-per-member 4 --fairness lexburden --meetings-slack 2 --fewest-meetings R02"
echo "$(date +%H:%M) round6: start"
python -m models.panel_model ../data/tdf/panel.csv $U --time-limit 10800 --start $R/round5_agenda.csv --out $R/round6 > $R/round6.log 2>&1
echo "$(date +%H:%M) round6: done"; grep -E '^objective|^burden' $R/round6.log
python -m models.check_agenda ../data/tdf/panel.csv $R/round6_agenda.csv --closed M3 --max-per-member 4 --unavailable ../data/tdf/unavailable.csv --windows ../data/tdf/windows.csv | tail -1 | sed 's/^/round6 check: /'
echo ALLDONE6
