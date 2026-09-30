"""
Parameter experiments for the review-panel schedule model, kept apart from the book.

Each experiment runs models/panel_model.py with its own options, writes its files to
../data/tdf/experiments/<name>/, and records its parameters and results in
../data/tdf/experiments/experiments.sqlite:

    experiments  one row per experiment: parameters, solver result and summary metrics
    members      one row per experiment and member: meetings, waiting, burden, ...
    agenda       one row per experiment and proposal: meeting and position

Experiments that are already in the database are skipped, so the script can be re-run to add new
ones. Run from code/:  python run_experiments.py
"""
import csv
import json
import os
import re
import sqlite3
import subprocess
import sys
from datetime import datetime

PANEL = '../data/tdf/panel.csv'
ROOT = '../data/tdf/experiments'
DB = os.path.join(ROOT, 'experiments.sqlite')
START = '../data/tdf/results/free_max4_agenda.csv'  # scenario 3: at most 4 per meeting

BASE = {'next_meeting': 'M3', 'max_per_member': 5, 'time_limit': 1200}

# alpha is the cost of attending a meeting, in proposals' worth of time: from almost nothing (1) to
# about half an average meeting (8). At most 7 own proposals in two consecutive meetings (3+4 or 5+2:
# a heavy meeting is followed by a light one) is a hard limit. A limit of 5 cannot hold for everyone
# (R11 and R15 have too many proposals left), so it is run once as a soft limit for comparison.
EXPERIMENTS = [
    {'name': f'alpha{a}_hard7', 'alpha': a, 'max_two_meetings': 7} for a in (1, 2, 4, 6, 8)
] + [
    {'name': 'alpha4_soft5', 'alpha': 4, 'pair_limit': 5, 'pair_weight': 1.0},
] + [
    # Fewest meetings first (a cost of 100 per meeting attended), 2-5 own proposals in each meeting a
    # member attends (the next meeting is exempt from the minimum), at most 7 in two consecutive
    # meetings. Fairness is then either the worst total waiting, not divided by anything, or (for
    # comparison) the worst burden per proposal. Nobody waits longer in total than the worst case of
    # the current plan (60, R11). One hour each, warm-started from alpha4_hard7.
    {'name': f'C100_min2_{fairness}', 'alpha': 4, 'max_two_meetings': 7, 'meeting_cost': 100,
     'min_per_member': 2, 'fairness': fairness, 'max_waiting': 60, 'time_limit': 3600,
     'start': os.path.join(ROOT, 'alpha4_hard7', 'run_agenda.csv')}
    for fairness in ('total', 'proposal')
] + [
    {'name': 'C100_min2_total_free', 'alpha': 4, 'meeting_cost': 100, 'min_per_member': 2,
     'fairness': 'total', 'max_waiting': 60, 'time_limit': 3600, 'start': os.path.join(ROOT, 'alpha4_hard7', 'run_agenda.csv')},
]

# A conflicted member who must step out and come back in is worse than was weighted above (1, about
# a fifth of a meeting attended): 10 each, and 5 for each proposal postponed from the next meeting.
# At most 8 in two consecutive meetings, a compromise between 7 and none (10). Two hours, started
# from C100_min2_total, which also satisfies the limit of 8.
EXPERIMENTS += [
    {'name': 'C100_min2_total_two8_coi10', 'alpha': 4, 'max_two_meetings': 8, 'meeting_cost': 100,
     'min_per_member': 2, 'fairness': 'total', 'max_waiting': 60, 'coi_penalty': 10,
     'postpone_penalty': 5, 'time_limit': 7200,
     'start': os.path.join(ROOT, 'C100_min2_total', 'run_agenda.csv')},
]

# Columns added after the first experiments ran: (name, type).
NEW_COLUMNS = [('meeting_cost', 'REAL'), ('min_per_member', 'INTEGER'), ('fairness', 'TEXT'),
               ('max_waiting', 'INTEGER'), ('coi_penalty', 'REAL'), ('postpone_penalty', 'REAL'),
               ('max_total_waiting', 'INTEGER'), ('max_waiting_per_meeting', 'REAL'),
               ('total_meetings', 'INTEGER')]


def setup_db(con):
    con.executescript('''
        CREATE TABLE IF NOT EXISTS experiments (
            name TEXT PRIMARY KEY, alpha REAL, max_per_member INTEGER, next_meeting TEXT,
            pair_limit INTEGER, pair_weight REAL, max_two_meetings INTEGER, time_limit REAL,
            objective REAL, gap REAL, runtime_s REAL, check_ok INTEGER, problems TEXT,
            worst_burden_per_proposal REAL, total_waiting INTEGER, max_waiting_per_proposal REAL,
            meetings_min INTEGER, meetings_max INTEGER, max_two_meeting_load INTEGER,
            coi_present INTEGER, postponed TEXT, options TEXT, started TEXT, finished TEXT);
        CREATE TABLE IF NOT EXISTS members (
            experiment TEXT, member TEXT, proposals INTEGER, meetings INTEGER, leave_slots INTEGER,
            waiting INTEGER, waiting_per_meeting REAL, waiting_per_proposal REAL, alpha REAL,
            burden REAL, burden_per_proposal REAL, PRIMARY KEY (experiment, member));
        CREATE TABLE IF NOT EXISTS agenda (
            experiment TEXT, meeting TEXT, position INTEGER, application TEXT,
            PRIMARY KEY (experiment, application));
    ''')
    have = {row[1] for row in con.execute('PRAGMA table_info(experiments)')}
    for column, kind in NEW_COLUMNS:
        if column not in have:
            con.execute(f'ALTER TABLE experiments ADD COLUMN {column} {kind}')


def command(exp, out):
    start = exp['start'] if os.path.exists(exp.get('start', '')) else START
    args = [sys.executable, '-m', 'models.panel_model', PANEL, '--out', out, '--start', start,
            '--next-meeting', BASE['next_meeting'], '--max-per-member', str(BASE['max_per_member']),
            '--time-limit', str(exp.get('time_limit', BASE['time_limit'])), '--alpha', str(exp['alpha'])]
    for key in ('meeting_cost', 'min_per_member', 'fairness', 'max_waiting', 'coi_penalty', 'postpone_penalty'):
        if key in exp:
            args += ['--' + key.replace('_', '-'), str(exp[key])]
    if 'pair_limit' in exp:
        args += ['--pair-limit', str(exp['pair_limit']), '--pair-weight', str(exp['pair_weight'])]
    if 'max_two_meetings' in exp:
        args += ['--max-two-meetings', str(exp['max_two_meetings'])]
    return args


def max_two_meeting_load(agenda_rows, reviewers):
    """Largest number of own proposals any member has in two consecutive meetings."""
    per = {}
    for row in agenda_rows:
        for r in reviewers.get(row['application'], ()):
            per[r, row['meeting']] = per.get((r, row['meeting']), 0) + 1
    meetings = sorted({row['meeting'] for row in agenda_rows}, key=lambda m: int(m[1:]))
    members = {r for r, _ in per}
    return max(per.get((r, m), 0) + per.get((r, n), 0) for r in members for m, n in zip(meetings, meetings[1:]))


def main():
    os.makedirs(ROOT, exist_ok=True)
    con = sqlite3.connect(DB)
    setup_db(con)
    done = {row[0] for row in con.execute('SELECT name FROM experiments')}
    with open(PANEL, newline='', encoding='utf-8-sig') as f:
        reviewers = {r['application']: [r[c] for c in ('editor', 'reader1', 'reader2') if r[c]]
                     for r in csv.DictReader(f)}

    for exp in EXPERIMENTS:
        if exp['name'] in done:
            print(f"{exp['name']}: already done")
            continue
        folder = os.path.join(ROOT, exp['name'])
        os.makedirs(folder, exist_ok=True)
        out = os.path.join(folder, 'run')
        started = datetime.now().isoformat(timespec='seconds')
        print(f"{started} {exp['name']}: start", flush=True)
        with open(os.path.join(folder, 'run.log'), 'w', encoding='utf-8') as log:
            result = subprocess.run(command(exp, out), stdout=log, stderr=subprocess.STDOUT)
        text = open(os.path.join(folder, 'run.log'), encoding='utf-8', errors='replace').read()
        if result.returncode != 0 or not os.path.exists(out + '_agenda.csv'):
            print(f"{exp['name']}: FAILED (see {folder}/run.log)", flush=True)
            continue

        check_args = [sys.executable, '-m', 'models.check_agenda', PANEL, out + '_agenda.csv',
                      '--next-meeting', BASE['next_meeting'], '--max-per-member', str(BASE['max_per_member'])]
        if 'max_two_meetings' in exp:
            check_args += ['--max-two-meetings', str(exp['max_two_meetings'])]
        if 'min_per_member' in exp:
            check_args += ['--min-per-member', str(exp['min_per_member'])]
        check = subprocess.run(check_args, capture_output=True, text=True)
        problems = [line for line in check.stdout.splitlines() if line.startswith('PROBLEM')]

        with open(out + '_members.csv', newline='', encoding='utf-8') as f:
            members = list(csv.DictReader(f))
        with open(out + '_agenda.csv', newline='', encoding='utf-8') as f:
            agenda = list(csv.DictReader(f))
        with open(out + '_coi_present.csv', newline='', encoding='utf-8') as f:
            coi = len(list(csv.DictReader(f)))
        runtime = float(re.search(r'in ([0-9.]+) seconds', text).group(1))
        objective, gap = map(float, re.search(r'Best objective ([0-9.e+-]+), best bound [0-9.e+-]+, gap ([0-9.]+)%',
                                               text).groups())
        postponed = re.search(r'postponed from the next meeting: (.*)', text)

        row = {
            'name': exp['name'], 'alpha': exp['alpha'], 'max_per_member': BASE['max_per_member'],
            'next_meeting': BASE['next_meeting'], 'pair_limit': exp.get('pair_limit'),
            'pair_weight': exp.get('pair_weight'), 'max_two_meetings': exp.get('max_two_meetings'),
            'time_limit': exp.get('time_limit', BASE['time_limit']), 'objective': objective, 'gap': gap,
            'runtime_s': runtime, 'check_ok': int(not problems), 'problems': '\n'.join(problems),
            'worst_burden_per_proposal': max(float(m['burden_per_proposal']) for m in members),
            'total_waiting': sum(int(m['waiting']) for m in members),
            'max_waiting_per_proposal': max(float(m['waiting_per_proposal']) for m in members),
            'meetings_min': min(int(m['meetings']) for m in members),
            'meetings_max': max(int(m['meetings']) for m in members),
            'max_two_meeting_load': max_two_meeting_load(agenda, reviewers), 'coi_present': coi,
            'postponed': postponed.group(1) if postponed else None, 'options': json.dumps({**BASE, **exp}),
            'started': started, 'finished': datetime.now().isoformat(timespec='seconds'),
            'meeting_cost': exp.get('meeting_cost', 0.0), 'min_per_member': exp.get('min_per_member'),
            'fairness': exp.get('fairness', 'proposal'), 'max_waiting': exp.get('max_waiting'),
            'coi_penalty': exp.get('coi_penalty', 1.0), 'postpone_penalty': exp.get('postpone_penalty', 0.5),
            'max_total_waiting': max(int(m['waiting']) for m in members),
            'max_waiting_per_meeting': max(float(m['waiting_per_meeting']) for m in members),
            'total_meetings': sum(int(m['meetings']) for m in members),
        }
        con.execute(f"INSERT INTO experiments ({','.join(row)}) VALUES ({','.join('?' * len(row))})",
                    tuple(row.values()))
        con.executemany('INSERT INTO members VALUES (?,?,?,?,?,?,?,?,?,?,?)', [
            (exp['name'], m['member'], m['proposals'], m['meetings'], m['leave_slots'], m['waiting'],
             m['waiting_per_meeting'], m['waiting_per_proposal'], m['alpha'], m['burden'],
             m['burden_per_proposal']) for m in members])
        con.executemany('INSERT INTO agenda VALUES (?,?,?,?)', [
            (exp['name'], a['meeting'], a['position'], a['application']) for a in agenda])
        con.commit()
        print(f"{exp['name']}: objective {objective:.3f}, gap {gap:.1f}%, check "
              f"{'OK' if not problems else f'{len(problems)} problems'}", flush=True)
    con.close()


if __name__ == '__main__':
    main()
