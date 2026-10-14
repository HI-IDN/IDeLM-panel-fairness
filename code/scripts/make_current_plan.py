"""Build the panel file and the reference agenda of the plan as the funder has implemented it, plus new proposals.

    python scripts/make_current_plan.py ../data/tdf/panel.csv PLAN_AGENDA.csv NEW.csv --out ../data/tdf/results/rannis

PLAN_AGENDA.csv is the agenda of the implemented plan (columns application, meeting, position), e.g. a
scenario result; NEW.csv holds proposals that came after it (columns as in panel.csv: application, meeting,
coi, editor, reader1, reader2, ...), already pseudonymised, meeting = the meeting they were put on. Writes
  <out>_panel.csv   panel.csv with every proposal in its meeting of the plan (held meetings keep their
                    position), the new proposals in theirs
  <out>_agenda.csv  the plan as an agenda, new proposals last in their meeting in the order of NEW.csv:
                    the reference of --no-worse-than when the funder has not ordered them
  <out>_free.txt    the codes of the new proposals, for --free-proposals
Only codes are read and written.
"""
import argparse
import csv
from collections import defaultdict


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n\n')[0])
    ap.add_argument('panel')
    ap.add_argument('plan', help='agenda CSV of the implemented plan')
    ap.add_argument('new', help='CSV of the proposals that came later')
    ap.add_argument('--out', required=True, help='output prefix')
    args = ap.parse_args()
    with open(args.panel, newline='', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        fields, rows = reader.fieldnames, list(reader)
    with open(args.plan, newline='', encoding='utf-8-sig') as f:
        plan = {r['application']: (r['meeting'], int(r['position'])) for r in csv.DictReader(f)}
    with open(args.new, newline='', encoding='utf-8-sig') as f:
        new = list(csv.DictReader(f))
    known = {r['application'] for r in rows}
    if known != set(plan):
        raise SystemExit(f'plan and panel differ: {sorted(known ^ set(plan))}')
    if known & {r['application'] for r in new}:
        raise SystemExit('a new proposal already has a code in the panel')
    for r in rows:
        if r['position'] and plan[r['application']][0] != r['meeting']:
            raise SystemExit(f"{r['application']} was held in {r['meeting']} but the plan has it elsewhere")
        r['meeting'] = plan[r['application']][0]
    for r in new:
        r.setdefault('readers_alphabetical', '1')
        r.setdefault('readers_missing', '0')
        r['position'] = ''
    full = rows + [{k: r.get(k, '') for k in fields} for r in new]
    with open(f'{args.out}_panel.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.DictWriter(f, fieldnames=fields)
        w.writeheader()
        w.writerows(full)
    by_meeting = defaultdict(list)
    for p, (m, k) in plan.items():
        by_meeting[m].append((k, p))
    agenda = []
    for m in sorted(by_meeting, key=lambda x: int(x[1:])):
        agenda += [(p, m, i) for i, (_, p) in enumerate(sorted(by_meeting[m]), 1)]
    last = {m: len(by_meeting[m]) for m in by_meeting}
    for r in new:
        last[r['meeting']] = last.get(r['meeting'], 0) + 1
        agenda.append((r['application'], r['meeting'], last[r['meeting']]))
    with open(f'{args.out}_agenda.csv', 'w', newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['application', 'meeting', 'position'])
        w.writerows(agenda)
    with open(f'{args.out}_free.txt', 'w', encoding='utf-8') as f:
        f.write(' '.join(r['application'] for r in new) + '\n')
    print(f'{len(full)} proposals; free: {" ".join(r["application"] for r in new)}')


if __name__ == '__main__':
    main()
