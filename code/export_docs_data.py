"""
Copy what the book needs from the local model results into docs/data/, so the book can be rendered
on GitHub without Gurobi or the gitignored results.

Only whitelisted columns are copied, and only pseudonymised codes (R.., A.., M..) appear in them.
The Gurobi logs are never copied: they hold licence details. Solver time, time limit, gap and
version are summarised in solver.csv instead, and progress.csv keeps only the numbers of the
solver's progress lines (time, best solution, best bound, gap) for each step.

Experiments the book refers to (EXPERIMENTS below) go to docs/data/experiments/, with their own
solver.csv, so their numbers are computed in the book rather than typed in.

Run from code/ after run_panel_scenarios.sh:  python export_docs_data.py
"""
import csv
import glob
import os
import re

RESULTS = '../data/tdf/results'
OUT = '../docs/data'
SCENARIOS = ['current', 'free', 'free_sum', 'free_leximin', 'free_noworse', 'free_max4', 'scratch', 'assign_schedule']

# File suffix -> columns to keep.
COLUMNS = {
    '_agenda.csv': ['meeting', 'position', 'application'],
    '_members.csv': ['member', 'proposals', 'meetings', 'leave_slots', 'waiting', 'waiting_per_meeting',
                     'waiting_per_proposal', 'alpha', 'burden', 'burden_per_proposal'],
    '_coi_present.csv': ['application', 'member', 'meeting'],
    '_levels.csv': ['level', 'value', 'objective', 'bound', 'gap'],
}
# Experiments the book refers to: name in docs/data/experiments/ -> results prefix (in RESULTS).
EXPERIMENTS = {
    # Rotation rule on scenario 2, 60 minutes each from the same start: without the rule, the
    # members of the last proposal skip the next meeting, or wait at most 2 there.
    'rotation_none': 'final_long/free',
    'rotation_skip': 'rotation/free_skip',
    'rotation_wait2': 'rotation/free_wait2',
}
ROLE_FILES = {'roles_panel.csv': ['application', 'editor', 'reader1', 'reader2'],
              'assign_panel.csv': ['application', 'editor', 'reader1', 'reader2']}
CODE = re.compile(r'^([RAM]\d+|-?\d+(\.\d+)?([eE][-+]?\d+)?|TRUE|FALSE|True|False|yes|no|)$', re.I)  # codes, numbers, flags
LEVEL = re.compile(r'^(rules|reference|meetings|equity|worst|top\d+|waiting)$')  # step names of the model


def copy(src, dst, columns):
    with open(src, newline='', encoding='utf-8-sig') as f:
        rows = [{c: row[c] for c in columns} for row in csv.DictReader(f)]
    for row in rows:
        for c, v in row.items():
            for part in v.split(';'):
                assert CODE.match(part) or (c == 'level' and LEVEL.match(part)), \
                    f'{src}: unexpected value in column {c}'
    with open(dst, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def solver_info(log_file):
    """Gurobi version, total solve time over all steps, and the gap of the last step (the model's
    own summary line when there is one, as a stepwise solve has one Gurobi run per step)."""
    text = open(log_file, encoding='utf-8', errors='replace').read()
    version = re.search(r'Gurobi Optimizer version ([0-9.]+)', text)
    seconds = [float(s) for s in re.findall(r'Explored .* in ([0-9.]+) seconds', text)]
    gap = (re.findall(r'(?m)^objective .*gap ([0-9.]+)%', text)
           or re.findall(r'Best objective .*gap ([0-9.]+)%', text))
    # The first time limit set is the whole run's; a stepwise solve then sets a share for each step.
    limit = re.search(r'Set parameter TimeLimit to value ([0-9.e+]+)', text)
    return {'version': version.group(1) if version else '',
            'minutes': round(sum(seconds) / 60, 1) if seconds else '',
            'limit_minutes': round(float(limit.group(1)) / 60, 1) if limit else '',
            'gap': round(float(gap[-1]), 1) if gap else ''}


# A branch-and-bound progress line ends with: incumbent, best bound, gap %, iterations per node, time.
PROGRESS = re.compile(r'(-?[0-9.]+(?:e[-+]?\d+)?)\s+(-?[0-9.]+(?:e[-+]?\d+)?)\s+([0-9.]+)%\s+\S+\s+(\d+)s\s*$')
DONE = re.compile(r'Explored .* in ([0-9.]+) seconds')
FINAL = re.compile(r'Best objective (\S+), best bound (\S+), gap ([0-9.]+)%')
STEP = re.compile(r'^level (\w+):')


def solver_progress(log_file):
    """The solver's progress over time for each step of a run: one row per progress line, plus the
    final value of each step. Times are from the start of the run, over all steps."""
    rows, pending, offset, step = [], [], 0.0, 0
    for line in open(log_file, encoding='utf-8', errors='replace'):
        if m := PROGRESS.search(line):
            pending.append([offset + float(m.group(4)), m.group(1), m.group(2), m.group(3)])
        elif m := DONE.search(line):
            seconds = float(m.group(1))
        elif m := FINAL.search(line):
            pending.append([offset + seconds, m.group(1), m.group(2), m.group(3)])
            offset += seconds
            step += 1
        elif (m := STEP.match(line)) and LEVEL.match(m.group(1)):
            rows += [{'step': step, 'level': m.group(1), 'seconds': round(t, 1), 'incumbent': inc,
                      'bound': bound, 'gap': gap} for t, inc, bound, gap in pending]
            pending = []
    return rows


def main():
    os.makedirs(OUT, exist_ok=True)
    copy('../data/tdf/members.csv', os.path.join(OUT, 'members.csv'), ['member', 'new'])
    for s in SCENARIOS:
        for suffix, columns in COLUMNS.items():
            src = os.path.join(RESULTS, s + suffix)
            if os.path.exists(src):
                copy(src, os.path.join(OUT, s + suffix), columns)
    for name, columns in ROLE_FILES.items():
        if os.path.exists(os.path.join(RESULTS, name)):
            copy(os.path.join(RESULTS, name), os.path.join(OUT, name), columns)
    solver = [{'scenario': os.path.basename(f)[:-4], **solver_info(f)}
              for f in sorted(glob.glob(os.path.join(RESULTS, '*.log')))]
    write_solver(os.path.join(OUT, 'solver.csv'), solver)
    write_progress(os.path.join(OUT, 'progress.csv'),
                   [{'scenario': s, **row} for s in SCENARIOS if os.path.exists(os.path.join(RESULTS, s + '.log'))
                    for row in solver_progress(os.path.join(RESULTS, s + '.log'))])
    experiments = os.path.join(OUT, 'experiments')
    os.makedirs(experiments, exist_ok=True)
    solver = []
    for name, prefix in EXPERIMENTS.items():
        src = os.path.join(RESULTS, prefix)
        if not os.path.exists(src + '_members.csv'):
            continue
        for suffix in ('_members.csv', '_coi_present.csv'):
            copy(src + suffix, os.path.join(experiments, name + suffix), COLUMNS[suffix])
        if os.path.exists(src + '.log'):
            solver.append({'scenario': name, **solver_info(src + '.log')})
    write_solver(os.path.join(experiments, 'solver.csv'), solver)
    print(f'{len(os.listdir(OUT))} files in {OUT}, {len(os.listdir(experiments))} in {experiments}')


def write_solver(path, rows):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['scenario', 'version', 'minutes', 'limit_minutes', 'gap'])
        writer.writeheader()
        writer.writerows(rows)


def write_progress(path, rows):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['scenario', 'step', 'level', 'seconds', 'incumbent', 'bound', 'gap'])
        writer.writeheader()
        writer.writerows(rows)


if __name__ == '__main__':
    main()
