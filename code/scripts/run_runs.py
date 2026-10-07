"""Run the runs of scripts/runs.yml: the schedule model, then models/check_agenda.py on its agenda.

Run from code/:  python scripts/run_runs.py [--list] [--dry-run] [--results DIR] <run> [<run> ...]
Runs are made one after the other and the chain stops at the first that fails. A run's `start` run is
not made automatically: name the runs in order.
"""
import argparse
import datetime
import os
import re
import subprocess
import sys

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))


def now():
    return datetime.datetime.now().strftime('%H:%M')


def build(name, cfg, results_dir):
    d, run = cfg['defaults'], cfg['runs'][name]
    results = results_dir or d['results']
    model = run.get('model', 'panel_model')
    model_opts = list(d.get('options', [])) + list(run.get('options', []))
    check_opts = list(run.get('check', []))
    for key in run.get('files', []):
        f = cfg['files'][key]
        if not os.path.exists(f['path']):
            print(f'  warning: {f["path"]} not found, left out of {name}', file=sys.stderr)
            continue
        model_opts += [f['model'], f['path']]
        if 'check' in f:
            check_opts += [f['check'], f['path']]
    if run.get('start'):
        model_opts += ['--start', f'{results}/{run["start"]}_agenda.csv']
    limit = run.get('time_limit', d.get('time_limit'))
    cmd = [sys.executable, '-m', f'models.{model}', d['panel']] + [str(o) for o in model_opts]
    cmd += ['--time-limit', str(limit), '--out', f'{results}/{name}']
    check = [sys.executable, '-m', 'models.check_agenda', d['panel'], f'{results}/{name}_agenda.csv']
    check += [str(o) for o in check_opts]
    return cmd, check, f'{results}/{name}.log', model


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('runs', nargs='*')
    ap.add_argument('--list', action='store_true', help='list the runs with their notes')
    ap.add_argument('--dry-run', action='store_true', help='print the commands only')
    ap.add_argument('--results', help='results folder (default from runs.yml)')
    ap.add_argument('--config', default=os.path.join(HERE, 'runs.yml'))
    args = ap.parse_args()
    with open(args.config, encoding='utf-8') as f:
        cfg = yaml.safe_load(f)
    if args.list:
        for n, r in cfg['runs'].items():
            print(f'{n:16} start={r.get("start", "-"):8} {r.get("note", "")}')
        return
    unknown = [n for n in args.runs if n not in cfg['runs']]
    if unknown or not args.runs:
        sys.exit(f'unknown or no run: {unknown}; see --list')
    for name in args.runs:
        cmd, check, log, model = build(name, cfg, args.results)
        if args.dry_run:
            print(' '.join(cmd), '>', log)
            if model == 'panel_model':
                print(' '.join(check))
            continue
        os.makedirs(os.path.dirname(log), exist_ok=True)
        print(f'{now()} {name}: start', flush=True)
        with open(log, 'w', encoding='utf-8') as lf:
            rc = subprocess.run(cmd, stdout=lf, stderr=subprocess.STDOUT).returncode
        if rc:
            sys.exit(f'{now()} {name}: FAILED (see {log})')
        with open(log, encoding='utf-8', errors='replace') as lf:
            keep = [ln.rstrip() for ln in lf if re.match(r'(objective|burden|.*infeas)', ln)]
        print(f'{now()} {name}: done', *keep, sep='\n  ', flush=True)
        if model == 'panel_model':
            out = subprocess.run(check, capture_output=True, text=True).stdout.strip().splitlines()
            for line in out[-3:]:
                print(f'  {name} check: {line}')


if __name__ == '__main__':
    main()
