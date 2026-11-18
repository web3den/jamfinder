"""Checks on the registry of statistics in jf/field.py.

One test is marked xfail(strict=True): the optional statistic weight="pass" misses its pure-noise bound as the test
defines it. The suite FAILS if that test unexpectedly passes, so the marker cannot go stale. Do not weaken the
assertion to make the marker removable."""
import pytest

from tests.common import LAM
from jf import field


def test_statistics_registry_lists_blocks_and_pass():
    """Every statistic the search can use is registered with its pure-noise mean and variance, so the score
    normalisation is explicit and the reporting rule can be re-derived for each one."""
    assert {"blocks", "pass"} <= set(field.STATISTICS)
    for name, spec in field.STATISTICS.items():
        assert {"null_mean", "null_var"} <= set(spec), name
        assert spec["null_var"] > 0


@pytest.mark.xfail(strict=True, reason="Field(weight='pass') fails this bound as defined (max 8.35 >= 8 on this fixture)")
def test_pass_level_statistic_is_standardised_on_noise(noise_waterfall, lines, rx):
    """weight='pass': one matched-weight z per aircraft over its whole pass (weights = predicted relative echo
    power along the predicted track, normalised within the aircraft), then phi, then the same standardisation as
    'blocks'. On pure noise it must be 0 +- 1 like the current statistic."""
    assert "pass" in field.STATISTICS
    fld = field.Field(noise_waterfall["t"], noise_waterfall["f"], noise_waterfall["W"], lines, rx, LAM, weight="pass")
    e, n, M = fld.grid((0.0, 0.0), 5000.0, 500.0)
    assert abs(M.mean()) < 0.4 and 0.5 < M.std() < 1.6 and M.max() < 8.0, (M.mean(), M.std(), M.max())
