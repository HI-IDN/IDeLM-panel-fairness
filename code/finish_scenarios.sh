#!/usr/bin/env bash
until grep -q ALLDONE_SCEN ../data/tdf/results/book/run_scenarios.out; do sleep 60; done
cat ../data/tdf/results/book/run_scenarios.out | grep -E "start|check|objective|FAILED"
PYTHONIOENCODING=utf-8 python export_docs_data.py --results ../data/tdf/results/book 2>&1 | tail -15
D=/c/Users/hbi3/Documents/IDeLM-panel-fairness/data/tdf
cp $D/results/fundaaetlun_taeknithrounarsjodur_haust2026.xlsx $D/results/fundaaetlun_taeknithrounarsjodur_haust2026_round5.xlsx 2>&1 | tail -1
PYTHONIOENCODING=utf-8 python export_plan_xlsx.py --agenda ../data/tdf/results/round6_agenda.csv --members ../data/tdf/results/round6_members.csv --key $D/panel_key.csv --raw $D/TDF2026.csv --out $D/results/fundaaetlun_taeknithrounarsjodur_haust2026.xlsx 2>&1 | tail -3
echo FINISHED
