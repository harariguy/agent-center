"""Grouping — the mechanism that keeps the feed readable.

An agent on a schedule re-reports the same open item on every run. Notifications
sharing (agent, group_key) fold into one entry with an occurrence count.

`group_key` is agent-supplied (a ticket ref, a job name) and always wins. When
absent, a fingerprint of the title stands in — with volatile tokens stripped so
"7 new receipts ($311.83)" and "3 new receipts ($86.40)" land in the same group.
This is Sentry's model: explicit fingerprint if given, normalised content hash
otherwise, so grouping degrades gracefully rather than off.
"""

from __future__ import annotations

import hashlib
import re

# Order matters: URLs first (they contain digits), then everything numeric.
_URL = re.compile(r"https?://\S+")
# Dates, times, amounts, ids: any token containing a digit is volatile.
_NUMERIC_TOKEN = re.compile(r"\S*\d\S*")
# Calendar words are volatile too — "week of Jul 10" vs "week of Aug 2" is the
# same recurring item. Digits alone don't catch the month name.
_CALENDAR = re.compile(
    r"\b(?:jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?|"
    r"jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|"
    r"dec(?:ember)?|mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|"
    r"thu(?:rs(?:day)?)?|fri(?:day)?|sat(?:urday)?|sun(?:day)?|"
    r"today|yesterday|tomorrow)\b"
)
_NON_ALPHA = re.compile(r"[^a-z\s]")
_WS = re.compile(r"\s+")

# Enough words to keep distinct asks distinct, few enough that a trailing
# variable clause ("…due in 3 days") doesn't split a group.
_MAX_WORDS = 12


def normalise(title: str) -> str:
    t = title.lower()
    t = _URL.sub(" ", t)
    t = _NUMERIC_TOKEN.sub(" ", t)
    t = _CALENDAR.sub(" ", t)
    t = _NON_ALPHA.sub(" ", t)
    words = _WS.split(t.strip())[:_MAX_WORDS]
    return " ".join(w for w in words if w)


def fingerprint(title: str) -> str:
    base = normalise(title) or "untitled"
    return hashlib.sha1(base.encode()).hexdigest()[:16]
