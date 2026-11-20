"""Reconcile mutually exclusive volunteer reservations from trusted main-branch code."""
import json,os,re,sys,time,urllib.request,urllib.error
from claim_comments import COMMENT_FEED, comments_by_issue
from tasks import load
from collections import defaultdict
def api(route,method='GET',body=None):
 base='https://api.github.com/repos/'+os.environ['GITHUB_REPOSITORY']
 request=urllib.request.Request(base+route,method=method,headers={'Authorization':'Bearer '+os.environ['GITHUB_TOKEN'],'Accept':'application/vnd.github+json','User-Agent':'replay-claims'},data=None if body is None else json.dumps(body).encode())
 with urllib.request.urlopen(request,timeout=30) as response:return json.loads(response.read() or 'null')
def pages(route):
    page = 1
    while True:
        batch = api(f'{route}&page={page}')
        yield from batch
        if len(batch) < 100:
            return
        page += 1


def prior_decisions(issues, get_pages=None):
    get_pages = get_pages or pages
    labels = {i['number']: {label['name'] for label in i['labels']} for i in issues}
    decided = [i for i in issues if labels[i['number']] & {'claim-granted', 'claim-conflict'}]
    histories = comments_by_issue(decided, get_pages('/' + COMMENT_FEED))
    prior = {}
    conflicts = set()
    for number, comments in histories.items():
        for comment in sorted(comments, key=lambda c: c['id']):
            if comment['user']['login'] != 'github-actions[bot]':
                continue
            grant = re.match(r'Granted `(P\d{4}|M\d{6})`\.', comment['body'])
            if grant:
                if 'claim-granted' in labels[number]:
                    prior[number] = grant[1]
                conflicts.discard(number)
            elif comment['body'].startswith('No grant.'):
                conflicts.add(number)
    return prior, conflicts


def reconcile(get_pages=None, mutate=None):
 get_pages = get_pages or pages
 mutate = mutate or api
 rows=load();groups=defaultdict(set);reserved=set()
 for r in rows:
  groups[r['id']].add(r['id']);groups[r['packet']].add(r['id'])
  if r['state']!='open':reserved.add(r['id'])
 issues=[i for i in get_pages('/issues?state=open&per_page=100') if 'pull_request' not in i]
 planned=[];taken=set()
 # Preserve valid grants first, then use issue number as a deterministic tie-breaker.
 prior,conflicts=prior_decisions(issues,get_pages)
 for i in sorted(issues,key=lambda z:(prior.get(z['number'])!=z['title'].removeprefix('Claim '),z['number'])):
  labels={l['name'] for l in i['labels']};m=re.fullmatch(r'Claim (P\d{4}|M\d{6})',i['title'])
  if not m and not labels.intersection({'claim-granted','claim-conflict','claim'}):continue
  target=m[1] if m else '';mods=groups.get(target,set())
  existing_grant=prior.get(i['number'])==target
  # New build evidence should not revoke work already granted to a volunteer.
  win=bool(mods) and not mods.intersection(taken) and (existing_grant or not mods.intersection(reserved))
  if win:taken.update(mods)
  desired='claim-granted' if win else 'claim-conflict'
  planned.append((i['number'],labels,target,desired))
 for number,labels,target,desired in planned:
  other='claim-conflict' if desired=='claim-granted' else 'claim-granted'
  if other in labels:mutate(f'/issues/{number}/labels/{other}','DELETE')
 for number,labels,target,desired in planned:
  if desired not in labels or 'claim' not in labels:mutate(f'/issues/{number}/labels','POST',{'labels':['claim',desired]})
  if desired=='claim-granted' and (desired not in labels or prior.get(number)!=target):
   mutate(f'/issues/{number}/comments','POST',{'body':f'Granted `{target}`. Begin this reservation. Attach your receipt and log to this issue, or close it to release the work.'})
  elif desired=='claim-conflict' and (desired not in labels or number not in conflicts):
   mutate(f'/issues/{number}/comments','POST',{'body':'No grant. This selection is unavailable or overlaps existing work. Close this issue and choose a new open module or packet with `python3 tracker/tasks.py next`.'})
def rate_limit_delay(error, attempt):
    if error.code not in (403, 429):
        return None
    headers = error.headers
    retry = headers.get('Retry-After', '')
    reset = headers.get('X-RateLimit-Reset', '')
    exhausted = headers.get('X-RateLimit-Remaining') == '0'
    if not (error.code == 429 or retry.isdigit() or exhausted
            or b'rate limit' in error.read().lower()):
        return None
    delays = [int(retry)] if retry.isdigit() else []
    if exhausted and reset.isdigit():
        delays.append(max(1, int(reset) - int(time.time()) + 1))
    return max(delays) if delays else 60 * 2 ** attempt


def main():
    for attempt in range(4):
        try:
            if '--graphql' in sys.argv:
                import claims_graphql
                return claims_graphql.reconcile(reconcile)
            return reconcile()
        except urllib.error.HTTPError as error:
            delay = rate_limit_delay(error, attempt)
            if delay is None or attempt == 3:
                raise
            error.close()
            print(f'GitHub rate limit (HTTP {error.code}). Rechecking all claims after {delay}s.',
                  file=sys.stderr, flush=True)
            time.sleep(delay)


if __name__=='__main__':main()
