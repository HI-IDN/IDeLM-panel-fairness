"""
One absence per member for the robustness runs (issue #8): each member is absent from the open
meeting (after the next one) where they have the most own proposals in the base plan. Writes
<out>/absent_<member>.csv (member, meeting) for --unavailable.
Run from code/:  python absences.py <panel> <base agenda> <next meeting> <out folder>
"""
import csv
import os
import sys
from collections import Counter

panel, agenda, next_meeting, out = sys.argv[1:5]
reviewers = {}
with open(panel, newline='', encoding='utf-8-sig') as f:
    for row in csv.DictReader(f):
        reviewers[row['application']] = [r for r in (row['editor'], row['reader1'], row['reader2']) if r]
with open(agenda, newline='', encoding='utf-8-sig') as f:
    placed = {row['application']: row['meeting'] for row in csv.DictReader(f)}
order = lambda m: int(m[1:])
later = {m for m in placed.values() if order(m) > order(next_meeting)}
own = Counter((r, m) for p, m in placed.items() if m in later for r in reviewers[p])
os.makedirs(out, exist_ok=True)
for r in sorted({r for trio in reviewers.values() for r in trio}, key=lambda r: int(r[1:])):
    counts = [(n, -order(m), m) for (s, m), n in own.items() if s == r]
    if not counts:
        continue
    m = max(counts)[2]
    with open(os.path.join(out, f'absent_{r}.csv'), 'w', newline='', encoding='utf-8') as f:
        f.write(f'member,meeting\n{r},{m}\n')
    print(r, m, max(counts)[0])
