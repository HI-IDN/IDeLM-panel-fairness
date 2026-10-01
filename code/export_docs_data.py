"""
Copy what the book needs from the local model results into docs/data/, so the book can be rendered
on GitHub without Gurobi or the gitignored results.

Only whitelisted columns are copied, and only pseudonymised codes (R.., A.., M..) appear in them.
The Gurobi logs are never copied: they hold licence details. Solver time, gap and version are
summarised in solver.csv instead.

Run from code/ after run_panel_scenarios.sh:  python export_docs_data.py
"""
import csv
import glob
import os
import re

RESULTS = '../data/tdf/results'
OUT = '../docs/data'
SCENARIOS = ['current', 'free', 'free_max4', 'scratch', 'assign_schedule']

# File suffix -> columns to keep.
COLUMNS = {
    '_agenda.csv': ['meeting', 'position', 'application'],
    '_members.csv': ['member', 'proposals', 'meetings', 'leave_slots', 'waiting', 'waiting_per_meeting',
                     'waiting_per_proposal', 'alpha', 'burden', 'burden_per_proposal'],
    '_coi_present.csv': ['application', 'member', 'meeting'],
}
ROLE_FILES = {'roles_panel.csv': ['application', 'editor', 'reader1', 'reader2'],
              'assign_panel.csv': ['application', 'editor', 'reader1', 'reader2']}
CODE = re.compile(r'^([RAM]\d+|-?\d+(\.\d+)?|TRUE|FALSE|True|False|yes|no|)$', re.I)  # codes, numbers, flags


def copy(src, dst, columns):
    with open(src, newline='', encoding='utf-8-sig') as f:
        rows = [{c: row[c] for c in columns} for row in csv.DictReader(f)]
    for row in rows:
        for c, v in row.items():
            for part in v.split(';'):
                assert CODE.match(part), f'{src}: unexpected value in column {c}'
    with open(dst, 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=columns)
        writer.writeheader()
        writer.writerows(rows)


def solver_info(log_file):
    text = open(log_file, encoding='utf-8', errors='replace').read()
    version = re.search(r'Gurobi Optimizer version ([0-9.]+)', text)
    seconds = re.search(r'Explored .* in ([0-9.]+) seconds', text)
    gap = re.search(r'Best objective .*gap ([0-9.]+)%', text)
    return {'version': version.group(1) if version else '',
            'minutes': round(float(seconds.group(1)) / 60, 1) if seconds else '',
            'gap': round(float(gap.group(1)), 1) if gap else ''}


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
    with open(os.path.join(OUT, 'solver.csv'), 'w', newline='', encoding='utf-8') as f:
        writer = csv.DictWriter(f, fieldnames=['scenario', 'version', 'minutes', 'gap'])
        writer.writeheader()
        writer.writerows(solver)
    print(f'{len(os.listdir(OUT))} files in {OUT}')


if __name__ == '__main__':
    main()
