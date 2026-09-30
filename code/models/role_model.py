"""
Who reviews which proposal, and in which role: the first of the three decisions (see the book).

The meeting of each proposal is taken as given (from an agenda, e.g. the staff's meetings with a
fair order), and meetings that have been held keep their reviewers and roles. Two modes:

    roles   Keep the three members on each proposal, but choose which of them is the editor,
            and which reader speaks second (reader 1) and last (reader 2).
            New members may not be editor until they have been reader on the first part of their
            proposals (in time order).
    assign  Assume every member can review every proposal. Choose all three members and the editor,
            except members with a conflict of interest, who may never review the proposal.
            New members follow the same editor rules as in 'roles'.

Pay (see the book): base fee f0 plus fE per editor role and fL per reader role. Assuming every
proposal takes the same time, including waiting in the meeting, fair pay means equal pay per
proposal. Objectives:

    roles   minimise the spread (max - min) of pay per proposal, in thousand ISK;
    assign  minimise the spread of the number of proposals and of editor roles per member;

and in both, with smaller weights, give everyone similar room in the discussion (for each member,
reader 1 and reader 2 roles as equal as possible; reader 1 speaks second, reader 2 last) and avoid a
member being editor on several proposals in the same meeting (editor roles spread over the round).

Usage (from code/):
    python -m models.role_model ../data/tdf/panel.csv --mode roles \
        --agenda ../data/tdf/results/current_agenda.csv --out ../data/tdf/results/roles
"""
import argparse
import csv
import math
import os
from collections import defaultdict

import yaml
from gurobipy import GRB, Model, quicksum  # pylint: disable=no-name-in-module

from models.panel_model import read_agenda, read_new_members, read_panel

PAY = {'start': 38000, 'editor': 23000, 'reader': 15000}  # ISK, as in code/panel_workload.R


def time_order(data, agenda):
    """Proposals sorted by (meeting number, agenda position)."""
    return sorted(agenda, key=lambda p: (int(agenda[p][0][1:]), agenda[p][1]))


class RoleModel:
    """
    Decision variables:
        z[p, r]  1 if member r reviews proposal p (fixed to the current reviewers in 'roles' mode)
        y[p, r]  1 if member r is the editor of proposal p
        u[p, r]  1 if member r is reader 1 of proposal p (speaks second)
        over[r, m]  editor roles of r in meeting m beyond the first (spread over the round)
    """

    def __init__(self, data, agenda, mode, new_members=(), new_editor_share=0.15, max_per_member=6,
                 spread_weight=0.0, voice_weight=0.1, time_limit=300, pay=PAY, from_scratch=False):
        self.data, self.agenda, self.mode = data, agenda, mode
        self.pay = pay
        self.m = Model('Roles')
        self.m.Params.TimeLimit = time_limit
        members = data.members
        proposals = [p for p in time_order(data, agenda) if p in data.reviewers]
        self.proposals = proposals
        # From scratch nothing is fixed and meetings are not known yet, so rules that depend on the
        # meeting of a proposal (per-meeting limit, midpoint of a new member) are left to the
        # scheduling model that runs afterwards.
        held = set() if from_scratch else set(data.fixed_position)
        meeting = {p: agenda[p][0] for p in proposals}

        # Who may review p: the current three ('roles'), or anyone without a conflict ('assign').
        if mode == 'roles':
            candidates = {p: list(data.reviewers[p]) for p in proposals}
        else:
            candidates = {p: list(data.reviewers[p]) if p in held
                          else [r for r in members if r not in data.coi.get(p, [])] for p in proposals}
        self.candidates = candidates
        self.z = {(p, r): self.m.addVar(vtype=GRB.BINARY, name=f'z[{p},{r}]')
                  for p in proposals for r in candidates[p]}
        self.y = {(p, r): self.m.addVar(vtype=GRB.BINARY, name=f'y[{p},{r}]')
                  for p in proposals for r in candidates[p]}
        self.u = {(p, r): self.m.addVar(vtype=GRB.BINARY, name=f'u[{p},{r}]')
                  for p in proposals for r in candidates[p]}

        for p in proposals:
            self.m.addConstr(quicksum(self.y[p, r] for r in candidates[p]) == 1, name=f'one_editor[{p}]')
            self.m.addConstr(quicksum(self.u[p, r] for r in candidates[p]) == 1, name=f'one_reader1[{p}]')
            for r in candidates[p]:  # reader 1 reviews the proposal and is not its editor
                self.m.addConstr(self.u[p, r] + self.y[p, r] <= self.z[p, r], name=f'reader1[{p},{r}]')
            self.m.addConstr(quicksum(self.z[p, r] for r in candidates[p]) == 3, name=f'three[{p}]')
            for r in candidates[p]:
                self.m.addConstr(self.y[p, r] <= self.z[p, r], name=f'editor_reviews[{p},{r}]')
            if mode == 'roles' or p in held:
                for r in candidates[p]:
                    self.z[p, r].LB = 1
            if p in held:  # held meetings keep their editor
                editor = data.reviewers[p][0]
                for r in candidates[p]:
                    self.y[p, r].LB = self.y[p, r].UB = int(r == editor)
                    self.u[p, r].LB = self.u[p, r].UB = int(r == data.reviewers[p][1])

        def editors_of(r):
            return quicksum(self.y[p, r] for p in proposals if (p, r) in self.y)

        load = {r: quicksum(self.z[p, r] for p in proposals if (p, r) in self.z) for r in members}
        editors = {r: quicksum(self.y[p, r] for p in proposals if (p, r) in self.y) for r in members}
        self.load, self.editors = load, editors

        # At most max_per_member own proposals in a meeting (only matters when reviewers can change).
        by_meeting = defaultdict(list)
        for p in proposals:
            by_meeting[meeting[p]].append(p)
        if mode == 'assign' and not from_scratch:
            for r in members:
                for mt, ps in by_meeting.items():
                    own = [self.z[p, r] for p in ps if (p, r) in self.z]
                    if own:
                        self.m.addConstr(quicksum(own) <= max_per_member, name=f'per_meeting[{r},{mt}]')

        # New members: no editor role before the midpoint of their own meetings (which may be later
        # than the middle of the round if their meetings come late), and after that at most
        # new_editor_share of their proposals as editor.
        # Their meetings are taken from the current plan, also in 'assign' mode where their proposals
        # can change. The share applies to the proposals they end up with (load is a variable there).
        self.new_members = set(new_members)
        for r in self.new_members:
            current = [p for p in proposals if r in data.reviewers[p]]
            their_meetings = sorted({meeting[p] for p in current}, key=lambda m: int(m[1:]))
            before_mid = set() if from_scratch else set(their_meetings[:len(their_meetings) // 2])
            for p in proposals:
                if (p, r) in self.y and p not in held and meeting[p] in before_mid:
                    self.y[p, r].UB = 0
            held_editor = sum(1 for p in current if p in held and data.reviewers[p][0] == r)
            self.m.addConstr(editors_of(r) <= new_editor_share * load[r] + 0.5 + held_editor,
                             name=f'new_editor_share[{r}]')

        # Editor roles spread over the round: penalise more than one editor role per meeting
        # (off by default; future work).
        self.over = {}
        for r in (members if spread_weight else []):
            for mt, ps in by_meeting.items():
                own = [self.y[p, r] for p in ps if (p, r) in self.y]
                if len(own) > 1:
                    v = self.m.addVar(lb=0, name=f'over[{r},{mt}]')
                    self.m.addConstr(v >= quicksum(own) - 1, name=f'over[{r},{mt}]')
                    self.over[r, mt] = v
        bunching = quicksum(self.over.values()) / len(members)
        reader1 = {r: quicksum(self.u[p, r] for p in proposals if (p, r) in self.u) for r in members}
        reader2 = {r: load[r] - editors[r] - reader1[r] for r in members}
        # From scratch the first meeting is chosen here too: a set of proposals that covers every
        # member exactly once, with no new member as editor. It gives the scheduling model a valid
        # first meeting to start from.
        self.first = {}
        if from_scratch and mode == 'assign':
            self.first = {p: self.m.addVar(vtype=GRB.BINARY, name=f'first[{p}]') for p in proposals}
            for r in members:
                both = []
                for p in proposals:
                    if (p, r) not in self.z:
                        continue
                    v = self.m.addVar(vtype=GRB.BINARY, name=f'first_member[{p},{r}]')
                    self.m.addConstr(v <= self.first[p])
                    self.m.addConstr(v <= self.z[p, r])
                    self.m.addConstr(v >= self.first[p] + self.z[p, r] - 1)
                    both.append(v)
                    if r in self.new_members:
                        self.m.addConstr(self.y[p, r] + self.first[p] <= 1, name=f'first_new[{p},{r}]')
                self.m.addConstr(quicksum(both) == 1, name=f'first_once[{r}]')

        voice_gap = self.m.addVar(lb=0, name='voice_gap')
        for r in members:
            self.m.addConstr(voice_gap >= reader1[r] - reader2[r], name=f'voice_hi[{r}]')
            self.m.addConstr(voice_gap >= reader2[r] - reader1[r], name=f'voice_lo[{r}]')

        if mode == 'roles':
            # Pay per proposal (thousand ISK) is linear in the editor count, as the load is fixed.
            n = {r: len([p for p in proposals if r in candidates[p]]) for r in members}
            per_prop = {r: (pay['start'] + pay['reader'] * n[r] + (pay['editor'] - pay['reader']) * editors[r])
                        / (1000 * n[r]) for r in members if n[r]}
            hi, lo = self.m.addVar(lb=0, name='pay_hi'), self.m.addVar(lb=0, name='pay_lo')
            # Equal pay per proposal among experienced members; new members edit less by design.
            for r, q in per_prop.items():
                if r in self.new_members:
                    continue
                self.m.addConstr(hi >= q, name=f'pay_hi[{r}]')
                self.m.addConstr(lo <= q, name=f'pay_lo[{r}]')
            self.m.setObjective(hi - lo + spread_weight * bunching + voice_weight * voice_gap, GRB.MINIMIZE)
        else:
            n_hi, n_lo = self.m.addVar(lb=0), self.m.addVar(lb=0)
            e_hi, e_lo = self.m.addVar(lb=0), self.m.addVar(lb=0)
            for r in members:
                self.m.addConstr(n_hi >= load[r])
                self.m.addConstr(n_lo <= load[r])
                if r not in self.new_members:  # new members edit less by design
                    self.m.addConstr(e_hi >= editors[r])
                    self.m.addConstr(e_lo <= editors[r])
            self.m.setObjective((n_hi - n_lo) + (e_hi - e_lo) + spread_weight * bunching
                                + voice_weight * voice_gap, GRB.MINIMIZE)

    def solve(self):
        self.m.optimize()
        if self.m.SolCount == 0:
            raise RuntimeError(f'No solution found (status {self.m.Status}).')
        rows = []
        for p in self.proposals:
            chosen = [r for r in self.candidates[p] if self.z[p, r].X > 0.5]
            editor = next(r for r in chosen if self.y[p, r].X > 0.5)
            first = next(r for r in chosen if self.u[p, r].X > 0.5)
            readers = [first, next(r for r in chosen if r not in (editor, first))]
            rows.append({'application': p, 'meeting': self.agenda[p][0], 'position': self.agenda[p][1],
                         'editor': editor, 'reader1': readers[0], 'reader2': readers[1],
                         'first_meeting': int(bool(self.first) and self.first[p].X > 0.5)})
        return rows


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('panel')
    parser.add_argument('--mode', choices=['roles', 'assign'], required=True)
    parser.add_argument('--agenda', required=True, help='agenda CSV giving each proposal its meeting and position')
    parser.add_argument('--config', default=os.path.join(os.path.dirname(__file__), 'panel_model.yml'))
    parser.add_argument('--time-limit', type=float, default=300)
    parser.add_argument('--from-scratch', action='store_true',
                        help='nothing is fixed, not even held meetings (with --mode assign)')
    parser.add_argument('--out', required=True, help='output prefix; writes <out>_panel.csv')
    args = parser.parse_args()

    with open(args.config, encoding='utf-8') as f:
        config = yaml.safe_load(f)
    data = read_panel(args.panel)
    agenda = read_agenda(args.agenda)
    new = read_new_members(config['members'])
    model = RoleModel(data, agenda, args.mode, new_members=new,
                      new_editor_share=config.get('new_editor_share', 0.15),
                      max_per_member=config.get('max_per_member') or 99, time_limit=args.time_limit,
                      from_scratch=args.from_scratch)
    rows = model.solve()
    os.makedirs(os.path.dirname(args.out) or '.', exist_ok=True)
    # Written in the format of panel.csv, so it can be scheduled by models/panel_model.py. From
    # scratch the agenda positions of held meetings are cleared, so nothing is fixed there either.
    with open(args.panel, newline='', encoding='utf-8-sig') as f:
        panel_rows = list(csv.DictReader(f))
    roles = {row['application']: row for row in rows}
    for row in panel_rows:
        if row['application'] in roles:
            for col in ('editor', 'reader1', 'reader2'):
                row[col] = roles[row['application']][col]  # first_meeting only goes to the start agenda
        if args.from_scratch:
            row['position'] = ''
    with open(f'{args.out}_panel.csv', 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=list(panel_rows[0]))
        writer.writeheader()
        writer.writerows(panel_rows)
    if args.from_scratch:
        # Start agenda for the scheduling model: the chosen first meeting, then the staff's meetings
        # for everything else (proposals moved out of the first meeting are left for the solver).
        first = [row['application'] for row in rows if row['first_meeting']]
        first_meeting = min((row['meeting'] for row in rows), key=lambda m: int(m[1:]))
        start = [{'meeting': first_meeting, 'position': k, 'application': p} for k, p in enumerate(first, 1)]
        slots = defaultdict(int)
        for row in sorted(rows, key=lambda r: (int(r['meeting'][1:]), int(r['position']))):
            if row['application'] in first or row['meeting'] == first_meeting:
                continue
            slots[row['meeting']] += 1
            start.append({'meeting': row['meeting'], 'position': slots[row['meeting']],
                          'application': row['application']})
        with open(f'{args.out}_start_agenda.csv', 'w', newline='', encoding='utf-8') as f:
            writer = csv.DictWriter(f, fieldnames=['meeting', 'position', 'application'])
            writer.writeheader()
            writer.writerows(start)
    print(f"objective {model.m.ObjVal:.3f}, gap {model.m.MIPGap:.1%}, {len(rows)} proposals")


if __name__ == '__main__':
    main()
