"""Build the bot's commit message from the claim issues changed in the index."""

import json
import os
from pathlib import Path
import re
import subprocess
import sys


def changed_issues(repo):
    def changed_rows(path):
        diff = subprocess.check_output(
            ['git', 'diff', '--cached', '--no-color', '--no-ext-diff', '-U0', '--', path], text=True)
        return (line[1:] for line in diff.splitlines() if line.startswith(('+', '-')))

    numbers = set()
    issue_link = re.compile(r'\]\(https://github\.com/' + re.escape(repo) + r'/issues/(\d+)(?:#issuecomment-\d+)?\)')
    for row in changed_rows('README.md'):
        if row.startswith('| [@') and (match := issue_link.search(row)):
            numbers.add(int(match[1]))
    for row in changed_rows('tracker/activity.tsv'):
        fields = row.split('\t')
        if len(fields) == 4 and fields[2].isdigit():
            numbers.add(int(fields[2]))
    return numbers


def commit_message(repo, issue_authors):
    authors = {}
    for number in sorted(changed_issues(repo)):
        if author := issue_authors.get(str(number)):
            user_id, login = author
            authors[user_id] = login

    trailers = [f'Co-authored-by: {login} <{user_id}+{login}@users.noreply.github.com>'
                for user_id, login in sorted(authors.items())]
    return '\n'.join(['Update replay contributor credits', '', *trailers]).rstrip()


if __name__ == '__main__':
    print(commit_message(os.environ['GITHUB_REPOSITORY'], json.loads(Path(sys.argv[1]).read_text())))
