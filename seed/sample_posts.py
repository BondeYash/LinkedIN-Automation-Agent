"""Seed reference posts for style learning.

These are short, generic LinkedIn-style posts written for this project — NOT
scraped or copied from anyone. They exist only so the style analyzer has
something to measure on a fresh install; the analyzer keeps the *numbers*, not
the text. Replace/extend with your own approved posts in production.
"""

from __future__ import annotations

SAMPLE_POSTS: list[str] = [
    (
        "Most teams don't have a productivity problem. They have a focus problem.\n\n"
        "Last quarter we cut our active projects from 11 to 4. Output went up, not down.\n\n"
        "Fewer things, done well, beats many things done halfway.\n\n"
        "What would you stop doing if you could only ship 3 things this quarter?\n\n"
        "#leadership #productivity #engineering"
    ),
    (
        "I reviewed 50 pull requests this month. One pattern stood out.\n\n"
        "The best engineers write smaller PRs. Not because they code less — because "
        "they think in shippable steps.\n\n"
        "Small PRs review faster, break less, and ship sooner.\n\n"
        "Ship small. Ship often. #softwareengineering #codereview"
    ),
    (
        "Your first AI feature doesn't need a fancy model.\n\n"
        "It needs a clear job:\n"
        "- one input\n"
        "- one output\n"
        "- one way to tell if it worked\n\n"
        "Start there. Scale later.\n\n"
        "#ai #productmanagement #startups"
    ),
    (
        "Hiring tip nobody tells you:\n\n"
        "Interview for how someone learns, not just what they know.\n\n"
        "Skills expire. The ability to pick up new ones doesn't.\n\n"
        "How do you test for learning speed in an interview? Curious to hear your approach. "
        "#hiring #careers"
    ),
    (
        "We deleted 12,000 lines of code last week.\n\n"
        "No new features. Just less.\n\n"
        "The system got faster, the bugs got fewer, and onboarding got easier.\n\n"
        "Deleting code is underrated engineering. #softwareengineering #refactoring"
    ),
]
