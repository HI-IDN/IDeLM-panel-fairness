"""
Meeting schedule for a review panel: which meeting each proposal is discussed in, and in what
order.

Inspired by the APAP allocation model (models/allocation_model.py). There, doctors get a leave
order each day and the points are balanced over a horizon. Here, a panel member may leave once the
last of their proposals has been discussed, and their burden over the round combines

    * commitment: every meeting they must attend costs `alpha` slots, whether or not they
      stay long, because it ties up their afternoon; and
    * waiting: the slot in which their last proposal ends, i.e. how long they stay.

A member who has to attend often is therefore compensated by leaving earlier, and a member who
attends rarely may stay longer. `alpha` can differ per member, to reflect whether they would
rather attend less often and stay longer (high alpha) or attend often and leave early (low alpha).

The objective is chosen with `fairness`. The original one ('proposal') minimises the largest burden
per own proposal and, with a small weight, the total burden. The recommended ones are solved in
steps: first the fewest meetings attended (with the rule costs), then fairness of the unpaid burden
alpha * meetings + waiting (the largest one with 'lexburden', or leximin with 'leximin', which
protects every member and not only the worst-off one), then the least total waiting. A reference
plan (`reference_burden`) adds a first step that keeps everyone at most as burdened as there.
Reported measures are recomputed from the agenda (member_measures, fairness_metrics).

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
# Objectives solved in steps (see PanelScheduleModel._solve_in_steps).
STEP_MODES = ('lex', 'lexmax', 'lexboth', 'lexburden', 'lexsum', 'leximin')
# Modes with an equity-band term, which needs leave tied to the actual last own slot.
BAND_MODES = ('bands', 'lex', 'lexboth')


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
    """Codes of new panel members: columns member, new (TRUE/FALSE). The file stays local
    (gitignored); without it no member counts as new."""
    if not os.path.exists(members_file):
        print(f'{members_file} not found: no members are treated as new')
        return set()
    with open(members_file, newline='', encoding='utf-8-sig') as f:
        return {row['member'] for row in csv.DictReader(f) if row['new'].strip().upper() == 'TRUE'}


def meetings_attended(data, agenda):
    """Number of meetings each member attends in an agenda {proposal: (meeting, slot)}."""
    attended = {r: set() for r in data.members}
    for p, (m, _) in agenda.items():
        for r in data.reviewers.get(p, ()):
            attended[r].add(m)
    return {r: len(ms) for r, ms in attended.items()}


def member_measures(data, agenda, alpha):
    """Per member, recomputed from an agenda {proposal: (meeting, slot)} rather than from model
    variables: proposals, meetings attended, slots stayed (up to their last own proposal in each
    meeting), waiting (proposals of others sat through) and burden = alpha * meetings + waiting,
    the quantity the fairness steps compare. alpha is a number or {member: value}."""
    leave, own = defaultdict(int), defaultdict(int)
    for p, (m, k) in agenda.items():
        for r in data.reviewers.get(p, ()):
            leave[r, m] = max(leave[r, m], k)
            own[r, m] += 1
    rows = []
    for r in data.members:
        a = alpha[r] if isinstance(alpha, dict) else alpha
        meetings = [m for (s, m) in leave if s == r]
        slots = sum(leave[r, m] for m in meetings)
        n = len(data.proposals_of(r))
        waiting = slots - sum(own[r, m] for m in meetings)
        burden = a * len(meetings) + waiting
        rows.append({'member': r, 'proposals': n, 'meetings': len(meetings), 'leave_slots': slots,
                     'waiting': waiting, 'waiting_per_meeting': round(waiting / max(len(meetings), 1), 3),
                     'waiting_per_proposal': round(waiting / n, 3), 'alpha': a, 'burden': round(burden, 2),
                     'burden_per_proposal': round(burden / n, 3)})
    return rows


def _ranks(values):
    """Ranks 1..n, ties sharing their average rank."""
    order = sorted(range(len(values)), key=lambda i: values[i])
    ranks = [0.0] * len(values)
    i = 0
    while i < len(order):
        j = i
        while j + 1 < len(order) and values[order[j + 1]] == values[order[i]]:
            j += 1
        for t in range(i, j + 1):
            ranks[order[t]] = (i + j) / 2 + 1
        i = j + 1
    return ranks


def spearman(xs, ys):
    """Spearman rank correlation (None if either variable is constant)."""
    rx, ry = _ranks(xs), _ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    sxy = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    sxx, syy = sum((a - mx) ** 2 for a in rx), sum((b - my) ** 2 for b in ry)
    return round(sxy / (sxx * syy) ** 0.5, 3) if sxx and syy else None


def fairness_metrics(rows):
    """How fairly an agenda shares the unpaid burden, from member_measures rows:
        max_burden, mean_burden, gini_burden: the worst-off member, the average and the inequality;
        burden_sorted: all burdens, largest first (compare plans leximin-wise: the first entry that
                       differs decides);
        total_waiting, total_meetings: efficiency;
        rho_meetings_waiting: rank correlation of meetings attended and total waiting. Positive is
                       the original defect: those who attend often also wait more in total;
        inverted_pairs: pairs of members where the one who attends more meetings also waits more in
                       total (the intent is the opposite)."""
    burden = [r['burden'] for r in rows]
    meetings = [r['meetings'] for r in rows]
    waiting = [r['waiting'] for r in rows]
    n, total = len(burden), sum(burden)
    gini = (sum(abs(a - b) for a in burden for b in burden) / (2 * n * total)) if total else 0.0
    inverted = sum(1 for i in range(n) for j in range(n)
                   if meetings[i] > meetings[j] and waiting[i] > waiting[j])
    return {'max_burden': max(burden), 'mean_burden': round(total / n, 3), 'gini_burden': round(gini, 4),
            'burden_sorted': ' '.join(f'{b:g}' for b in sorted(burden, reverse=True)),
            'total_waiting': sum(waiting), 'total_meetings': sum(meetings),
            'rho_meetings_waiting': spearman(meetings, waiting), 'inverted_pairs': inverted}


def read_carry(carry_file):
    """Burden carried over from earlier rounds: columns member, burden (slots; may be negative)."""
    with open(carry_file, newline='', encoding='utf-8-sig') as f:
        return {row['member']: float(row['burden']) for row in csv.DictReader(f)}


def read_agenda(agenda_file):
    """Agenda from an earlier solution: columns application, meeting, position (1 = first)."""
    with open(agenda_file, newline='', encoding='utf-8-sig') as f:
        return {row['application']: (row['meeting'], int(row['position'])) for row in csv.DictReader(f)}


class PanelScheduleModel:
    """
    Assign each proposal to a meeting and a slot so that members' burden is shared fairly.

    Decision variables, created only where they can be nonzero:
        x[p, m, k]  1 if proposal p is discussed in meeting m as number k: for the meetings p may go
                    to, and slots up to the most proposals that meeting can get (a proposal of a
                    held meeting has only its known slot)
        a[r, m]     1 if member r has to attend meeting m, for meetings some proposal of r may go to
        leave[r, m] slot after which member r may leave meeting m (0 if not attending)
        z           largest burden per proposal over all members
    """

    def __init__(self, data, alpha=4.0, max_per_meeting=15, total_weight=0.01, time_limit=120,
                 keep_meetings=False, coi_penalty=1.0, closed_meetings=(), max_per_member=None,
                 first_meeting_rule=True, target_per_meeting=None, target_weight=0.0,
                 open_meeting_size=None, pair_limit=None, pair_weight=0.0, max_meetings=None,
                 next_meeting=None, postpone_penalty=0.5, not_before=None, max_two_meetings=None,
                 meeting_cost=0.0, min_per_member=None, fairness='proposal', max_waiting=None,
                 new_members=(), learning_weight=0.001, soft_max_per_member=None, soft_max_weight=0.0,
                 rotate_wait=None, meetings_slack=0.0, leximin_levels=3, reference_burden=None,
                 carry=None):
        """
        alpha:              cost of attending a meeting, in slots; a number or {member: value}
        max_per_meeting:    most proposals one meeting can handle
        total_weight:       weight of the total burden next to the worst-off member's burden
        keep_meetings:      keep every proposal in its current meeting and only choose the order
        coi_penalty:        objective penalty for each time a conflicted member is present
        closed_meetings:    meetings whose proposals are settled (e.g. the next meeting): no other
                            proposals may be moved there. Held meetings are always closed.
        max_per_member:     most proposals one member may have in one meeting (None: no limit);
                            applies where the meeting is still a decision (not held, not closed,
                            and not when all of the member's proposals there are fixed to it)
        rotate_wait:        rotation rule (None: off): the members of the last proposal of a meeting
                            sit through at most rotate_wait proposals of others at the next meeting,
                            if they attend it (if not, they are first out by definition); a negative
                            value means they don't attend the next meeting at all (not applied to the
                            announced next meeting, whose agenda stays)
        soft_max_per_member: soft cap on own proposals in one meeting (same meetings); each
                            proposal above it costs soft_max_weight in the objective
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
        fairness:           'proposal', 'total', 'unpaid' (worst-off member, see _set_objective),
                            'bands' (the APAP equity measure: members within bands of a common
                            target for waiting per meeting attended), 'sum' (no fairness, only
                            the least total burden) or 'lex' (in steps: first the fewest meetings
                            attended, then the most equity by the bands, then the least waiting);
                            'lexmax' is the same in steps, but the second step makes the longest
                            total waiting of any member as short as possible; 'lexboth' has both
                            fairness steps, the bands first and then the longest waiting;
                            'lexburden' has as second step the largest unpaid burden, alpha per
                            meeting attended plus waiting, so members who attend often wait less;
                            'lexsum' has no fairness step: the fewest meetings, then the least
                            total waiting, whoever carries it (for comparison);
                            'leximin' replaces the single worst-off step of 'lexburden' by
                            leximin_levels steps: the largest burden, then the sum of the two
                            largest, and so on (Ogryczak's ordered min-max), so members below the
                            worst-off one are protected too
        new_members:        codes of new members; with 'bands' and the step modes their waiting in
                            the first half of the round is rewarded, as they sit longer to learn
                            anyway (in the last step only; the fairness steps count it in full)
        learning_weight:    objective weight of that reward, per slot (a tie-breaker)
        meetings_slack:     step modes: the first step (meetings and rule costs) is held at its
                            value plus this slack, so later steps may add a meeting attended where
                            it buys at least alpha slots less waiting (0: hold it exactly)
        leximin_levels:     with 'leximin', how many of the largest burdens are fixed in turn
                            (None or 0: all members)
        reference_burden:   step modes: {member: burden} of a reference plan (e.g. the staff's).
                            A first step makes the total excess over it as small as possible, so
                            nobody is worse off than in that plan where the rules allow it
        carry:              {member: burden carried over from earlier rounds}, added to each
                            member's burden in the fairness steps (lexburden, leximin) and the
                            reference step
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
        self.held = held
        self.closed = set(closed_meetings) | held
        self.next_meeting = next_meeting
        self.postpone_penalty = postpone_penalty
        self.not_before = not_before or {}
        self.max_two_meetings = max_two_meetings
        self.meeting_cost = meeting_cost
        self.fairness = fairness
        self.new_members = set(new_members)
        self.learning_weight = learning_weight
        self.waiting_target = None
        self.levels = []  # fairness='lex': (name, objective, expression held afterwards), in order
        self.max_waiting = max_waiting
        self.min_per_member = min_per_member
        self.planned_next = {p for p, m in data.current.items()
                             if next_meeting and m == next_meeting and p in data.reviewers}
        self.max_per_member = max_per_member
        self.soft_max_per_member = soft_max_per_member
        self.soft_max_weight = soft_max_weight
        self.rotate_wait = rotate_wait
        self.first_meeting_rule = first_meeting_rule
        self.target = target_per_meeting or {}
        self.target_weight = target_weight
        self.open_meeting_size = open_meeting_size
        self.pair_limit = pair_limit
        self.pair_weight = pair_weight
        self.max_meetings = max_meetings or {}
        self.meetings_slack = meetings_slack
        self.leximin_levels = leximin_levels
        self.reference_burden = reference_burden
        self.carry = carry or {}
        if reference_burden is not None and fairness not in STEP_MODES:
            raise ValueError('reference_burden needs a fairness mode solved in steps')

        self._set_variables()
        self._set_constraints()
        self._set_objective()

    def _allowed(self, p):
        """Meetings a proposal may go to. Meetings one of its members can't attend are left out
        (not held ones: they already happened)."""
        if p in self.fixed_meeting:
            return [self.fixed_meeting[p]]
        away = {m for r in self.data.reviewers[p] for m in self.data.unavailable.get(r, ())} - self.held
        open_meetings = [m for m in self.data.meetings
                         if m not in self.closed and m != self.next_meeting and m not in away]
        if p in self.not_before:
            first = self.data.meetings.index(self.not_before[p])
            open_meetings = [m for m in open_meetings if self.data.meetings.index(m) >= first]
        if p in self.planned_next:  # stays in the next meeting, or is postponed to a later one
            later = self.data.meetings.index(self.next_meeting)
            too_early = (p in self.not_before and later < self.data.meetings.index(self.not_before[p]))
            stay = [self.next_meeting] if self.next_meeting not in away and not too_early else []
            return stay + [m for m in open_meetings if self.data.meetings.index(m) > later]
        return open_meetings

    def _set_variables(self):
        data = self.data
        self.allowed = {p: self._allowed(p) for p in data.reviewers}
        # Slots of each meeting: up to the number of proposals that may go there, and at most the
        # size limit of the meeting.
        candidates = {m: [p for p in data.reviewers if m in self.allowed[p]] for m in data.meetings}
        limit = {m: self.max_per_meeting if m in self.closed or not self.open_meeting_size
                 else min(self.max_per_meeting, self.open_meeting_size) for m in data.meetings}
        self.slots = {m: list(range(1, min(limit[m], len(candidates[m])) + 1)) for m in data.meetings}
        self.candidates = candidates

        def slots_of(p, m):  # a proposal of a held meeting has only its known slot
            return [data.fixed_position[p]] if p in data.fixed_position else self.slots[m]
        self.x = {(p, m, k): self.m.addVar(vtype=GRB.BINARY, name=f'x[{p},{m},{k}]')
                  for p in data.reviewers for m in self.allowed[p] for k in slots_of(p, m)}
        # Meetings each member may have to attend: those some proposal of theirs may go to.
        self.meetings_of = {r: [m for m in data.meetings
                                if any(m in self.allowed[p] for p in data.proposals_of(r))]
                            for r in data.members}
        pairs = [(r, m) for r in data.members for m in self.meetings_of[r]]
        self.a = {(r, m): self.m.addVar(vtype=GRB.BINARY, name=f'a[{r},{m}]') for r, m in pairs}
        self.leave = {(r, m): self.m.addVar(lb=0, name=f'leave[{r},{m}]') for r, m in pairs}
        self.z = self.m.addVar(lb=0, name='z')

    def _placed(self, p, m):
        """1 if proposal p is in meeting m (linear expression)."""
        return quicksum(self.x[p, m, k] for k in self.slots[m] if (p, m, k) in self.x)

    def _slot(self, p, m):
        """Slot of proposal p in meeting m, or 0 if it is not there (linear expression)."""
        return quicksum(k * self.x[p, m, k] for k in self.slots[m] if (p, m, k) in self.x)

    def _limited(self, r):
        """Meetings where the number of member r's proposals is still a decision: not closed, and
        not when every proposal of r that may go there is fixed to it (e.g. the staff's meetings)."""
        return [m for m in self.meetings_of[r] if m not in self.closed
                and any(len(self.allowed[p]) > 1 for p in self.data.proposals_of(r) if m in self.allowed[p])]

    def _own(self, r, m):
        """Number of member r's proposals in meeting m (linear expression)."""
        return quicksum(self._placed(p, m) for p in self.data.proposals_of(r) if m in self.allowed[p])

    def interchangeable_meetings(self):
        """Groups of open meetings that the model can't tell apart: the same proposals may go to
        them, and nothing in the model depends on their order. Any schedule can then have its
        meetings in a group swapped without changing the objective."""
        data = self.data
        if self.pair_limit or self.max_two_meetings or self.rotate_wait is not None:  # order matters
            return []
        first = data.meetings[0]
        free = [m for m in data.meetings if m not in self.closed and m != self.next_meeting
                and not (self.first_meeting_rule and m == first)]
        learning = (self.fairness == 'bands' or self.fairness in STEP_MODES) and self.new_members
        early = set(data.meetings[:len(data.meetings) // 2]) if learning else set()
        groups = defaultdict(list)
        for m in free:
            groups[(frozenset(self.candidates[m]), m in early)].append(m)
        return [ms for ms in groups.values() if len(ms) > 1]

    def _set_constraints(self):
        data, x = self.data, self.x
        # Every proposal is discussed exactly once.
        self.m.addConstrs((quicksum(self._placed(p, m) for m in self.allowed[p]) == 1
                           for p in data.reviewers), name='once')
        # One proposal per slot, and slots are filled from the start without gaps.
        self.filled = {}
        for m in data.meetings:
            filled = {k: quicksum(x[p, m, k] for p in self.candidates[m] if (p, m, k) in x)
                      for k in self.slots[m]}
            self.filled[m] = filled
            self.m.addConstrs((filled[k] <= 1 for k in self.slots[m]), name=f'slot[{m}]')
            self.m.addConstrs((filled[k + 1] <= filled[k] for k in self.slots[m][:-1]),
                              name=f'nogap[{m}]')
        # Symmetry: in a group of interchangeable meetings, order the meetings by the first of
        # their proposals (in a fixed order of proposals). A proposal may then only go to a later
        # meeting of the group if an earlier proposal is in the meeting just before it. This keeps
        # one of the many equivalent schedules and removes the rest.
        # earlier[m][i] counts the first i proposals placed in meeting m, built up one proposal at a
        # time so each constraint stays short.
        for group in self.interchangeable_meetings():
            proposals = sorted(self.candidates[group[0]])
            earlier = {}
            for m in group[:-1]:
                earlier[m] = [0]
                for i, p in enumerate(proposals):
                    count = self.m.addVar(lb=0, name=f'earlier[{m},{i + 1}]')
                    self.m.addConstr(count == earlier[m][-1] + self._placed(p, m), name=f'earlier[{m},{i + 1}]')
                    earlier[m].append(count)
            for before, m in zip(group, group[1:]):
                for i, p in enumerate(proposals):
                    self.m.addConstr(self._placed(p, m) <= earlier[before][i], name=f'symmetry[{p},{m}]')
        # A member has at most max_per_member proposals in one meeting (where that is a decision).
        if self.max_per_member:
            for r in data.members:
                for m in self._limited(r):
                    self.m.addConstr(self._own(r, m) <= self.max_per_member, name=f'per_member[{r},{m}]')
        # Each member attends at most max_meetings[r] meetings over the round.
        for r, limit in self.max_meetings.items():
            if r in data.members:
                self.m.addConstr(quicksum(self.a[r, m] for m in self.meetings_of[r]) <= limit,
                                 name=f'max_meetings[{r}]')
        # A member who attends an open meeting has at least min_per_member own proposals there
        # (nobody comes for a single proposal). Exempt: the first meeting (one each), held meetings,
        # and the next meeting, whose agenda is already announced.
        if self.min_per_member:
            first = data.meetings[0]
            for r in data.members:
                for m in set(self.meetings_of[r]) - self.closed - {first, self.next_meeting}:
                    self.m.addConstr(self._own(r, m) >= self.min_per_member * self.a[r, m],
                                     name=f'min_own[{r},{m}]')
        # At most max_two_meetings own proposals in any two consecutive meetings (not both closed).
        if self.max_two_meetings:
            for r in data.members:
                for m, nxt in zip(data.meetings, data.meetings[1:]):
                    if m in self.closed and nxt in self.closed:
                        continue
                    self.m.addConstr(self._own(r, m) + self._own(r, nxt) <= self.max_two_meetings,
                                     name=f'two[{r},{m}]')
        # Shorter meetings: at most open_meeting_size proposals in each meeting that is not closed.
        if self.open_meeting_size:
            for m in set(data.meetings) - self.closed:
                self.m.addConstr(quicksum(self._placed(p, m) for p in self.candidates[m])
                                 <= self.open_meeting_size, name=f'meeting_size[{m}]')
        # First meeting: everyone attends, with exactly one proposal each.
        first = data.meetings[0]
        if self.first_meeting_rule and first not in self.closed:
            for r in data.members:
                self.m.addConstr(quicksum(self._placed(p, first) for p in data.proposals_of(r)) == 1,
                                 name=f'first_meeting[{r}]')
        # Members can't attend meetings they are unavailable for: _allowed leaves those meetings
        # out for their proposals, so there is nothing to add here.
        held = self.held
        # A member with a conflict of interest should not be present when that proposal is
        # discussed: either they are not at the meeting, or they have already left. This is a soft
        # rule: two members with crossed conflicts in the same meeting can't both be satisfied, so
        # each exception coi_present[p, r, m] = 1 is allowed but penalised in the objective.
        # Only where the member can be in that meeting at all (otherwise there is nothing to avoid).
        self.coi_present = {}
        for p, conflicted in data.coi.items():
            for r in conflicted:
                for m in set(self.allowed[p]) - held:
                    if (r, m) not in self.leave:
                        continue
                    big_m = len(self.slots[m]) + 1
                    v = self.m.addVar(vtype=GRB.BINARY, name=f'coi_present[{p},{r},{m}]')
                    self.coi_present[p, r, m] = v
                    self.m.addConstr(self._slot(p, m) >= self.leave[r, m] + 1
                                     - big_m * (1 - self._placed(p, m)) - big_m * v,
                                     name=f'coi[{p},{r},{m}]')
        # A member attends a meeting with any of their proposals, and stays until the last one.
        for r in data.members:
            for p in data.proposals_of(r):
                for m in self.allowed[p]:
                    self.m.addConstr(self.a[r, m] >= self._placed(p, m), name=f'attend[{r},{p},{m}]')
                    self.m.addConstr(self.leave[r, m] >= self._slot(p, m), name=f'leave[{r},{p},{m}]')
            for m in self.meetings_of[r]:
                own = self._own(r, m)
                # Members don't attend meetings without any of their proposals.
                self.m.addConstr(self.a[r, m] <= own, name=f'noattend[{r},{m}]')
                # Stronger bounds: own proposals take different slots, so a member with j of them
                # can't leave before slot j; and nobody stays in a meeting they don't attend.
                self.m.addConstr(self.leave[r, m] >= own, name=f'leave_own[{r},{m}]')
                self.m.addConstr(self.leave[r, m] <= len(self.slots[m]) * self.a[r, m],
                                 name=f'leave_attend[{r},{m}]')
        if self.fairness in BAND_MODES:
            self._exact_leave()
        if self.rotate_wait is not None:
            self._rotation()

    def _exact_leave(self):
        """Tie leave[r, m] to the slot of r's last proposal in m, not only bound it from below.
        Most objectives minimise leave anyway, so the lower bounds suffice; the equity bands do not
        (they reward moving a member's waiting into a band, which raising leave above the real last
        slot would do with phantom waiting). last[r, p, m] = 1 picks the proposal whose slot leave
        may not exceed; one is picked in each meeting r attends."""
        for r in self.data.members:
            for m in self.meetings_of[r]:
                own = [p for p in self.data.proposals_of(r) if m in self.allowed[p]]
                big_m = len(self.slots[m])
                last = {}
                for p in own:
                    last[p] = self.m.addVar(vtype=GRB.BINARY, name=f'last_own[{r},{p},{m}]')
                    self.m.addConstr(last[p] <= self._placed(p, m), name=f'last_own_placed[{r},{p},{m}]')
                    self.m.addConstr(self.leave[r, m] <= self._slot(p, m) + big_m * (1 - last[p]),
                                     name=f'leave_exact[{r},{p},{m}]')
                self.m.addConstr(quicksum(last.values()) == self.a[r, m], name=f'last_own[{r},{m}]')

    def _rotation(self):
        """Rotation, as in APAP where the doctor who was on call goes home first: the members of the
        last proposal of a meeting wait at most rotate_wait proposals of others at the next meeting,
        if they attend it. For held meetings the last proposal is known; otherwise
        last[p, m] >= placed(p, m) - (size(m) - slot(p, m)), which is 1 exactly when p is in m at its
        last slot (size(m) is the number of proposals in m)."""
        data, x = self.data, self.x
        for m, nxt in zip(data.meetings, data.meetings[1:]):
            if nxt in self.held or (self.rotate_wait < 0 and nxt == self.next_meeting):
                continue
            size = None
            if m not in self.held:
                size = self.m.addVar(lb=0, name=f'size[{m}]')
                self.m.addConstr(size == quicksum(self.filled[m].values()), name=f'size[{m}]')
            for p in self.candidates[m]:
                slots = [k for k in self.slots[m] if (p, m, k) in x]
                if not slots:
                    continue
                if p in data.fixed_position:  # held: last if no proposal comes after it
                    k = data.fixed_position[p]
                    if any(data.fixed_meeting.get(q) == m and data.fixed_position.get(q, 0) > k
                           for q in data.fixed_position):
                        continue
                    last = 1
                else:
                    last = self.m.addVar(lb=0, ub=1, name=f'last[{p},{m}]')
                    self.m.addConstr(last >= self._placed(p, m) - size + self._slot(p, m), name=f'last[{p},{m}]')
                for r in data.reviewers[p]:
                    if (r, nxt) not in self.leave:
                        continue
                    if self.rotate_wait < 0:  # last out here: no meeting next time
                        self.m.addConstr(self.a[r, nxt] <= 1 - last, name=f'rotate[{p},{r},{m}]')
                        continue
                    big_m = len(self.slots[nxt])
                    waiting = self.leave[r, nxt] - self._own(r, nxt)
                    self.m.addConstr(waiting <= self.rotate_wait + big_m * (1 - last),
                                     name=f'rotate[{p},{r},{m}]')

    def burden(self, r):
        """Commitment (alpha per meeting attended) plus waiting (slot of the last proposal)."""
        return quicksum(self.alpha[r] * self.a[r, m] + self.leave[r, m] for m in self.meetings_of[r])

    def unpaid(self, r):
        """The burden the fairness steps compare: alpha per meeting attended plus waiting (proposals
        of others sat through), plus what is carried over from earlier rounds. Own proposals are
        paid work and are not counted."""
        return (self.burden(r) - len(self.data.proposals_of(r))) + self.carry.get(r, 0.0)

    def _ordered_levels(self, waiting):
        """Leximin by Ogryczak's ordered min-max: step k minimises the sum of the k largest burdens,
        k*t + sum_r d[r] with d[r] >= unpaid(r) - t, d >= 0 (at the optimum t is the k-th largest).
        Holding that expression afterwards keeps the k largest burdens at most that sum, so each
        later step can only lower the burdens below them. Returns the steps."""
        members = self.data.members
        burden = {r: self.unpaid(r) for r in members}
        levels = []
        count = min(self.leximin_levels or len(members), len(members))
        for k in range(1, count + 1):
            t = self.m.addVar(lb=-GRB.INFINITY, name=f'kth[{k}]')
            d = {r: self.m.addVar(lb=0, name=f'above_kth[{k},{r}]') for r in members}
            for r in members:
                self.m.addConstr(d[r] >= burden[r] - t, name=f'ordered[{k},{r}]')
            top = k * t + quicksum(d.values())
            levels.append((f'top{k}', top + 1e-4 * waiting, top))
        return levels

    def _equity_bands(self, bands=(1, 0.5, 0.2)):
        """The APAP equity measure for the panel: the sum over bands eps of eps times the number of
        members whose waiting per meeting attended is within eps of a common target c. The target
        is a free variable.

        Waiting per meeting is waiting[r] / attended[r], where attended[r] = sum of a[r, m] is a
        decision. The band |waiting[r] - c * attended[r]| <= eps * attended[r] is kept linear with
        t[r, m] = c * a[r, m] (exact, as a[r, m] is binary and c is bounded).
        """
        data, slots = self.data, self.max_per_meeting
        self.waiting_target = self.m.addVar(lb=0, ub=slots, name='waiting_target')
        big_m = slots * len(data.meetings)
        equity = 0
        for r in data.members:
            n = len(data.proposals_of(r))
            waiting = quicksum(self.leave[r, m] for m in self.meetings_of[r]) - n
            attended = quicksum(self.a[r, m] for m in self.meetings_of[r])
            share = 0  # c * attended[r]
            for m in self.meetings_of[r]:
                t = self.m.addVar(lb=0, ub=slots, name=f'target_share[{r},{m}]')
                self.m.addConstr(t <= slots * self.a[r, m])
                self.m.addConstr(t <= self.waiting_target)
                self.m.addConstr(t >= self.waiting_target - slots * (1 - self.a[r, m]))
                share += t
            for eps in bands:
                y = self.m.addVar(vtype=GRB.BINARY, name=f'within[{eps},{r}]')
                self.m.addConstr(waiting - share <= eps * attended + big_m * (1 - y), name=f'band_hi[{eps},{r}]')
                self.m.addConstr(share - waiting <= eps * attended + big_m * (1 - y), name=f'band_lo[{eps},{r}]')
                equity += eps * y
        return equity

    def _learning(self):
        """Proposals of others that new members sit through in the first half of the round (meetings
        still open), when they stay longer to learn anyway."""
        early = [m for m in self.data.meetings[:len(self.data.meetings) // 2] if m not in self.closed]
        total = 0
        for r in self.new_members & set(self.data.members):
            for m in early:
                if (r, m) in self.leave:
                    total += self.leave[r, m] - self._own(r, m)
        return total

    def _set_objective(self):
        # Fairness, the worst-off member by
        #   proposal: burden (commitment + waiting) per own proposal;
        #   total:    total waiting over the round, not divided by anything, so the worst case leads;
        #   unpaid:   commitment + waiting over the round, not divided by anything. Own proposals
        #             are paid work and cost nothing; attending and waiting are unpaid, so nobody
        #             should carry more of them because they review more proposals.
        # Waiting = slots stayed minus own proposals = proposals of others sat through.
        for r in self.data.members:
            n = len(self.data.proposals_of(r))
            waiting = quicksum(self.leave[r, m] for m in self.meetings_of[r]) - n
            if self.max_waiting is not None:  # nobody waits longer than in a reference plan
                self.m.addConstr(waiting <= self.max_waiting, name=f'max_waiting[{r}]')
            if self.fairness == 'total':
                self.m.addConstr(waiting <= self.z, name=f'fair[{r}]')
            elif self.fairness == 'unpaid':
                self.m.addConstr(self.burden(r) - n <= self.z, name=f'fair[{r}]')
            elif self.fairness in ('lexmax', 'lexboth'):
                self.m.addConstr(waiting <= self.z, name=f'fair[{r}]')  # z: the longest waiting
            elif self.fairness == 'lexburden':  # z: the largest unpaid burden
                self.m.addConstr(self.unpaid(r) <= self.z, name=f'fair[{r}]')
            elif self.fairness in ('bands', 'sum', 'lex', 'lexsum', 'leximin'):
                pass  # no worst-off member: equity is the band count below, or not counted at all
            else:
                self.m.addConstr(self.burden(r) <= self.z * n, name=f'fair[{r}]')
        total = quicksum(self.burden(r) for r in self.data.members)
        # Soft target: in each open meeting a member attends, their number of own proposals should
        # be close to their target. dev[r, m] >= |proposals - target * attends|.
        deviation = 0
        if self.target and self.target_weight:
            dev = {}
            for r in self.data.members:
                for m in set(self.meetings_of[r]) - self.closed:
                    own, goal = self._own(r, m), self.target[r] * self.a[r, m]
                    dev[r, m] = self.m.addVar(lb=0, name=f'target_dev[{r},{m}]')
                    self.m.addConstr(dev[r, m] >= own - goal, name=f'target_over[{r},{m}]')
                    self.m.addConstr(dev[r, m] >= goal - own, name=f'target_under[{r},{m}]')
            deviation = quicksum(dev.values()) / len(self.data.members)
        # Soft limit on reading in two consecutive meetings: excess[r, m] >= own(m) + own(next) - limit.
        excess = 0
        if self.pair_limit and self.pair_weight:
            meetings = self.data.meetings
            over = self.m.addVars(self.data.members, meetings[:-1], lb=0, name='pair_excess')
            for r in self.data.members:
                own = {m: self._own(r, m) for m in meetings}
                for m, nxt in zip(meetings, meetings[1:]):
                    if m in self.closed and nxt in self.closed:
                        continue
                    self.m.addConstr(over[r, m] >= own[m] + own[nxt] - self.pair_limit,
                                     name=f'pair[{r},{m}]')
            excess = over.sum() / len(self.data.members)
        # Soft cap: over[r, m] >= own proposals - soft_max_per_member, in the same meetings.
        above_cap = 0
        if self.soft_max_per_member and self.soft_max_weight:
            over = {}
            for r in self.data.members:
                for m in self._limited(r):
                    over[r, m] = self.m.addVar(lb=0, name=f'above_cap[{r},{m}]')
                    self.m.addConstr(over[r, m] >= self._own(r, m) - self.soft_max_per_member,
                                     name=f'above_cap[{r},{m}]')
            above_cap = quicksum(over.values()) / len(self.data.members)
        postponed = quicksum(1 - self._placed(p, self.next_meeting) for p in self.planned_next)
        # bands: maximise equity, plus the reward for new members waiting early in the round.
        # sum: no fairness term, only the total burden (least waiting overall, whoever carries it).
        if self.fairness in STEP_MODES:
            # In steps (see solve): each step keeps what the steps before it reached.
            #   1. meetings: the fewest meetings attended, with own proposals per meeting close
            #      to each member's target (total deviation, so a meeting saved by overloading
            #      another one does not pay), and the rule penalties (a conflicted member present,
            #      a postponed proposal);
            #   2. equity:   the most members within the bands of the common waiting target. Many
            #      targets give the same equity, so a tiny weight on waiting (less than the
            #      smallest band) already steers this step to a low target;
            #      With 'lexmax' the second step is instead
            #      worst:    the shortest possible waiting for the member who waits the longest;
            #      and with 'lexboth' the equity step is followed by the worst step;
            #      With 'leximin' the second step is a series: the largest burden, the sum of the two
            #      largest, and so on (see _ordered_levels);
            #   3. waiting:  the least total waiting, new members waiting early in the round.
            # With a reference plan, a step 0 first makes the total excess burden over that plan
            # as small as possible (zero when nobody needs to be worse off).
            waiting = quicksum(self.leave.values()) - sum(len(trio) for trio in self.data.reviewers.values())
            meetings = (quicksum(self.a.values()) + self.postpone_penalty * postponed
                        + self.coi_penalty * quicksum(self.coi_present.values())
                        + len(self.data.members) * (self.target_weight * deviation + self.pair_weight * excess
                                                    + self.soft_max_weight * above_cap))
            least = waiting - self.learning_weight * self._learning()
            fairness_steps = []
            if self.fairness in ('lex', 'lexboth'):
                equity = self._equity_bands()
                fairness_steps.append(('equity', -equity + 1e-4 * waiting, -equity))
            if self.fairness in ('lexmax', 'lexboth', 'lexburden'):
                fairness_steps.append(('worst', self.z + 1e-4 * waiting, 1.0 * self.z))
            if self.fairness == 'leximin':
                fairness_steps += self._ordered_levels(waiting)
            self.levels = [('meetings', meetings, meetings)] + fairness_steps + [('waiting', least, least)]
            if self.reference_burden is not None:
                excess = []
                for r in self.data.members:
                    if r not in self.reference_burden:
                        continue
                    e = self.m.addVar(lb=0, name=f'excess_reference[{r}]')
                    self.m.addConstr(e >= self.unpaid(r) - self.reference_burden[r] - self.carry.get(r, 0.0),
                                     name=f'excess_reference[{r}]')
                    excess.append(e)
                excess = quicksum(excess)
                self.levels.insert(0, ('reference', excess + 1e-4 * waiting, excess))
            self.m.setObjective(self.levels[0][1], GRB.MINIMIZE)
            return
        fair = 0 if self.fairness == 'sum' else self.z
        if self.fairness == 'bands':
            fair = -self._equity_bands() - self.learning_weight * self._learning()
        self.m.setObjective(fair + self.total_weight * total / len(self.data.members)
                            + self.postpone_penalty * postponed
                            # A large cost per meeting attended keeps the number of meetings low first.
                            + self.meeting_cost * quicksum(self.a.values()) / len(self.data.members)
                            + self.coi_penalty * quicksum(self.coi_present.values())
                            + self.target_weight * deviation + self.pair_weight * excess
                            + self.soft_max_weight * above_cap, GRB.MINIMIZE)

    def set_start(self, agenda):
        """Warm start from an agenda {proposal: (meeting, slot)}, e.g. a solution with fewer freedoms.

        Proposals whose place in the agenda breaks a rule of this model (a meeting it may not go
        to, or too many proposals for a member or a meeting) are left out of the start, and Gurobi
        completes the partial start itself. The rest of the agenda is kept.
        """
        agenda = self._canonical(agenda)
        drop = {p for p, (m, _) in agenda.items() if p in self.data.reviewers and m not in self.allowed[p]}
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

    def _canonical(self, agenda):
        """The same agenda with the meetings of each interchangeable group reordered as the
        symmetry constraints require (by their first proposal; empty meetings last)."""
        agenda = dict(agenda)
        for group in self.interchangeable_meetings():
            order = sorted(self.candidates[group[0]])
            rank = {p: i for i, p in enumerate(order)}
            first = {m: min((rank[p] for p, (pm, _) in agenda.items() if pm == m and p in rank),
                            default=len(order)) for m in group}
            relabel = dict(zip(sorted(group, key=lambda m: first[m]), group))
            agenda = {p: (relabel.get(m, m), k) for p, (m, k) in agenda.items()}
        return agenda

    def _solve_in_steps(self):
        """Hierarchical optimisation: minimise each level in turn, then hold it at the value reached
        while the next level is optimised. The time limit is split between the levels. Returns the
        value and bound of each level."""
        time_limit, reached = self.m.Params.TimeLimit, []
        # The meetings step gets 40% of the time (the reference step, if any, 10%); the other steps
        # share the rest equally.
        names = [name for name, _, _ in self.levels]
        first = {'reference': 0.1, 'meetings': 0.4}
        rest = (1 - sum(first.get(n, 0) for n in names)) / max(1, sum(n not in first for n in names))
        shares = [first.get(n, rest) for n in names]
        for (name, objective, held), share in zip(self.levels, shares):
            self.m.setObjective(objective, GRB.MINIMIZE)
            self.m.Params.TimeLimit = share * time_limit
            self.m.optimize()
            if self.m.SolCount == 0:
                raise RuntimeError(f'No solution found at level {name} (status {self.m.Status}).')
            value = held.getValue()
            gap = self.m.MIPGap if self.m.IsMIP else 0.0
            reached.append({'level': name, 'value': value, 'bound': self.m.ObjBound, 'gap': gap})
            print(f"level {name}: value {value:.3f}, bound {self.m.ObjBound:.3f}, gap {gap:.1%}")
            # Gurobi accepts binaries within 1e-5 of 0 or 1, so a held value can come back a little
            # below the true one (6.99998 for 7). Holding it that tightly can make the next step
            # infeasible, so hold with a tolerance well above that, but below any real difference.
            tolerance = 1e-4 * max(1.0, abs(value))
            slack = self.meetings_slack if name == 'meetings' else 0.0
            self.m.addConstr(held <= value + slack + tolerance, name=f'hold[{name}]')
        return reached

    def solve(self):
        levels = None
        if self.levels:
            levels = self._solve_in_steps()
        else:
            self.m.optimize()
        if self.m.SolCount == 0:
            raise RuntimeError(f'No solution found (status {self.m.Status}).')
        agenda = sorted((m, k, p) for (p, m, k), var in self.x.items() if var.X > 0.5)
        # Measures are recomputed from the agenda, not read from leave or a, so they show what the
        # plan actually does whatever slack the model variables have.
        members = member_measures(self.data, {p: (m, k) for m, k, p in agenda}, self.alpha)
        for row in members:
            row['carry'] = self.carry.get(row['member'], 0.0)
        self.solution = {
            'agenda': [{'meeting': m, 'position': k, 'application': p} for m, k, p in agenda],
            'members': members,
            'fairness': fairness_metrics(members),
            'status': self.m.Status, 'objective': self.m.ObjVal, 'gap': self.m.MIPGap,
            'waiting_target': self.waiting_target.X if self.waiting_target is not None else None,
            'levels': levels,
            'postponed': sorted(p for p in self.planned_next
                                if self._placed(p, self.next_meeting).getValue() < 0.5),
            'coi_present': [{'application': p, 'member': r, 'meeting': m}
                            for (p, r, m), v in self.coi_present.items() if v.X > 0.5],
        }
        return self.solution

    def save(self, out_prefix):
        os.makedirs(os.path.dirname(out_prefix) or '.', exist_ok=True)
        columns = {'agenda': ['meeting', 'position', 'application'],
                   'members': ['member', 'proposals', 'meetings', 'leave_slots', 'waiting',
                               'waiting_per_meeting', 'waiting_per_proposal', 'alpha', 'burden',
                               'burden_per_proposal', 'carry'],
                   'coi_present': ['application', 'member', 'meeting'],
                   'fairness': ['metric', 'value'],
                   'levels': ['level', 'value', 'bound', 'gap']}
        for name, fields in columns.items():
            if name == 'fairness':
                rows = [{'metric': k, 'value': v} for k, v in self.solution['fairness'].items()]
            elif name == 'levels':
                rows = self.solution['levels'] or []
            else:
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
    parser.add_argument('--fairness', choices=['proposal', 'total', 'unpaid', 'bands', 'sum', *STEP_MODES],
                        default='proposal',
                        help="worst-off member by burden per proposal, by total waiting ('total'), or by "
                             "commitment plus waiting, undivided ('unpaid'); or the APAP measure: members "
                             "within bands of a common target for waiting per meeting ('bands'); or no fairness at "
                             "all, only the least total burden ('sum'); or in steps: fewest meetings, then most "
                             "equity by the bands, then least waiting ('lex'); or the same steps with the longest "
                             "waiting of any member as the second step ('lexmax'), with both ('lexboth'), or with "
                             "the largest alpha * meetings + waiting ('lexburden'); or no fairness step, fewest "
                             "meetings then least total waiting ('lexsum'); or leximin of alpha * meetings + "
                             "waiting in steps after the meetings step ('leximin', see --leximin-levels)")
    parser.add_argument('--leximin-levels', type=int,
                        help="with --fairness leximin: how many of the largest burdens to fix in turn (0: all)")
    parser.add_argument('--meetings-slack', type=float,
                        help='step modes: hold the meetings step at its value plus this slack, so later '
                             'steps may trade a meeting attended for alpha slots less waiting')
    parser.add_argument('--no-worse-than',
                        help='step modes: agenda CSV of a reference plan (e.g. the staff\'s meetings); a '
                             'first step keeps every member\'s burden at most theirs there where possible')
    parser.add_argument('--carry', help='CSV (member, burden) of burden carried over from earlier rounds')
    parser.add_argument('--coi-penalty', type=float,
                        help='objective cost each time a conflicted member must step out and come back')
    parser.add_argument('--postpone-penalty', type=float,
                        help='objective cost of each proposal postponed from the next meeting')
    parser.add_argument('--rotate-wait', type=int,
                        help='rotation: members of the last proposal of a meeting wait at most this many '
                             'proposals of others at the next meeting they attend (if it is the next one); '
                             '-1: they do not attend the next meeting')
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
                 'postpone_penalty', 'leximin_levels', 'meetings_slack'):
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
    if args.target or args.fairness in STEP_MODES:  # in steps, the targets are part of the first step
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

    reference, carry = None, None
    if args.carry:
        carry = read_carry(args.carry)
        print(f'burden carried over for {len(carry)} members')
    if args.no_worse_than:
        rows = member_measures(data, read_agenda(args.no_worse_than), float(config['alpha']))
        reference = {row['member']: row['burden'] for row in rows}
        print(f'reference plan {args.no_worse_than}: largest burden {max(reference.values()):g}')
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
                               fairness=args.fairness, max_waiting=args.max_waiting,
                               new_members=(read_new_members(config['members'])
                                            if args.fairness == 'bands' or args.fairness in STEP_MODES
                                            else ()),
                               learning_weight=config.get('learning_weight', 0.001),
                               soft_max_per_member=config.get('soft_max_per_member'),
                               soft_max_weight=config.get('soft_max_weight', 0.0),
                               rotate_wait=args.rotate_wait,
                               meetings_slack=float(config.get('meetings_slack') or 0.0),
                               leximin_levels=config.get('leximin_levels', 3),
                               reference_burden=reference, carry=carry)
    model.m.Params.MIPFocus = args.mip_focus
    if args.start:
        model.set_start(read_agenda(args.start))
    solution = model.solve()
    model.save(args.out)
    if solution['waiting_target'] is not None:
        print(f"target waiting per meeting: {solution['waiting_target']:.2f}")
    fair = solution['fairness']
    print(f"burden: largest {fair['max_burden']:g}, gini {fair['gini_burden']}, total waiting "
          f"{fair['total_waiting']}, rho(meetings, waiting) {fair['rho_meetings_waiting']}, "
          f"inverted pairs {fair['inverted_pairs']}")
    if reference is not None:
        worse = [row['member'] for row in solution['members'] if row['burden'] > reference[row['member']] + 1e-6]
        print(f"worse off than in the reference plan: {', '.join(worse) or 'nobody'}")
    print(f"objective {solution['objective']:.3f}, gap {solution['gap']:.1%}, "
          f"conflicted members present: {len(solution['coi_present'])}, "
          f"postponed from the next meeting: {solution['postponed'] or 'none'}")


if __name__ == '__main__':
    main()
