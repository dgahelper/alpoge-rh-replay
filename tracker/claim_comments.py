"""Group paginated repository comments by their owning claim issue."""

from collections import defaultdict

COMMENT_FEED = 'issues/comments?sort=created&direction=asc&per_page=100'


def comments_by_issue(issues, comments):
    numbers = {issue['url']: issue['number'] for issue in issues if issue['comments']}
    grouped = defaultdict(list)
    if numbers:
        for comment in comments:
            number = numbers.get(comment['issue_url'])
            if number is not None:
                grouped[number].append(comment)
    return grouped
