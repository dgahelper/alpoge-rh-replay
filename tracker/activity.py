"""Build volunteer activity history and chart from public GitHub claim issues."""

import csv
from datetime import datetime, timezone
import json
import math
import os
from pathlib import Path
import re

from submissions import gh_output

TRACKER = Path(__file__).resolve().parent
SERIES = {
    'volunteer': ('Volunteers', '#1d4ed8'),
    'grant': ('Granted claims', '#7c3aed'),
    'submission': ('Submissions', '#087f67'),
}


def activity(issues, owner, reviewed_comments):
    events = []
    first_grants = {}
    for issue in issues:
        claim = re.fullmatch(r'Claim (P\d{4}|M\d{6})', issue['title'])
        author = issue.get('author') or {}
        login = author.get('login')
        if not claim or not login or login.casefold() == owner.casefold() or author['is_bot']:
            continue
        grant_prefix = f'Granted `{claim[1]}`.'
        grants = [
            c['createdAt'] for c in issue['comments']
            if c['author']['login'] in ('github-actions', 'github-actions[bot]')
            and c['body'].startswith(grant_prefix)
        ]
        if grants:
            timestamp = min(grants)
            events.append((timestamp, 'grant', issue['number'], login))
            first_grants[login] = min(first_grants.get(login, (timestamp, issue['number'])),
                                      (timestamp, issue['number']))
        submissions = [
            c['createdAt'] for c in issue['comments'] if c['author']['login'] == login
            and (c['body'].split('\n', 1)[0].strip().casefold() == 'replay submission'
                 or c['url'] in reviewed_comments)
        ]
        if submissions:
            events.append((min(submissions), 'submission', issue['number'], login))
    events.extend((stamp, 'volunteer', issue, login) for login, (stamp, issue) in first_grants.items())
    return sorted(events)


def render_volunteer_roster(readme, events):
    """Replace the README roster with volunteers credited in the activity log."""
    logins = {
        login.casefold(): login for _, kind, _, login in events
        if kind in ('volunteer', 'submission') and re.fullmatch(r'[A-Za-z0-9-]+', login)
    }
    names = ', '.join(f'[@{login}](https://github.com/{login})'
                      for _, login in sorted(logins.items()))
    start, end = '<!-- volunteer-roster-start -->', '<!-- volunteer-roster-end -->'
    if start not in readme or end not in readme:
        return readme
    roster = f'**Replay volunteers ({len(logins)})**\n\n{names}' if names else 'No replay volunteers recorded yet.'
    return f'{readme.split(start, 1)[0]}{start}\n\n{roster}\n\n{end}{readme.split(end, 1)[1]}'


def render_svg(events):
    series = {key: [] for key in SERIES}
    for stamp, key, _, _ in events:
        series[key].append(datetime.fromisoformat(stamp.replace('Z', '+00:00')).timestamp())
    times = [t for line in series.values() for t in line]
    start = min(times, default=0)
    stop = max(times, default=start) + 1
    if stop - start < 1800:
        stop = start + 1800
    peak = max(map(len, series.values()), default=0)
    step = max(1, math.ceil(peak / 5))
    ceiling = step * 5
    left, right, top, bottom = 58, 694, 66, 295

    def x(seconds):
        return left + (right - left) * (seconds - start) / (stop - start)

    def y(value):
        return bottom - (bottom - top) * value / ceiling

    attrs = 'font-family="system-ui, sans-serif" fill="#344357"'
    svg = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 730 370" role="img" aria-labelledby="title desc">',
        '<title id="title">Volunteer replay activity</title>',
        '<desc id="desc">Cumulative volunteer accounts, granted claims, and submitted results. Coordinator reservations are excluded.</desc>',
        '<rect x="1" y="1" width="728" height="368" rx="14" fill="#f8fafc" stroke="#dbe3ed"/>',
        '<text x="32" y="30" font-family="system-ui, sans-serif" font-weight="600" font-size="18" fill="#172338">Volunteer replay activity</text>',
    ]
    for tick in range(0, ceiling+1, step):
        row = y(tick)
        svg.append(f'<path d="M{left} {row}H{right}" stroke="#dbe3ed"/>')
        svg.append(f'<text x="{left-11}" y="{row+4}" text-anchor="end" font-size="11" {attrs}>{tick}</text>')
    for i in range(5):
        when = start + (stop-start)*i/4
        utc = datetime.fromtimestamp(when,timezone.utc)
        label = utc.strftime('%b %d' if stop-start >= 86400 else '%H:%M')
        svg.append(f'<text x="{x(when):.1f}" y="{bottom+23}" text-anchor="middle" font-size="11" {attrs}>{label}</text>')
    for idx, (key, (label, color)) in enumerate(SERIES.items()):
        points = series[key]
        path = [f'M{left} {bottom}']
        for count, when in enumerate(points,1):
            path.append(f'H{x(when):.2f}V{y(count):.2f}')
        path.append(f'H{right}')
        svg.append(f'<path d="{"".join(path)}" fill="none" stroke="{color}" stroke-width="2.5"/>')
        legend = 54 + idx*207
        svg.append(f'<path d="M{legend} 345h18" stroke="{color}" stroke-width="3"/>')
        svg.append(f'<text x="{legend+25}" y="349" font-size="12" {attrs}>{label} ({len(points)})</text>')
    svg.append(f'<text x="{right}" y="{bottom+40}" text-anchor="end" font-size="10" {attrs}>UTC</text>')
    svg.append('</svg>')
    return '\n'.join(svg)+'\n'


def main():
    repo = os.environ['GITHUB_REPOSITORY']
    fields = 'number,title,author,comments'
    issues = json.loads(gh_output(
        ['gh','issue','list','--repo',repo,'--state','all','--label','claim','--limit','10000','--json',fields],
    ))
    reviewed = {json.loads(p.read_text())['claim'] for p in (TRACKER.parent/'evidence/volunteers').glob('*.json')}
    events = activity(issues,repo.split('/')[0],reviewed)
    with (TRACKER/'activity.tsv').open('w', newline='') as stream:
        output = csv.writer(stream, delimiter='\t', lineterminator='\n')
        output.writerow(['timestamp_utc','event','issue','volunteer'])
        output.writerows(events)
    (TRACKER/'activity.svg').write_text(render_svg(events))
    readme = TRACKER.parent/'README.md'
    current = readme.read_text()
    updated = render_volunteer_roster(current, events)
    if updated != current:
        readme.write_text(updated)


if __name__ == '__main__':
    main()
