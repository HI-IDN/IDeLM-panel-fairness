"""
Meeting schedule for a review panel: which meeting each proposal is discussed in, and in what
order.

Inspired by the APAP allocation model (models/allocation_model.py). There, doctors get a leave
order each day and the points are balanced over a horizon. Here, a panel member may leave once the
last of their proposals has been discussed, and their burden over the round combines

    * commitment: every meeting they must attend costs `alpha` slots, whether or not they
      stay long, because it ties up their evening; and
    * waiting: the slot in which their last proposal ends, i.e. how long they stay.

A member who has to attend often is therefore compensated by leaving earlier, and a member who
attends rarely may stay longer. `alpha` can differ per member, to reflect whether they would
rather attend less often and stay longer (high alpha) or attend often and leave early (low alpha).

Burden is compared relative to each member's own load (number of proposals). The objective
minimises the largest relative burden (the least well-off member) and, with a small weight, the
total burden.

Meetings that have already been held are fixed: their proposals stay in that meeting, and their
order is fixed too when an agenda is given. Their burden counts towards the round, just like APAP
carries points from earlier days.

Members can be unavailable for some meetings (other obligations); none of their proposals are
then scheduled there. A member with a conflict of interest in a proposal is never present when it
is discussed: they either don't attend that meeting or have left before it comes up.

The first version treats all proposals as taking one slot of equal length.

Usage (from code/):
    python -m models.panel_model ../data/tdf/panel.csv --fix-meetings M1 M2 \
        --out ../data/tdf/results/free
"""
import argparse
import csv
import os
from collections import defaultdict
from dataclasses import dataclass, field

import yaml
from gurobipy import GRB, Model, quicksum  # pylint: disable=no-name-in-module

ROLES = ('editor', 'reader1', 'reader2')


@dataclass
class PanelData:
    """Proposals with their three members, the meetings, and what is already fixed."""
    reviewers: dict                      # proposal -> tuple of members
    meetings: list                       # ['M1', 'M2', ...] in date order
    current: dict                        # proposal -> meeting in the current plan (or None)
    fixed_meeting: dict = field(default_factory=dict)   # proposal -> meeting (held meetings)
    fixed_position: dict = field(default_factory=dict)  # proposal -> slot, when agenda known
    unavailable: dict = field(default_factory=dict)     # member -> meetings they can't attend
    coi: dict = field(default_factory=dict)             # proposal -> members with a conflict

    @property
    def members(self):
        return sorted({r for trio in self.reviewers.values() for r in trio})

    def proposals_of(self, member):
        return [p for p, trio in self.reviewers.items() if member in trio]


def read_panel(panel_file):
    """Read the pseudonymised panel.csv. Proposals without any reviewer are left out.

    Proposals with an agenda position were discussed in a meeting that has been held: they are
    fixed to that meeting and position.
    """
    with open(panel_file, newline='', encoding='utf-8-sig') as f:
        rows = list(csv.DictReader(f))
    meetings = sorted({r['meeting'] for r in rows if r['meeting']}, key=lambda m: int(m[1:]))
    reviewers, current, fixed_meeting, fixed_position, coi = {}, {}, {}, {}, {}
    for row in rows:
        trio = tuple(row[role] for role in ROLES if row[role])
        if not trio:
            continue
        p = row['application']
        reviewers[p] = trio
        if row['coi']:
            coi[p] = row['coi'].split(';')
        current[p] = row['meeting'] or None
        if row.get('position'):
            fixed_meeting[p], fixed_position[p] = current[p], int(row['position'])
    return PanelData(reviewers=reviewers, meetings=meetings,
                     current=current, fixed_meeting=fixed_meeting, fixed_position=fixed_position,
                     coi=coi)


def read_unavailable(unavailable_file):
    """Meetings members can't attend: columns member, meeting (one row per pair)."""
    unavailable = {}
    with open(unavailable_file, newline='', encoding='utf-8-sig') as f:
        for row in csv.DictReader(f):
            unavailable.setdefault(row['member'], set()).add(row['meeting'])
    return unavailable


def read_new_members(members_file):
    """Codes of new panel members: columns member, new (TRUE/FALSE)."""
    with open(members_file, newline='', encoding='utf-8-sig') as f:
        return {row['member'] for row in csv.DictReader(f) if row['new'].strip().upper() == 'TRUE'}


def meetings_attended(data, agenda):
    """Number of meetings each member attends in an agenda {proposal: (meeting, slot)}."""
    attended = {r: set() for r in data.members}
    for p, (m, _) in agenda.items():
        for r in data.reviewers.get(p, ()):
            attended[r].add(m)
    return {r: len(ms) for r, ms in attended.items()}


def read_agenda(agenda_file):
    """Agenda from an earlier solution: columns application, meeting, position (1 = first)."""
    with open(agenda_file, newline='', encoding='utf-8-sig') as f:
        return {row['application']: (row['meeting'], int(row['position'])) for row in csv.DictReader(f)}


class PanelScheduleModel:
    """
    Assign each proposal to a meeting and a slot so that members' burden is shared fairly.

    Decision variables:
        x[p, m, k]  1 if proposal p is discussed in meeting m as number k
        a[r, m]     1 if member r has to attend meeting m
        leave[r, m] slot after which member r may leave meeting m (0 if not attending)
        z           largest burden per proposal over all members
    """

    def __init__(self, data, alpha=4.0, max_per_meeting=15, total_weight=0.01, time_limit=120,
                 keep_meetings=False, coi_penalty=1.0, closed_meetings=(), max_per_member=None,
                 first_meeting_rule=True, target_per_meeting=None, target_weight=0.0,
                 open_meeting_size=None, pair_limit=None, pair_weight=0.0, max_meetings=None,
                 next_meeting=None, postpone_penalty=0.5, not_before=None, max_two_meetings=None,
                 meeting_cost=0.0, min_per_member=None, fairness='proposal', max_waiting=None):
        """
        alpha:              cost of attending a meeting, in slots; a number or {member: value}
        max_per_meeting:    most proposals one meeting can handle
        total_weight:       weight of the total burden next to the worst-off member's burden
        keep_meetings:      keep every proposal in its current meeting and only choose the order
        coi_penalty:        objective penalty for each time a conflicted member is present
        closed_meetings:    meetings whose proposals are settled (e.g. the next meeting): no other
                            proposals may be moved there. Held meetings are always closed.
        max_per_member:     most proposals one member may have in one meeting (None: no limit);
                            applies to meetings that are not closed
        first_meeting_rule: in the first meeting everyone attends with exactly one proposal, unless
                            that meeting is already closed
        target_per_meeting: {member: target} number of own proposals per meeting attended (e.g. 3.5
                            for experienced and 2.5 for new members); None for no target
        target_weight:      objective weight of the average deviation from the target (soft)
        open_meeting_size:  most proposals in a meeting that is not closed (None: max_per_meeting);
                            used for shorter meetings
        pair_limit:         soft limit on a member's proposals in two consecutive meetings, so heavy
                            reading in one meeting is followed by a lighter one
        pair_weight:        objective weight of the average excess over pair_limit
        max_meetings:       {member: most meetings they may attend}, e.g. no more than in an
                            earlier schedule; None for no limit
        next_meeting:       the next meeting (e.g. 'M3'): no proposals may be added to it, because
                            members have prepared for the announced ones, but a planned proposal
                            may be postponed to a later meeting (as when short of staff)
        postpone_penalty:   objective penalty for each postponed proposal of the next meeting
        max_two_meetings:   most own proposals of a member in two consecutive meetings (None: no
                            limit), so a heavy meeting is followed by no meeting or a light one
        not_before:         {proposal: first meeting it may go to}, e.g. proposals edited by a new
                            member only after the middle of the round
        """
        self.data = data
        self.alpha = alpha if isinstance(alpha, dict) else {r: alpha for r in data.members}
        self.max_per_meeting = max_per_meeting
        self.total_weight = total_weight
        self.coi_penalty = coi_penalty
        self.m = Model('PanelSchedule')
        self.m.Params.TimeLimit = time_limit
        self.solution = None

        self.fixed_meeting = dict(data.fixed_meeting)
        if keep_meetings:
            self.fixed_meeting.update({p: m for p, m in data.current.items() if m})
        held = {data.fixed_meeting[p] for p in data.fixed_position}
        self.closed = set(closed_meetings) | held
        self.next_meeting = next_meeting
        self.postpone_penalty = postpone_penalty
        self.not_before = not_before or {}
        self.max_two_meetings = max_two_meetings
        self.meeting_cost = meeting_cost
        self.fairness = fairness
        self.max_waiting = max_waiting
        self.min_per_member = min_per_member
        self.planned_next = {p for p, m in data.current.items()
                             if next_meeting and m == next_meeting and p in data.reviewers}
        self.max_per_member = max_per_member
        self.first_meeting_rule = first_meeting_rule
        self.target = target_per_meeting or {}
        self.target_weight = target_weight
        self.open_meeting_size = open_meeting_size
        self.pair_limit = pair_limit
        self.pair_weight = pair_weight
        self.max_meetings = max_meetings or {}

        self._set_variables()
        self._set_constraints()
        self._set_objective()

    def _allowed(self, p):
        """Meetings a proposal may go to."""
        if p in self.fixed_meeting:
            return [self.fixed_meeting[p]]
        open_meetings = [m for m in self.data.meetings if m not in self.closed and m != self.next_meeting]
        if p in self.not_before:
            first = self.data.meetings.index(self.not_before[p])
            open_meetings = [m for m in open_meetings if self.data.meetings.index(m) >= first]
        if p in self.planned_next:  # stays in the next meeting, or is postponed to a later one
            later = self.data.meetings.index(self.next_meeting)
            return [self.next_meeting] + [m for m in open_meetings if self.data.meetings.index(m) > later]
        return open_meetings

    def _set_variables(self):
        slots = range(1, self.max_per_meeting + 1)
        self.slots = list(slots)
        self.x = {(p, m, k): self.m.addVar(vtype=GRB.BINARY, name=f'x[{p},{m},{k}]')
                  for p in self.data.reviewers for m in self._allowed(p) for k in slots}
        self.a = self.m.addVars(self.data.members, self.data.meetings, vtype=GRB.BINARY, name='a')
        self.leave = self.m.addVars(self.data.members, self.data.meetings, lb=0, name='leave')
        self.z = self.m.addVar(lb=0, name='z')

    def _placed(self, p, m):
        """1 if proposal p is in meeting m (linear expression)."""
        return quicksum(self.x[p, m, k] for k in self.slots if (p, m, k) in self.x)

    def _slot(self, p, m):
        """Slot of proposal p in meeting m, or 0 if it is not there (linear expression)."""
        return quicksum(k * self.x[p, m, k] for k in self.slots if (p, m, k) in self.x)

    def _set_constraints(self):
        data, x = self.data, self.x
        # Every proposal is discussed exactly once.
        self.m.addConstrs((quicksum(x[p, m, k] for m in self._allowed(p) for k in self.slots) == 1
                           for p in data.reviewers), name='once')
        # One proposal per slot, and slots are filled from the start without gaps.
        for m in data.meetings:
            filled = {k: quicksum(x[p, m, k] for p in data.reviewers if (p, m, k) in x)
                      for k in self.slots}
            self.m.addConstrs((filled[k] <= 1 for k in self.slots), name=f'slot[{m}]')
            self.m.addConstrs((filled[k + 1] <= filled[k] for k in self.slots[:-1]),
                              name=f'nogap[{m}]')
        # A member has at most max_per_member proposals in one meeting (meetings still open).
        if self.max_per_member:
            for r in data.members:
                for m in set(data.meetings) - self.closed:
                    self.m.addConstr(quicksum(self._placed(p, m) for p in data.proposals_of(r)
                                              if m in self._allowed(p)) <= self.max_per_member,
                                     name=f'per_member[{r},{m}]')
        # Each member attends at most max_meetings[r] meetings over the round.
        for r, limit in self.max_meetings.items():
            if r in data.members:
                self.m.addConstr(self.a.sum(r, '*') <= limit, name=f'max_meetings[{r}]')
        # A member who attends an open meeting has at least min_per_member own proposals there
        # (nobody comes for a single proposal). Exempt: the first meeting (one each), held meetings,
        # and the next meeting, whose agenda is already announced.
        if self.min_per_member:
            first = data.meetings[0]
            for r in data.members:
                for m in set(data.meetings) - self.closed - {first, self.next_meeting}:
                    own = quicksum(self._placed(p, m) for p in data.proposals_of(r) if m in self._allowed(p))
                    self.m.addConstr(own >= self.min_per_member * self.a[r, m], name=f'min_own[{r},{m}]')
        # At most max_two_meetings own proposals in any two consecutive meetings (not both closed).
        if self.max_two_meetings:
            for r in data.members:
                own = {m: quicksum(self._placed(p, m) for p in data.proposals_of(r) if m in self._allowed(p))
                       for m in data.meetings}
                for m, nxt in zip(data.meetings, data.meetings[1:]):
                    if m in self.closed and nxt in self.closed:
                        continue
                    self.m.addConstr(own[m] + own[nxt] <= self.max_two_meetings, name=f'two[{r},{m}]')
        # Shorter meetings: at most open_meeting_size proposals in each meeting that is not closed.
        if self.open_meeting_size:
            for m in set(data.meetings) - self.closed:
                self.m.addConstr(quicksum(self._placed(p, m) for p in data.reviewers if m in self._allowed(p))
                                 <= self.open_meeting_size, name=f'meeting_size[{m}]')
        # First meeting: everyone attends, with exactly one proposal each.
        first = data.meetings[0]
        if self.first_meeting_rule and first not in self.closed:
            for r in data.members:
                self.m.addConstr(quicksum(self._placed(p, first) for p in data.proposals_of(r)) == 1,
                                 name=f'first_meeting[{r}]')
        # Members can't attend meetings they are unavailable for, so none of their proposals go
        # there. Held meetings are left out: they already happened.
        held = {data.fixed_meeting[p] for p in data.fixed_position}
        for r, meetings in data.unavailable.items():
            for m in set(meetings) - held:
                self.m.addConstr(self.a[r, m] == 0, name=f'unavailable[{r},{m}]')
        # A member with a conflict of interest should not be present when that proposal is
        # discussed: either they are not at the meeting, or they have already left. This is a soft
        # rule: two members with crossed conflicts in the same meeting can't both be satisfied, so
        # each exception coi_present[p, r, m] = 1 is allowed but penalised in the objective.
        big_m = self.max_per_meeting + 1
        self.coi_present = {}
        for p, conflicted in data.coi.items():
            for r in conflicted:
                if r not in data.members:
                    continue
                for m in set(self._allowed(p)) - held:
                    v = self.m.addVar(vtype=GRB.BINARY, name=f'coi_present[{p},{r},{m}]')
                    self.coi_present[p, r, m] = v
                    self.m.addConstr(self._slot(p, m) >= self.leave[r, m] + 1
                                     - big_m * (1 - self._placed(p, m)) - big_m * v,
                                     name=f'coi[{p},{r},{m}]')
        # Known agenda positions of held meetings.
        for p, k in data.fixed_position.items():
            self.m.addConstr(x[p, data.fixed_meeting[p], k] == 1, name=f'agenda[{p}]')
        # A member attends a meeting with any of their proposals, and stays until the last one.
        for r in data.members:
            for p in data.proposals_of(r):
                for m in self._allowed(p):
                    self.m.addConstr(self.a[r, m] >= self._placed(p, m), name=f'attend[{r},{p},{m}]')
                    self.m.addConstr(self.leave[r, m] >= self._slot(p, m), name=f'leave[{r},{p},{m}]')
            # Members don't attend meetings without any of their proposals.
            for m in data.meetings:
                self.m.addConstr(self.a[r, m] <= quicksum(self._placed(p, m) for p in data.proposals_of(r)
                                                          if m in self._allowed(p)),
                                 name=f'noattend[{r},{m}]')

    def burden(self, r):
        """Commitment (alpha per meeting attended) plus waiting (slot of the last proposal)."""
        return quicksum(self.alpha[r] * self.a[r, m] + self.leave[r, m] for m in self.data.meetings)

    def _set_objective(self):
        # Fairness, the worst-off member by
        #   proposal: burden (commitment + waiting) per own proposal;
        #   total:    total waiting over the round, not divided by anything, so the worst case leads.
        # Waiting = slots stayed minus own proposals = proposals of others sat through.
        for r in self.data.members:
            n = len(self.data.proposals_of(r))
            waiting = quicksum(self.leave[r, m] for m in self.data.meetings) - n
            if self.max_waiting is not None:  # nobody waits longer than in a reference plan
                self.m.addConstr(waiting <= self.max_waiting, name=f'max_waiting[{r}]')
            if self.fairness == 'total':
                self.m.addConstr(waiting <= self.z, name=f'fair[{r}]')
            else:
                self.m.addConstr(self.burden(r) <= self.z * n, name=f'fair[{r}]')
        total = quicksum(self.burden(r) for r in self.data.members)
        # Soft target: in each open meeting a member attends, their number of own proposals should
        # be close to their target. dev[r, m] >= |proposals - target * attends|.
        deviation = 0
        if self.target and self.target_weight:
            dev = self.m.addVars(self.data.members, self.data.meetings, lb=0, name='target_dev')
            for r in self.data.members:
                for m in set(self.data.meetings) - self.closed:
                    own = quicksum(self._placed(p, m) for p in self.data.proposals_of(r) if m in self._allowed(p))
                    goal = self.target[r] * self.a[r, m]
                    self.m.addConstr(dev[r, m] >= own - goal, name=f'target_over[{r},{m}]')
                    self.m.addConstr(dev[r, m] >= goal - own, name=f'target_under[{r},{m}]')
            deviation = dev.sum() / len(self.data.members)
        # Soft limit on reading in two consecutive meetings: excess[r, m] >= own(m) + own(next) - limit.
        excess = 0
        if self.pair_limit and self.pair_weight:
            meetings = self.data.meetings
            over = self.m.addVars(self.data.members, meetings[:-1], lb=0, name='pair_excess')
            for r in self.data.members:
                own = {m: quicksum(self._placed(p, m) for p in self.data.proposals_of(r) if m in self._allowed(p))
                       for m in meetings}
                for m, nxt in zip(meetings, meetings[1:]):
                    if m in self.closed and nxt in self.closed:
                        continue
                    self.m.addConstr(over[r, m] >= own[m] + own[nxt] - self.pair_limit,
                                     name=f'pair[{r},{m}]')
            excess = over.sum() / len(self.data.members)
        postponed = quicksum(1 - self._placed(p, self.next_meeting) for p in self.planned_next)
        self.m.setObjective(self.z + self.total_weight * total / len(self.data.members)
                            + self.postpone_penalty * postponed
                            # A large cost per meeting attended keeps the number of meetings low first.
                            + self.meeting_cost * quicksum(self.a.values()) / len(self.data.members)
                            + self.coi_penalty * quicksum(self.coi_present.values())
                            + self.target_weight * deviation + self.pair_weight * excess, GRB.MINIMIZE)

    def set_start(self, agenda):
        """Warm start from an agenda {proposal: (meeting, slot)}, e.g. a solution with fewer freedoms.

        Proposals whose place in the agenda breaks a rule of this model (a meeting it may not go
        to, or too many proposals for a member or a meeting) are left out of the start, and Gurobi
        completes the partial start itself. The rest of the agenda is kept.
        """
        drop = {p for p, (m, _) in agenda.items() if p in self.data.reviewers and m not in self._allowed(p)}
        by_meeting = defaultdict(list)
        for p, (m, k) in agenda.items():
            if p not in drop:
                by_meeting[m].append((k, p))
        for m, items in by_meeting.items():
            if m in self.closed:
                continue
            items.sort()
            if self.open_meeting_size and len(items) > self.open_meeting_size:
                drop.update(p for _, p in items[self.open_meeting_size:])
            if self.max_per_member:
                own = defaultdict(list)
                for k, p in items:
                    for r in self.data.reviewers[p]:
                        own[r].append(p)
                for r, proposals in own.items():
                    drop.update(proposals[self.max_per_member:])
        if self.max_two_meetings:
            meetings = self.data.meetings
            placed_in = {m: [p for p, (pm, _) in agenda.items() if pm == m and p not in drop] for m in meetings}
            for r in self.data.members:
                for m, nxt in zip(meetings, meetings[1:]):
                    if m in self.closed and nxt in self.closed:
                        continue
                    first = [p for p in placed_in[m] if r in self.data.reviewers.get(p, ())]
                    second = [p for p in placed_in[nxt] if r in self.data.reviewers.get(p, ()) and p not in drop]
                    excess = len(first) + len(second) - self.max_two_meetings
                    if excess > 0:
                        drop.update(second[len(second) - excess:] if nxt not in self.closed else first[-excess:])
        if self.min_per_member:  # a member with too few proposals in an open meeting: leave them open
            first = self.data.meetings[0]
            for m in set(self.data.meetings) - self.closed - {first, self.next_meeting}:
                in_m = [p for p, (pm, _) in agenda.items() if pm == m and p not in drop]
                for r in self.data.members:
                    own = [p for p in in_m if r in self.data.reviewers.get(p, ())]
                    if 0 < len(own) < self.min_per_member:
                        drop.update(own)
        drop.update(p for p in self.data.reviewers if p not in agenda)  # not in the start at all
        for (p, m, k), var in self.x.items():
            var.Start = GRB.UNDEFINED if p in drop else (1 if agenda.get(p) == (m, k) else 0)
        if drop:
            print(f'warm start: {len(drop)} proposals left open for Gurobi to place')

    def solve(self):
        self.m.optimize()
        if self.m.SolCount == 0:
            raise RuntimeError(f'No solution found (status {self.m.Status}).')
        agenda = sorted((m, k, p) for (p, m, k), var in self.x.items() if var.X > 0.5)
        self.solution = {
            'agenda': [{'meeting': m, 'position': k, 'application': p} for m, k, p in agenda],
            'members': [self._member_summary(r) for r in self.data.members],
            'status': self.m.Status, 'objective': self.m.ObjVal, 'gap': self.m.MIPGap,
            'postponed': sorted(p for p in self.planned_next
                                if self._placed(p, self.next_meeting).getValue() < 0.5),
            'coi_present': [{'application': p, 'member': r, 'meeting': m}
                            for (p, r, m), v in self.coi_present.items() if v.X > 0.5],
        }
        return self.solution

    def _member_summary(self, r):
        """Per member: meetings attended, slots stayed, and peel-off points, i.e. proposals of
        others they sat through before their last own proposal (in total, per meeting attended and
        per own proposal)."""
        attended = [m for m in self.data.meetings if self.a[r, m].X > 0.5]
        leave_slots = sum(self.leave[r, m].X for m in self.data.meetings)
        n = len(self.data.proposals_of(r))
        waiting = round(leave_slots) - n
        burden = self.alpha[r] * len(attended) + leave_slots
        return {'member': r, 'proposals': n, 'meetings': len(attended), 'leave_slots': round(leave_slots),
                'waiting': waiting, 'waiting_per_meeting': round(waiting / max(len(attended), 1), 3),
                'waiting_per_proposal': round(waiting / n, 3),
                'alpha': self.alpha[r], 'burden': round(burden, 2), 'burden_per_proposal': round(burden / n, 3)}

    def save(self, out_prefix):
        os.makedirs(os.path.dirname(out_prefix) or '.', exist_ok=True)
        columns = {'agenda': ['meeting', 'position', 'application'],
                   'members': ['member', 'proposals', 'meetings', 'leave_slots', 'waiting',
                               'waiting_per_meeting', 'waiting_per_proposal', 'alpha', 'burden',
                               'burden_per_proposal'],
                   'coi_present': ['application', 'member', 'meeting']}
        for name, fields in columns.items():
            rows = self.solution[name]
            with open(f'{out_prefix}_{name}.csv', 'w', newline='', encoding='utf-8') as f:
                writer = csv.DictWriter(f, fieldnames=fields)
                writer.writeheader()
                writer.writerows(rows)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('panel', help='pseudonymised panel.csv')
    parser.add_argument('--config', default=os.path.join(os.path.dirname(__file__), 'panel_model.yml'),
                        help='YAML file with the model settings')
    parser.add_argument('--fix-meetings', nargs='*', default=[],
                        help='also keep the proposals of these meetings in them (order still free)')
    parser.add_argument('--keep-meetings', action='store_true',
                        help='keep all proposals in their current meeting; only choose the order')
    parser.add_argument('--alpha', type=float, help='cost of attending a meeting, in slots')
    parser.add_argument('--max-per-meeting', type=int)
    parser.add_argument('--max-per-member', type=int, help='most proposals per member in one meeting')
    parser.add_argument('--fairness', choices=['proposal', 'total'], default='proposal',
                        help="worst-off member by burden per proposal, or by total waiting ('total')")
    parser.add_argument('--coi-penalty', type=float,
                        help='objective cost each time a conflicted member must step out and come back')
    parser.add_argument('--postpone-penalty', type=float,
                        help='objective cost of each proposal postponed from the next meeting')
    parser.add_argument('--max-waiting', type=int,
                        help="most total waiting (others' proposals sat through) for any member, e.g. that of the current plan")
    parser.add_argument('--meeting-cost', type=float, default=0.0,
                        help='objective cost of each meeting a member attends (e.g. 100: meetings first)')
    parser.add_argument('--min-per-member', type=int,
                        help='least own proposals of a member in a meeting they attend (open meetings)')
    parser.add_argument('--pair-limit', type=int,
                        help='soft limit on own proposals in two consecutive meetings (penalised excess)')
    parser.add_argument('--pair-weight', type=float, help='objective weight of the excess over --pair-limit')
    parser.add_argument('--max-two-meetings', type=int,
                        help='most own proposals of a member in two consecutive meetings')
    parser.add_argument('--new-editor-from',
                        help='meeting from which new members may be editor (e.g. M5, the middle of the round)')
    parser.add_argument('--next-meeting',
                        help='next meeting: nothing may be added, planned proposals may be postponed')
    parser.add_argument('--max-meetings-from',
                        help='agenda CSV: no member attends more meetings than in that schedule')
    parser.add_argument('--more-meetings', action='store_true',
                        help='more, shorter meetings: extra meetings, a smaller size limit and a soft '
                             'limit on reading in consecutive meetings (settings in the YAML file)')
    parser.add_argument('--from-scratch', action='store_true',
                        help='plan the whole round from the start: held meetings are not fixed')
    parser.add_argument('--target', action='store_true',
                        help='use the target number of proposals per meeting (experienced / new)')
    parser.add_argument('--time-limit', type=float)
    parser.add_argument('--mip-focus', type=int, default=0,
                        help='Gurobi MIPFocus (1: focus on finding good solutions quickly)')
    parser.add_argument('--start', help='agenda CSV to warm-start from (e.g. the order-only solution)')
    parser.add_argument('--unavailable', help='CSV of meetings members cannot attend (member, meeting)')
    parser.add_argument('--out', required=True, help='output prefix, e.g. ../data/tdf/results/free')
    args = parser.parse_args()
    with open(args.config, encoding='utf-8') as f:
        config = yaml.safe_load(f)
    # Command-line options override the settings file.
    for name in ('alpha', 'max_per_meeting', 'time_limit', 'unavailable', 'max_per_member', 'coi_penalty',
                 'postpone_penalty'):
        if getattr(args, name) is not None:
            config[name] = getattr(args, name)

    data = read_panel(args.panel)
    if args.more_meetings:
        extra = config['extra_meetings']
        start = len(data.meetings) + 1
        data.meetings = data.meetings + [f'M{i}' for i in range(start, start + extra)]
        print(f"more meetings: {extra} extra, at most {config['open_meeting_size']} proposals each")
    if args.from_scratch:
        data.fixed_meeting, data.fixed_position = {}, {}
    data.fixed_meeting.update({p: m for p, m in data.current.items() if m in args.fix_meetings})
    if config.get('unavailable'):
        data.unavailable = read_unavailable(config['unavailable'])
        print(f'{sum(map(len, data.unavailable.values()))} member-meeting unavailabilities')
    print(f'{len(data.fixed_position)} proposals fixed by the agenda of held meetings')
    targets = None
    if args.target:
        new = read_new_members(config['members'])
        targets = {r: config['target_new'] if r in new else config['target_experienced'] for r in data.members}
        print(f"target per meeting: {config['target_experienced']} experienced, "
              f"{config['target_new']} new ({len(new & set(data.members))} new members)")

    not_before = {}
    if args.new_editor_from:
        new = read_new_members(config['members'])
        not_before = {p: args.new_editor_from for p, trio in data.reviewers.items() if trio[0] in new}
        print(f'{len(not_before)} proposals edited by new members go to {args.new_editor_from} or later')
    max_meetings = {}
    if config.get('max_meetings_per_member'):
        max_meetings = {r: config['max_meetings_per_member'] for r in data.members}
    if args.max_meetings_from:
        earlier = meetings_attended(data, read_agenda(args.max_meetings_from))
        max_meetings = {r: min(n, max_meetings.get(r, n)) for r, n in earlier.items()}
    if max_meetings:
        print(f'meeting limit per member: {min(max_meetings.values())}-{max(max_meetings.values())}')

    model = PanelScheduleModel(data, alpha=float(config['alpha']), max_per_meeting=config['max_per_meeting'],
                               total_weight=config['total_weight'], time_limit=config['time_limit'],
                               keep_meetings=args.keep_meetings, coi_penalty=float(config['coi_penalty']),
                               closed_meetings=args.fix_meetings, max_per_member=config.get('max_per_member'),
                               first_meeting_rule=config.get('first_meeting_rule', True),
                               target_per_meeting=targets, target_weight=config.get('target_weight', 0.0),
                               open_meeting_size=config['open_meeting_size'] if args.more_meetings else None,
                               pair_limit=args.pair_limit or config.get('pair_limit'),
                               pair_weight=(args.pair_weight if args.pair_weight is not None
                                            else config.get('pair_weight', 0.0) if args.more_meetings else 0.0),
                               max_meetings=max_meetings, next_meeting=args.next_meeting,
                               postpone_penalty=float(config.get('postpone_penalty', 0.5)),
                               not_before=not_before, max_two_meetings=args.max_two_meetings,
                               meeting_cost=args.meeting_cost, min_per_member=args.min_per_member,
                               fairness=args.fairness, max_waiting=args.max_waiting)
    model.m.Params.MIPFocus = args.mip_focus
    if args.start:
        model.set_start(read_agenda(args.start))
    solution = model.solve()
    model.save(args.out)
    print(f"objective {solution['objective']:.3f}, gap {solution['gap']:.1%}, "
          f"conflicted members present: {len(solution['coi_present'])}, "
          f"postponed from the next meeting: {solution['postponed'] or 'none'}")


if __name__ == '__main__':
    main()
