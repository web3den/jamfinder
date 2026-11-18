"""The search package must be truth-free: no path into data/ref, no unsealing, no truth coordinates.

A reference position ("truth") is only ever compared with an answer after the search has given it."""
import glob
import os

from tests.common import ROOT

FORBIDDEN = ("data/ref", "unseal", "truth_table", "truth_lat", "truth_lon")


def test_search_package_never_references_truth():
    bad = []
    for fn in sorted(glob.glob(os.path.join(ROOT, "jf", "*.py"))):
        src = open(fn, encoding="utf-8").read()
        for pat in FORBIDDEN:
            if pat in src:
                bad.append((os.path.basename(fn), pat))
    assert not bad, bad
