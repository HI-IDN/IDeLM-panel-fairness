#!/usr/bin/env bash
until grep -q ALLDONE2 ../data/tdf/results/run_round2.out; do sleep 60; done
./run_round3.sh > ../data/tdf/results/run_round3.out 2>&1
