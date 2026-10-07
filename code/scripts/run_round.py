"""Run the model runs listed in a round file, one after the other, and check each agenda.

    python scripts/run_round.py scripts/rounds/example.yml [--only NAME ...]

The runs go in the foreground in the order of the file, so a plain `nohup python scripts/run_round.py ... &`
or a terminal left open is all the waiting there is: each run prints "start", "done" and the
check's last line with the time. A failed run stops the round (later runs may start from it).
"""
import argparse
import os
import shlex
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import yaml


def stamp():
    return datetime.now().strftime('%H:%M')


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('round_file')
    ap.add_argument('--only', nargs='+', metavar='NAME', help='run only these runs')
    args = ap.parse_args()
    round_file = Path(args.round_file).resolve()
    os.chdir(Path(__file__).resolve().parent.parent)  # paths in the round file are relative to code/
    cfg = yaml.safe_load(round_file.read_text(encoding='utf-8'))
    panel, results = cfg['panel'], Path(cfg['results'])
    results.mkdir(parents=True, exist_ok=True)
    common = shlex.split(cfg.get('common', ''))
    for run in cfg['runs']:
        name = run['name']
        if args.only and name not in args.only:
            continue
        cmd = [sys.executable, '-m', 'models.panel_model', panel, *common, *shlex.split(run.get('options', ''))]
        if 'start' in run:
            cmd += ['--start', str(results / f"{run['start']}_agenda.csv")]
        if 'time_limit' in run:
            cmd += ['--time-limit', str(run['time_limit'])]
        cmd += ['--out', str(results / name)]
        print(f'{stamp()} {name}: start', flush=True)
        with open(results / f'{name}.log', 'w', encoding='utf-8') as log:
            if subprocess.run(cmd, stdout=log, stderr=subprocess.STDOUT, check=False).returncode:
                sys.exit(f'{stamp()} {name}: FAILED (see {results / name}.log)')
        print(f'{stamp()} {name}: done', flush=True)
        if 'check' in run:
            chk = [sys.executable, '-m', 'models.check_agenda', panel, str(results / f'{name}_agenda.csv'),
                   *common_check(common), *shlex.split(run['check'])]
            out = subprocess.run(chk, capture_output=True, text=True, check=False).stdout.strip().splitlines()
            print(f'{stamp()} {name} check: {out[-1] if out else "no output"}', flush=True)


def common_check(common):
    """The rules the checker also knows: absences and windows."""
    keep, i = [], 0
    while i < len(common):
        if common[i] in ('--unavailable', '--windows'):
            keep += common[i:i + 2]
            i += 2
        else:
            i += 1
    return keep


if __name__ == '__main__':
    main()
