#!/usr/bin/env bash
until grep -q ALLDONE6 ../data/tdf/results/run_round6.out; do sleep 60; done
mkdir -p ../data/tdf/results/book
RESULTS=../data/tdf/results/book MODEL_OPTIONS="--fairness lexburden --meetings-slack 2" ONLY="current free free_sum free_leximin free_noworse free_max4" bash run_panel_scenarios.sh > ../data/tdf/results/book/run_scenarios.out 2>&1
echo ALLDONE_SCEN >> ../data/tdf/results/book/run_scenarios.out
