"""Excel export of a chosen schedule, to send to the funder.

Reads the pseudonymised agenda and panel (codes only) and, from the local, gitignored key and
extract files, maps the codes back to real members and application numbers/titles. The workbook is
the only place the real values appear; it is written under data/tdf/ (gitignored) and never
committed. This script contains no real values.

Sheets (Icelandic): 'Yfirlit' (key figures, per-member table, moved and unscheduled proposals), then
one sheet per meeting.

Run from code/:
    python export_plan_xlsx.py --agenda ../data/tdf/results/round4_agenda.csv \
        --members ../data/tdf/results/round4_members.csv --coi ../data/tdf/results/round4_coi_present.csv \

The output defaults to ../data/tdf/results/fundaaaetlun_taeknithrounarsjodur_haust2026.xlsx.
"""
import argparse
import csv
import datetime as dt
from collections import Counter

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

SLOT_MINUTES = 11
START_MINUTES = 16 * 60


def read(path):
    with open(path, newline='', encoding='utf-8-sig') as f:
        return list(csv.DictReader(f))


def slot_time(position, start=START_MINUTES, slot=SLOT_MINUTES):
    minutes = start + (int(position) - 1) * slot
    return f'{minutes // 60}:{minutes % 60:02d}'


def date_text(iso):
    d = dt.date.fromisoformat(iso)
    return f'{d.day}.{d.month}.{d.year}'


def style_sheet(ws, widths, header_row):
    bold = Font(bold=True)
    fill = PatternFill('solid', fgColor='DDE6F0')
    for cell in ws[header_row]:
        if cell.value is not None:
            cell.font = bold
            cell.fill = fill
            cell.alignment = Alignment(wrap_text=True, vertical='center')
    for col, width in enumerate(widths, start=1):
        ws.column_dimensions[get_column_letter(col)].width = width
    for row in ws.iter_rows(min_row=header_row + 1):
        for cell in row:
            cell.alignment = Alignment(wrap_text=True, vertical='top')
    ws.freeze_panes = ws.cell(row=header_row + 1, column=1)
    ws.page_setup.orientation = 'landscape'
    ws.page_setup.fitToWidth = 1
    ws.page_setup.fitToHeight = 0
    ws.sheet_properties.pageSetUpPr.fitToPage = True
    ws.print_title_rows = f'{header_row}:{header_row}'


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument('--agenda', required=True, help='agenda CSV (meeting, position, application)')
    ap.add_argument('--members', required=True, help='members CSV of the same run')
    ap.add_argument('--coi', help='coi_present CSV of the same run (conflicted members present)')
    ap.add_argument('--panel', default='../data/tdf/panel.csv')
    ap.add_argument('--key', default='../data/tdf/panel_key.csv', help='pseudonym key (local, gitignored)')
    ap.add_argument('--raw', default='../data/tdf/TDF2026.csv', help='raw extract with titles and dates (local)')
    ap.add_argument('--meetings', default='M1,M2,M3,M4,M5,M6,M7,M8,M9')
    ap.add_argument('--held', default='M1,M2', help='meetings already held')
    ap.add_argument('--first-open', default='M3', help='the meeting proposals are moved from')
    ap.add_argument('--author', default='Helga Ingimundardóttir, helgaingim@hi.is',
                    help='author name and contact, written to the workbook properties and the Yfirlit sheet')
    ap.add_argument('--out', default='../data/tdf/results/fundaaaetlun_taeknithrounarsjodur_haust2026.xlsx')
    args = ap.parse_args()

    meetings = args.meetings.split(',')
    held = set(args.held.split(','))
    panel = {r['application']: r for r in read(args.panel)}
    agenda = read(args.agenda)
    members = read(args.members)
    coi_present = {(r['application'], r['member']) for r in read(args.coi)} if args.coi else set()

    key = read(args.key)
    app_orig = {r['code']: r['original'] for r in key if r['kind'] == 'application'}
    person = {r['code']: r['original'] for r in key if r['kind'] == 'reviewer'}
    raw = {r['application_id']: r for r in read(args.raw)}

    def who(code):
        return person.get(code, code) if code else ''

    def appl(code):
        number = app_orig.get(code, code)
        title = raw.get(number, {}).get('title', '')
        return f'{number} {title}'.strip()

    # Dates of the meetings: the panel meeting M# is the #th distinct date of the raw extract.
    dates = sorted({r['meeting_date'] for r in raw.values() if r.get('meeting_date')})
    date_of = {f'M{i + 1}': d for i, d in enumerate(dates)}

    placed = {(r['meeting'], int(r['position'])): r['application'] for r in agenda}
    planned = {a: r['meeting'] for a, r in panel.items()}
    scheduled = {r['application'] for r in agenda}
    moved = sorted(a for a, m in planned.items()
                   if m == args.first_open and a in scheduled
                   and not any(r['application'] == a and r['meeting'] == args.first_open for r in agenda))
    unscheduled = sorted(a for a in panel if a not in scheduled)
    moved_to = {r['application']: r['meeting'] for r in agenda if r['application'] in moved}

    wb = Workbook()
    ws = wb.active
    ws.title = 'Yfirlit'
    waiting = [float(m['waiting']) for m in members]
    burden = [float(m['burden']) for m in members]
    rows = [
        ('Samtals bið (raufar)', int(sum(waiting))),
        ('Mesta bið eins fulltrúa (raufar)', int(max(waiting))),
        ('Mesta byrði eins fulltrúa (alfa × fundir + bið)', int(max(burden))),
        ('Lengd rauf (mín.)', SLOT_MINUTES),
    ]
    if args.author:
        wb.properties.creator = args.author
        wb.properties.lastModifiedBy = args.author
        ws.append(['Höfundur', args.author])
        ws.append([])
    ws.append(['Lykiltölur', ''])
    for r in rows:
        ws.append(list(r))
    ws.append([])
    ws.append(['Umsóknir á fundi', 'Fjöldi'])
    count = Counter(r['meeting'] for r in agenda)
    for m in meetings:
        label = f'{m} ({date_text(date_of[m])})' + (' - haldinn' if m in held else '') if m in date_of else m
        ws.append([label, count.get(m, 0)])
    ws.append([])
    ws.append(['Fulltrúi', 'Umsóknir', 'Fundir', 'Bið (raufar)', 'Byrði'])
    member_header = ws.max_row
    for m in sorted(members, key=lambda r: who(r['member'])):
        ws.append([who(m['member']), int(m['proposals']), int(m['meetings']), int(float(m['waiting'])),
                   int(float(m['burden']))])
    ws.append([])
    ws.append([f'Umsóknir færðar af {args.first_open}', 'Nýr fundur'])
    for a in moved:
        ws.append([appl(a), f"{moved_to[a]} ({date_text(date_of[moved_to[a]])})" if moved_to[a] in date_of else moved_to[a]])
    ws.append([])
    ws.append(['Umsóknir sem eiga eftir að fá úthlutun', 'Staða'])
    for a in unscheduled:
        ws.append([appl(a), 'á eftir að úthluta'])
    style_sheet(ws, [58, 16, 12, 14, 12], 1)
    if args.author:
        ws['A1'].font = Font(bold=True)
        ws['A1'].fill = PatternFill(fill_type=None)
    off = 2 if args.author else 0
    for r in (1 + off, 6 + off, member_header):
        for cell in ws[r]:
            if cell.value is not None:
                cell.font = Font(bold=True)
    for row in ws.iter_rows():
        if row[0].value and str(row[0].value).startswith(('Umsóknir færðar', 'Umsóknir sem eiga')):
            for cell in row:
                if cell.value is not None:
                    cell.font = Font(bold=True)
    ws.freeze_panes = None

    header = ['Fundur', 'Dagsetning', 'Röð', 'Tími', 'Umsókn', 'Ritstjóri', '1. lesari', '2. lesari', 'Athugasemd']
    for m in meetings:
        sheet = wb.create_sheet(m)
        if m in held:
            sheet.append([f'{m} - haldinn'])
            sheet['A1'].font = Font(bold=True)
        head_row = sheet.max_row + 1
        sheet.append(header)
        for (mm, pos), a in sorted((k, v) for k, v in placed.items() if k[0] == m):
            p = panel[a]
            notes = []
            if a in moved:
                notes.append(f'færð af {args.first_open}')
            conflicted = [c for c in p['coi'].split(';') if c]
            for c in conflicted:
                if (a, c) in coi_present:
                    notes.append(f'{who(c)} er vanhæf(ur) en mætir á fundinn: víkur þegar umsókn er rædd')
                else:
                    notes.append(f'{who(c)} er vanhæf(ur): ekki á fundinum')
            sheet.append([m, date_text(date_of[m]) if m in date_of else '', pos, slot_time(pos), appl(a),
                          who(p['editor']), who(p['reader1']), who(p['reader2']), '; '.join(notes)])
        style_sheet(sheet, [8, 13, 6, 8, 60, 14, 14, 14, 48], head_row)
    wb.save(args.out)
    print(f'{len(agenda)} scheduled proposals in {len(meetings)} meeting sheets; '
          f'{len(moved)} moved from {args.first_open}; {len(unscheduled)} not scheduled; wrote {args.out}')


if __name__ == '__main__':
    main()
