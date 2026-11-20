"""Suggest disjoint builds against a prepared worker's project module inventory."""
from collections import Counter


def suggestions(rows, busy, cached, primary, limit, max_builds):
    # A closure contains exactly the project modules a cold edge may pull in,
    # stopping at known local objects. Bound each set before storing it.
    closures = {}
    available = []
    for row in sorted(rows, key=lambda r: r['depth']):
        task = row['id']
        if task in cached:
            closures[task] = frozenset()
            continue
        if task in busy or row['packet'] in busy or row['state'] == 'assigned':
            continue
        if row['state'] == 'open' and task not in primary:
            available.append(row)
        missing = {task}
        for dep in row['imports']:
            if dep not in closures:
                break
            missing.update(closures[dep])
            if len(missing) > max_builds:
                break
        else:
            closures[task] = missing
    consumers = Counter(dep for row in available for dep in set(row['imports']))
    choices = [r for r in available if r['id'] in closures]
    choices.sort(key=lambda r: (-consumers[r['id']] / len(closures[r['id']]),
                                len(closures[r['id']]), r['id']))
    taken = set()
    for row in choices:
        if limit <= 0:
            break
        missing = closures[row['id']]
        if taken.isdisjoint(missing):
            yield row, len(missing), consumers[row['id']]
            taken.update(missing)
            limit -= 1
