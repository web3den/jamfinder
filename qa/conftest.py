"""Shared settings for the tests under qa/.

Hypothesis searches with fresh random inputs on every local run (more ground covered over time) and with a fixed
seed in CI (the same inputs every time, so a red build is always reproducible)."""
import os

from hypothesis import settings

settings.register_profile("ci", derandomize=True, deadline=None, print_blob=True)
settings.register_profile("dev", deadline=None, print_blob=True)
settings.load_profile("ci" if os.environ.get("CI") or os.environ.get("QA_DETERMINISTIC") else "dev")
