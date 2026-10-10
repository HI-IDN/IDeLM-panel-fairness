"""
Copy what the book needs from the local model results into docs/data/, so the book can be rendered
on GitHub without Gurobi or the gitignored results.

Each scenario is taken from its best run: results/<scenario> or a run of the same name in a
subfolder, such as a longer run in results/long/ (see best_run).

Only whitelisted columns are copied, and only pseudonymised codes (R.., A.., M..) appear in them.
The Gurobi logs are never copied: they hold licence details. Solver time, time limit, gap and
version are summarised in solver.csv instead, and progress.csv keeps only the numbers of the
solver's progress lines (time, best solution, best bound, gap) for each step.

Experiments the book refers to (EXPERIMENTS below) go to docs/data/experiments/, with their own
solver.csv, so their numbers are computed in the book rather than typed in.

The runs of the October 2026 round on the 110 proposals that are discussed (ROUNDS below) are copied as
scenarios s1, s2, s3, with their logs taken from ../data/tdf/logs/. With --rounds-only, only these are
copied and their rows replaced in solver.csv and progress.csv, leaving every other file as it is.

Run from code/ after scripts/run_panel_scenarios.sh:  python export_docs_data.py [--results <folder>] [--rounds-only]
"""
import argparse
import csv
import glob
import os
import re

RESULTS = '../data/tdf/results'
OUT = '../docs/data'
# Runs chosen by hand over the automatic pick of best_run, because their settings differ from the scenario's
# (so their steps cannot be compared): scenario -> (run in results, minutes spent on the runs it was
# started from). Used only when the run exists in the results folder.
#   free_noworse (2d): the 3 h run with --meetings-slack 2, started from the 1 h run (42.7 min) of 2d, itself
#   started from the first 2d run (17.3 min), started from the staff's plan (5.0 min); the slack run was 42.1 min.
CHOSEN = {'free_noworse': ('long/best_long', 5.0 + 17.3 + 42.7 + 42.1)}
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
# The October 2026 round on the 110 proposals that are discussed: scenario -> run in results (its log has the
# same name in LOGS). s1: the staff's plan with the meetings fixed and the order optimised; s2: M1-M4 fixed and
# M5-M9 free; s3: from scratch. A run is copied only once it has finished (its _members.csv exists).
LOGS = '../data/tdf/logs'
ROUNDS = {'s1': 'rounds_2026-10/scen110_1', 's2': 'rounds_2026-10/scen110_2', 's3': 'rounds_2026-10/scen110_3_whatif'}
ROLE_FILES = {'roles_panel.csv': ['application', 'editor', 'reader1', 'reader2'],
              'assign_panel.csv': ['application', 'editor', 'reader1', 'reader2']}
CODE = re.compile(r'^([RAM]\d+|-?\d+(\.\d+)?([eE][-+]?\d+)?|TRUE|FALSE|True|False|yes|no|)$', re.I)  # codes, numbers, flags
LEVEL = re.compile(r'^(priority|rules|reference|meetings|equity|worst|top\d+|waiting)$')  # step names of the model


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
    seconds = step_seconds(log_file)
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
LIMIT = re.compile(r'Set parameter TimeLimit to value ([0-9.e+]+)')


def step_seconds(log_file):
    """The solve time of each Gurobi run in a log. Gurobi counts wall-clock time, so a run during which
    the machine slept reports far more than its time limit: when the reported time exceeds the time of
    the run's last progress line by more than the run's time limit, that last progress time is used."""
    seconds, limit, last = [], None, None
    for line in open(log_file, encoding='utf-8', errors='replace'):
        if m := LIMIT.search(line):
            limit = float(m.group(1))
        elif m := PROGRESS.search(line):
            last = float(m.group(4))
        elif m := DONE.search(line):
            reported = float(m.group(1))
            asleep = last is not None and limit is not None and reported - last > limit
            seconds.append(last if asleep else reported)
            last = None
    return seconds


def solver_progress(log_file):
    """The solver's progress over time for each step of a run: one row per progress line, plus the
    final value of each step. Times are from the start of the run, over all steps."""
    rows, pending, offset, step = [], [], 0.0, 0
    solve_times = iter(step_seconds(log_file))
    for line in open(log_file, encoding='utf-8', errors='replace'):
        if m := PROGRESS.search(line):
            pending.append([offset + float(m.group(4)), m.group(1), m.group(2), m.group(3)])
        elif DONE.search(line):
            seconds = next(solve_times)
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
    chosen = {s: best_run(s) for s in SCENARIOS}
    for s, src in chosen.items():
        if src is None:
            continue
        print(f'{s}: {os.path.relpath(src, RESULTS)}')
        for suffix, columns in COLUMNS.items():
            if os.path.exists(src + suffix):
                copy(src + suffix, os.path.join(OUT, s + suffix), columns)
    for name, columns in ROLE_FILES.items():
        if os.path.exists(os.path.join(RESULTS, name)):
            copy(os.path.join(RESULTS, name), os.path.join(OUT, name), columns)
    # Each scenario's log is the chosen run's; other runs (roles, assignment) are taken as they are.
    logs = {os.path.basename(f)[:-4]: f for f in sorted(glob.glob(os.path.join(RESULTS, '*.log')))}
    logs.update({s: src + '.log' for s, src in chosen.items() if src and os.path.exists(src + '.log')})
    solver = [{'scenario': name, **solver_info(f)} for name, f in sorted(logs.items())]
    for row in solver:
        # Minutes spent on the runs this one was started from, when it is not the script's own chain.
        if row['scenario'] in CHOSEN and chosen[row['scenario']] == os.path.join(RESULTS, CHOSEN[row['scenario']][0]):
            row['prior_minutes'] = round(CHOSEN[row['scenario']][1], 1)
    write_solver(os.path.join(OUT, 'solver.csv'), solver)
    write_progress(os.path.join(OUT, 'progress.csv'),
                   [{'scenario': s, **row} for s in SCENARIOS if s in logs for row in solver_progress(logs[s])])
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
    export_rounds()
    print(f'{len(os.listdir(OUT))} files in {OUT}, {len(os.listdir(experiments))} in {experiments}')


def export_rounds():
    """Copy the finished runs of ROUNDS as their scenario names, and replace their rows in solver.csv and
    progress.csv (other rows are kept)."""
    solver, progress = [], []
    for s, run in ROUNDS.items():
        src, log = os.path.join(RESULTS, run), os.path.join(LOGS, run + '.log')
        if not os.path.exists(src + '_members.csv'):
            continue
        print(f'{s}: {run}')
        for suffix, columns in COLUMNS.items():
            if os.path.exists(src + suffix):
                copy(src + suffix, os.path.join(OUT, s + suffix), columns)
        if os.path.exists(log):
            solver.append({'scenario': s, **solver_info(log)})
            progress += [{'scenario': s, **row} for row in solver_progress(log)]
    done = {row['scenario'] for row in solver}
    write_solver(os.path.join(OUT, 'solver.csv'), keep_rows(os.path.join(OUT, 'solver.csv'), done) + solver)
    write_progress(os.path.join(OUT, 'progress.csv'), keep_rows(os.path.join(OUT, 'progress.csv'), done) + progress)


def keep_rows(path, scenarios):
    """The rows of an exported csv whose scenario is not among scenarios."""
    if not os.path.exists(path):
        return []
    with open(path, newline='', encoding='utf-8') as f:
        return [row for row in csv.DictReader(f) if row['scenario'] not in scenarios]


def best_run(scenario):
    """The best run of a scenario: results/<scenario> or a run of the same name in a subfolder of results
    (for example a longer run in results/long/). Runs are compared step by step on the values their
    stepwise objective reached (<run>_levels.csv), the way the model itself ranks solutions; only runs
    with the same steps are compared, and results/<scenario> is kept when no other run is comparable."""
    if scenario in CHOSEN and os.path.exists(os.path.join(RESULTS, CHOSEN[scenario][0] + '_members.csv')):
        return os.path.join(RESULTS, CHOSEN[scenario][0])
    runs = [os.path.join(RESULTS, scenario)] + sorted(
        p[:-len('_members.csv')] for p in glob.glob(os.path.join(RESULTS, '*', scenario + '_members.csv')))
    runs = [r for r in runs if os.path.exists(r + '_members.csv')]
    if not runs:
        return None

    def levels(run):
        if not os.path.exists(run + '_levels.csv'):
            return None
        with open(run + '_levels.csv', newline='', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
        # Rounded, as each step is held to its value within a small tolerance.
        return [r['level'] for r in rows], tuple(round(float(r['value']), 3) for r in rows)

    reached = {r: levels(r) for r in runs}
    default = runs[0] if runs[0] == os.path.join(RESULTS, scenario) else None
    steps = reached[default][0] if default and reached[default] else None
    comparable = [r for r in runs if reached[r] and (steps is None or reached[r][0] == steps)]
    if not comparable:
        return runs[0]
    return min(comparable, key=lambda r: reached[r][1])


def write_solver(path, rows):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['scenario', 'version', 'minutes', 'limit_minutes', 'gap', 'prior_minutes'])
        writer.writeheader()
        writer.writerows(rows)  # prior_minutes is blank unless set


def write_progress(path, rows):
    with open(path, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['scenario', 'step', 'level', 'seconds', 'incumbent', 'bound', 'gap'])
        writer.writeheader()
        writer.writerows(rows)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument('--results', default=RESULTS,
                        help='folder of the model results (default: %(default)s), e.g. a copy where long runs were made')
    parser.add_argument('--rounds-only', action='store_true',
                        help='copy only the runs of ROUNDS, leaving the other exported files as they are')
    args = parser.parse_args()
    RESULTS = args.results
    if args.rounds_only:
        export_rounds()
    else:
        main()
