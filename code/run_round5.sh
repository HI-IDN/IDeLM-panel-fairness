#!/usr/bin/env bash
# M3 is tomorrow: its proposals are fixed to the staff plan (order free); M4-M9 optimised.
R=../data/tdf/results
U="--unavailable ../data/tdf/unavailable.csv --windows ../data/tdf/windows.csv --alpha-file ../data/tdf/alpha_tiers.csv --fix-meetings M1 M2 M3 --max-per-member 4 --fairness lexburden --meetings-slack 2 --fewest-meetings R02"
chk() { python -m models.check_agenda ../data/tdf/panel.csv $R/$1_agenda.csv --closed M3 --max-per-member 4 --unavailable ../data/tdf/unavailable.csv --windows ../data/tdf/windows.csv | tail -3 | sed "s/^/$1 check: /"; }
echo "$(date +%H:%M) round5a: start"
python -m models.panel_model ../data/tdf/panel.csv $U --time-limit 600 --out $R/round5a > $R/round5a.log 2>&1
echo "$(date +%H:%M) round5a: done"; grep -E '^objective|^burden|infeas' $R/round5a.log; chk round5a
echo ALLDONE5A
echo "$(date +%H:%M) round5: start"
python -m models.panel_model ../data/tdf/panel.csv $U --time-limit 10800 --start $R/round5a_agenda.csv --out $R/round5 > $R/round5.log 2>&1
echo "$(date +%H:%M) round5: done"; grep -E '^objective|^burden' $R/round5.log; chk round5
echo ALLDONE5
