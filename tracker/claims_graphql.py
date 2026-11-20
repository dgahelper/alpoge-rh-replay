"""Read claim history and apply bot decisions through GitHub GraphQL."""

import io
import json
import os
import re
from urllib.error import HTTPError
from urllib.request import Request, urlopen

LABELS = ('claim', 'claim-granted', 'claim-conflict')
COMMENT_FIELDS = 'databaseId body author { login __typename }'


class ClaimsGraphQL:
    def __init__(self, repo, token):
        self.owner, self.repo = repo.split('/')
        self.token = token
        self.issues = {}
        self.comments = []
        self.labels = {}
        self.writes = []

    def query(self, query, **variables):
        request = Request('https://api.github.com/graphql',
                          headers={'Authorization': 'Bearer ' + self.token,
                                   'Content-Type': 'application/json', 'User-Agent': 'replay-claims'},
                          data=json.dumps({'query': query, 'variables': variables}).encode())
        with urlopen(request, timeout=45) as response:
            result = json.load(response)
            if errors := result.get('errors'):
                body = json.dumps(errors).encode()
                if b'rate limit' in body.lower() or b'RATE_LIMITED' in body:
                    raise HTTPError(request.full_url, 429, 'GitHub GraphQL rate limit',
                                    response.headers, io.BytesIO(body))
                raise RuntimeError('; '.join(error['message'] for error in errors))
            return result['data']

    def snapshot(self):
        query = '''
        query($owner:String!, $repo:String!, $after:String) {
          repository(owner:$owner, name:$repo) {
            claim: label(name:"claim") { id }
            granted: label(name:"claim-granted") { id }
            conflict: label(name:"claim-conflict") { id }
            issues(states:OPEN, first:30, after:$after) {
              pageInfo { endCursor hasNextPage }
              nodes { id number title labels(first:30) { nodes { name } }
                      comments(last:30) { pageInfo { startCursor hasPreviousPage }
                                          nodes { %s } } }
            }
          }
        }''' % COMMENT_FIELDS
        after = None
        while True:
            data = self.query(query, owner=self.owner, repo=self.repo, after=after)['repository']
            self.labels = {name: data[key]['id'] for name, key in zip(LABELS, ('claim', 'granted', 'conflict'))}
            issue_page = data['issues']
            for issue in issue_page['nodes']:
                labels = issue['labels']['nodes']
                if not (re.fullmatch(r'Claim (P\d{4}|M\d{6})', issue['title'])
                        or any(label['name'] in LABELS for label in labels)):
                    continue
                number = issue['number']
                url = f'https://api.github.com/repos/{self.owner}/{self.repo}/issues/{number}'
                history = list(self.history(issue))
                self.issues[number] = {**issue, 'labels': labels, 'url': url, 'comments': len(history)}
                self.comments.extend({
                    'id': comment['databaseId'], 'issue_url': url, 'body': comment['body'],
                    'user': {'login': 'github-actions[bot]'}
                } for comment in history
                    if comment.get('author') and comment['author']['__typename'] == 'Bot'
                    and comment['author']['login'] in ('github-actions', 'github-actions[bot]'))
            info = issue_page['pageInfo']
            if not info['hasNextPage']:
                break
            after = info['endCursor']

    def history(self, issue):
        page = issue['comments']
        while True:
            yield from page['nodes']
            info = page['pageInfo']
            if not info['hasPreviousPage']:
                return
            page = self.query('''
              query($id:ID!, $before:String) {
                node(id:$id) { ... on Issue {
                  comments(last:100, before:$before) {
                    pageInfo { startCursor hasPreviousPage }
                    nodes { %s }
                  }
                } }
              }''' % COMMENT_FIELDS, id=issue['id'], before=info['startCursor'])['node']['comments']

    def pages(self, route):
        if route.startswith('/issues/comments?'):
            return iter(self.comments)
        return iter(self.issues.values())

    def queue(self, route, method, body=None):
        match = re.fullmatch(r'/issues/(\d+)/(labels|comments)(?:/([a-z-]+))?', route)
        number, path, label = match.groups()
        node = json.dumps(self.issues[int(number)]['id'])
        if path == 'comments':
            mutation = 'addComment(input:{subjectId:%s,body:%s}){clientMutationId}' % (node, json.dumps(body['body']))
        elif method == 'DELETE':
            mutation = 'removeLabelsFromLabelable(input:{labelableId:%s,labelIds:[%s]}){clientMutationId}' % (
                node, json.dumps(self.labels[label]))
        else:
            ids = ','.join(json.dumps(self.labels[name]) for name in body['labels'])
            mutation = 'addLabelsToLabelable(input:{labelableId:%s,labelIds:[%s]}){clientMutationId}' % (node, ids)
        self.writes.append(mutation)

    def apply(self):
        for offset in range(0, len(self.writes), 8):
            batch = self.writes[offset:offset+8]
            self.query('mutation{' + '\n'.join(f'm{i}:{item}' for i, item in enumerate(batch)) + '}')
        print(f'Reconciled {len(self.issues)} claims with {len(self.writes)} changes.', flush=True)


def reconcile(planner):
    transport = ClaimsGraphQL(os.environ['GITHUB_REPOSITORY'], os.environ['GITHUB_TOKEN'])
    transport.snapshot()
    planner(get_pages=transport.pages, mutate=transport.queue)
    transport.apply()
