"""The fingerprint: volatile tokens must not split a group."""

from agent_notifications.core.grouping import fingerprint, normalise


def test_numbers_and_amounts_are_volatile():
    a = fingerprint("Mesh receipts — 7 new today ($311.83 total)")
    b = fingerprint("Mesh receipts — 3 new today ($86.40 total)")
    assert a == b


def test_dates_are_volatile():
    assert fingerprint("Weekly ops wrap — week of Jul 10, 2026") == \
           fingerprint("Weekly ops wrap — week of Aug 2, 2026")


def test_urls_are_volatile():
    assert fingerprint("Draft ready → https://mail.example.com/draft/abc123") == \
           fingerprint("Draft ready → https://mail.example.com/draft/zzz999")


def test_distinct_asks_stay_distinct():
    assert fingerprint("Bank signature needed — July payroll") != \
           fingerprint("Which entity paid the Meridian invoice?")


def test_case_and_whitespace_insensitive():
    assert fingerprint("  Payroll   Draft UNSENT ") == fingerprint("payroll draft unsent")


def test_degenerate_titles_do_not_crash():
    assert fingerprint("$311.83") == fingerprint("42")   # all-volatile → same bucket
    assert normalise("$311.83") == ""
    assert fingerprint("") == fingerprint("   ")
