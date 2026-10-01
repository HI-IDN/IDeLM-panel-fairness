"""
Check a model agenda against the rules of the scenarios.

    * held meetings (with a known agenda) are exactly as they happened;
    * closed meetings contain exactly the proposals of the staff's plan;
    * every proposal with reviewers is on the agenda once, without gaps in any meeting;
    * no member has more than the allowed number of own proposals in an open meeting;
    * open meetings respect the meeting size limit, if one is given;
    * with --keep-meetings, every proposal is in its meeting of the staff's plan;
    * with --first-meeting-rule, everyone has exactly one proposal in the first meeting (when it was
      still open).

It also reports, without counting them as problems: conflicted members present when the proposal
is discussed (a soft rule in the model), and the fairness measures of the agenda, recomputed from
the agenda alone (models.panel_model.member_measures and fairness_metrics).

Usage (from code/):
    python -m models.check_agenda ../data/tdf/panel.csv ../data/tdf/results/free_agenda.csv \
        --closed M3 --max-per-member 6
"""
import argparse
import csv
import sys
from collections import Counter, defaultdict

from models.panel_model import fairness_metrics, member_measures, read_panel


def check(data, agenda, closed=(), max_per_member=None, meeting_size=None, next_meeting=None,
          max_two_meetings=None, min_per_member=None, keep_meetings=False, first_meeting_rule=False):
    """Return a list of problems (empty if the agenda follows the rules)."""
    problems = []
    if keep_meetings:
        for p, m, _ in agenda:
            if data.current.get(p) and data.current[p] != m:
                problems.append(f'{p} moved from {data.current[p]} to {m}')
    placed = Counter(p for p, _, _ in agenda)
    for p in data.reviewers:
        if placed[p] != 1:
            problems.append(f'{p} is on the agenda {placed[p]} times')
    by_meeting = defaultdict(list)
    for p, m, k in agenda:
        by_meeting[m].append((k, p))
    for m, items in by_meeting.items():
        slots = sorted(k for k, _ in items)
        if slots != list(range(1, len(slots) + 1)):
            problems.append(f'{m} has gaps or duplicate slots: {slots}')
    for p, k in data.fixed_position.items():
        m = data.fixed_meeting[p]
        if (k, p) not in by_meeting[m]:
            problems.append(f'held proposal {p} is not at {m} slot {k}')
    for m in closed:
        planned = {p for p, cm in data.current.items() if cm == m}
        actual = {p for _, p in by_meeting[m]}
        if planned != actual:
            problems.append(f'closed {m} differs from the plan: extra {sorted(actual - planned)}, '
                            f'missing {sorted(planned - actual)}')
    if next_meeting:  # nothing added to the next meeting; planned proposals may be postponed
        planned = {p for p, cm in data.current.items() if cm == next_meeting}
        added = {p for _, p in by_meeting[next_meeting]} - planned
        if added:
            problems.append(f'proposals added to {next_meeting}: {sorted(added)}')
    held = {data.fixed_meeting[p] for p in data.fixed_position}
    if first_meeting_rule and data.meetings and data.meetings[0] not in held | set(closed):
        first = data.meetings[0]
        own = Counter(r for _, p in by_meeting[first] for r in data.reviewers[p])
        for r in data.members:
            if own[r] != 1:
                problems.append(f'{r} has {own[r]} proposals in the first meeting {first} (rule: exactly 1)')
    if max_two_meetings:
        order = sorted(by_meeting, key=lambda m: int(m[1:]))
        for m, nxt in zip(order, order[1:]):
            if m in held and nxt in held:
                continue
            own = Counter(r for _, p in by_meeting[m] + by_meeting[nxt] for r in data.reviewers[p])
            for r, n in own.items():
                if n > max_two_meetings:
                    problems.append(f'{r} has {n} proposals in {m}+{nxt} (limit {max_two_meetings})')
    for m, items in by_meeting.items():
        if m in held or m in closed:
            continue
        if meeting_size and len(items) > meeting_size:
            problems.append(f'{m} has {len(items)} proposals (limit {meeting_size})')
        if max_per_member:
            own = Counter(r for _, p in items for r in data.reviewers[p])
            for r, n in own.items():
                if n > max_per_member:
                    problems.append(f'{r} has {n} proposals in {m} (limit {max_per_member})')
    if min_per_member:  # the first and the next meeting are exempt, as in the model
        first = min(by_meeting, key=lambda m: int(m[1:]))
        for m, items in by_meeting.items():
            if m in held or m in closed or m in (first, next_meeting):
                continue
            own = Counter(r for _, p in items for r in data.reviewers[p])
            for r, n in own.items():
                if n < min_per_member:
                    problems.append(f'{r} has {n} proposals in {m} (at least {min_per_member})')
    return problems


def conflicts_present(data, agenda):
    """(proposal, member, meeting) where a member with a conflict of interest is still in the
    meeting when the proposal comes up, i.e. has an own proposal later in it."""
    leave = Counter()
    for p, m, k in agenda:
        for r in data.reviewers.get(p, ()):
            leave[r, m] = max(leave[r, m], k)
    return [(p, r, m) for p, m, k in agenda for r in data.coi.get(p, []) if leave[r, m] > k]


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('panel')
    parser.add_argument('agenda')
    parser.add_argument('--closed', nargs='*', default=[])
    parser.add_argument('--max-per-member', type=int)
    parser.add_argument('--meeting-size', type=int)
    parser.add_argument('--from-scratch', action='store_true', help='held meetings were not fixed')
    parser.add_argument('--next-meeting', help='next meeting: nothing may be added to it')
    parser.add_argument('--max-two-meetings', type=int)
    parser.add_argument('--min-per-member', type=int, help='least own proposals in a meeting a member attends')
    parser.add_argument('--keep-meetings', action='store_true', help='every proposal stays in its planned meeting')
    parser.add_argument('--first-meeting-rule', action='store_true',
                        help='everyone has exactly one proposal in the first meeting')
    parser.add_argument('--alpha', type=float, default=2.0, help='cost of a meeting in the fairness measures')
    args = parser.parse_args()

    data = read_panel(args.panel)
    if args.from_scratch:
        data.fixed_meeting, data.fixed_position = {}, {}
    with open(args.agenda, newline='', encoding='utf-8') as f:
        agenda = [(row['application'], row['meeting'], int(row['position'])) for row in csv.DictReader(f)]
    problems = check(data, agenda, args.closed, args.max_per_member, args.meeting_size, args.next_meeting,
                     args.max_two_meetings, args.min_per_member, args.keep_meetings, args.first_meeting_rule)
    meetings = Counter(m for _, m, _ in agenda)
    print(f'{len(agenda)} proposals in {len(meetings)} meetings: '
          + ', '.join(f'{m}={n}' for m, n in sorted(meetings.items(), key=lambda kv: int(kv[0][1:]))))
    present = conflicts_present(data, agenda)
    print(f'conflicted members present: {len(present)}'
          + (' (' + ', '.join(f'{r} at {p} in {m}' for p, r, m in present) + ')' if present else ''))
    by_proposal = {p: (m, k) for p, m, k in agenda}
    for metric, value in fairness_metrics(member_measures(data, by_proposal, args.alpha)).items():
        print(f'{metric}: {value}')
    for problem in problems:
        print('PROBLEM:', problem)
    print('OK' if not problems else f'{len(problems)} problems')
    sys.exit(1 if problems else 0)


if __name__ == '__main__':
    main()
