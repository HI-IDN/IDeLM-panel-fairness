"""
Order each meeting of an agenda exactly, keeping every proposal in its meeting.

With the meetings of an agenda fixed, ordering one meeting is a small problem: at most 15
proposals, so dynamic programming over the subsets already discussed (2^15 states) solves it
exactly in seconds. This tells how far a solution of the schedule model (models/panel_model.py) is
from the best order for its own meetings, and so how much of the solver's gap lies in the order and
how much in the choice of meetings.

For each meeting not yet held, two orders are computed:

    * best:  the fewest conflicted members present, then the least total waiting, with no member
             staying longer in that meeting than in the given agenda. Nobody's burden goes up, so
             the largest burden and the leximin vector can only improve, and the meetings attended
             don't change. This order is written to <prefix>_agenda.csv.
    * bound: the least total waiting for the meeting with nothing else held, a lower bound on the
             waiting of any order of these meetings.

Held meetings (proposals with a position in panel.csv) keep their order. Waiting is the same
measure as in member_measures: slots stayed up to one's last own proposal, minus one's own
proposals.

Usage (from code/):
    python -m models.order_meetings ../data/tdf/panel.csv ../data/tdf/results/free_agenda.csv \
        --out ../data/tdf/results/free_ordered
"""
import argparse
import csv
import os

from models.panel_model import (fairness_metrics, member_measures, read_agenda, read_alpha,
                                read_panel)


class MeetingOrder:
    """Exact order of one meeting by dynamic programming over the set of proposals discussed so far.

    A member present in the meeting stays until their last own proposal; a conflicted member is
    present when a proposal comes up if they still have an own proposal after it."""

    def __init__(self, proposals, reviewers, coi):
        self.proposals = list(proposals)
        index = {p: i for i, p in enumerate(self.proposals)}
        members = sorted({r for p in self.proposals for r in reviewers[p]})
        self.members = members
        # Bit mask of each member's own proposals in this meeting.
        self.own = {r: sum(1 << index[p] for p in self.proposals if r in reviewers[p]) for r in members}
        self.of = [[r for r in reviewers[p]] for p in self.proposals]
        self.conflicted = [[r for r in coi.get(p, ()) if r in self.own] for p in self.proposals]

    def leave(self, order):
        """Slot of each member's last own proposal in an order (list of proposals)."""
        slot = {p: k for k, p in enumerate(order, 1)}
        return {r: max(slot[p] for p in self.proposals if self.own[r] >> self.proposals.index(p) & 1)
                for r in self.members}

    def coi_present(self, order):
        """Number of times a conflicted member is present when the proposal comes up."""
        leave = self.leave(order)
        return sum(1 for k, p in enumerate(order, 1) for r in self.conflicted[self.proposals.index(p)]
                   if leave[r] >= k)

    def solve(self, cap=None, coi_first=True):
        """Order minimising (conflicted members present, sum of leave) lexicographically, or only the
        sum of leave if coi_first is False. cap {member: slot} is the latest slot each member may
        leave at. Returns (order, coi, sum of leave), or None if no order meets the caps."""
        n = len(self.proposals)
        full = (1 << n) - 1
        cap = cap or {}
        caps = [(self.own[r], cap[r]) for r in self.members if r in cap]
        limit = {r: cap.get(r, n) for r in self.members}

        def fits(after, k):
            """Every member still in the meeting can have their remaining proposals before their cap."""
            if after not in fits.memo:
                fits.memo[after] = all(k + bin(mask & ~after).count('1') <= c
                                       for mask, c in caps if mask & ~after)
            return fits.memo[after]
        fits.memo = {}

        best = {0: (0, 0)}
        parent = {}
        for done in range(full + 1):  # adding a proposal makes the set larger, so this order works
            if done not in best:
                continue
            cost_coi, cost_leave = best[done]
            for i in range(n):
                bit = 1 << i
                if done & bit:
                    continue
                after = done | bit
                k = bin(after).count('1')
                finishing = [r for r in self.of[i] if not self.own[r] & ~after]
                if any(k > limit[r] for r in finishing) or not fits(after, k):
                    continue
                finished = len(finishing)
                present = sum(1 for r in self.conflicted[i] if self.own[r] & ~after) if coi_first else 0
                cost = (cost_coi + present, cost_leave + k * finished)
                if after not in best or cost < best[after]:
                    best[after] = cost
                    parent[after] = i
        if full not in best:
            return None
        order, done = [], full
        while done:
            i = parent[done]
            order.append(self.proposals[i])
            done &= ~(1 << i)
        order.reverse()
        return order, self.coi_present(order), sum(self.leave(order).values())


def order_agenda(data, agenda):
    """Reorder every meeting not yet held. Returns the new agenda {proposal: (meeting, slot)} and
    one report row per meeting."""
    held = {data.fixed_meeting[p] for p in data.fixed_position}
    meetings = sorted({m for m, _ in agenda.values()}, key=lambda m: int(m[1:]))
    new_agenda, report = dict(agenda), []
    for m in meetings:
        order = [p for p, _ in sorted(((p, k) for p, (pm, k) in agenda.items() if pm == m),
                                      key=lambda pk: pk[1])]
        if m in held:
            continue
        problem = MeetingOrder(order, data.reviewers, data.coi)
        given_leave = problem.leave(order)
        own_total = sum(bin(mask).count('1') for mask in problem.own.values())
        best, best_coi, best_leave = problem.solve(cap=given_leave)
        _, _, bound_leave = problem.solve(coi_first=False)
        for k, p in enumerate(best, 1):
            new_agenda[p] = (m, k)
        report.append({'meeting': m, 'proposals': len(order), 'members': len(problem.members),
                       'coi_given': problem.coi_present(order), 'coi_best': best_coi,
                       'waiting_given': sum(given_leave.values()) - own_total,
                       'waiting_best': best_leave - own_total, 'waiting_bound': bound_leave - own_total,
                       'changed': int(best != order)})
    return new_agenda, report


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('panel', help='pseudonymised panel.csv')
    parser.add_argument('agenda', help='agenda CSV (meeting, position, application) to reorder')
    parser.add_argument('--out', help='prefix for <prefix>_agenda.csv and <prefix>_order.csv')
    parser.add_argument('--alpha', type=float, default=2.0, help='cost of attending a meeting, in slots')
    parser.add_argument('--alpha-file', help='CSV (member, alpha) of alpha per member')
    args = parser.parse_args()

    data = read_panel(args.panel)
    agenda = read_agenda(args.agenda)
    new_agenda, report = order_agenda(data, agenda)
    for row in report:
        print(f"{row['meeting']}: {row['proposals']} proposals, waiting {row['waiting_given']} -> "
              f"{row['waiting_best']} (bound {row['waiting_bound']}), conflicted present "
              f"{row['coi_given']} -> {row['coi_best']}")
    alpha = read_alpha(args.alpha_file, args.alpha, data.members)
    before = fairness_metrics(member_measures(data, agenda, alpha))
    after = fairness_metrics(member_measures(data, new_agenda, alpha))
    for key in ('max_burden', 'total_waiting', 'burden_sorted'):
        print(f'{key}: {before[key]} -> {after[key]}')
    given = sum(r['waiting_given'] for r in report)
    best = sum(r['waiting_best'] for r in report)
    bound = sum(r['waiting_bound'] for r in report)
    print(f'waiting in reordered meetings: given {given}, best with nobody worse off {best}, '
          f'least possible {bound}')

    if args.out:
        os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
        with open(f'{args.out}_agenda.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(['meeting', 'position', 'application'])
            writer.writerows(sorted((m, k, p) for p, (m, k) in new_agenda.items()))
        with open(f'{args.out}_order.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=list(report[0]) if report else ['meeting'])
            writer.writeheader()
            writer.writerows(report)


if __name__ == '__main__':
    main()
