#!/usr/bin/env bash
until grep -q ALLDONE ../data/tdf/results/run_round.out; do sleep 60; done
./run_round2.sh > ../data/tdf/results/run_round2.out 2>&1
