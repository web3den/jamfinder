"""The independent oracle must accept the repository's Doppler code and reject the planted mistake.
A check that cannot fail is not a check, so the negative control is part of the test."""
from qa.oracle import independent_oracle, subject


def test_the_real_doppler_code_meets_the_independent_oracle():
    assert independent_oracle.judge(subject.bistatic_doppler_correct) == []


def test_the_independent_oracle_rejects_the_planted_mistake():
    scope = {}
    exec(subject.BUGGY_SOURCE, scope)
    failures = independent_oracle.judge(scope["bistatic_doppler"])
    assert len(failures) >= 3, failures
