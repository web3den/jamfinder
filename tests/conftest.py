"""Shared pytest fixtures: the receiver position, the synthetic aircraft lines, and a waterfall of pure noise."""
import numpy as np
import pytest

from tests.common import DUR, RX, T0, make_lines
from jf import iq, scatter


@pytest.fixture(scope="session")
def rx():
    return RX.copy()


@pytest.fixture(scope="session")
def lines():
    return make_lines()


@pytest.fixture(scope="session")
def noise_waterfall():
    """A whitened waterfall of pure complex white noise: what the search sees when there is nothing at all."""
    rng = np.random.default_rng(1)
    fs = 1250.0
    n = int(DUR * fs)
    y = ((rng.standard_normal(n) + 1j * rng.standard_normal(n)) / np.sqrt(2)).astype(np.complex64)
    t, f, S = iq.spectrogram(y, fs, win_s=1.0, hop_s=0.5, f_max=250.0)
    W, floor = scatter.whiten(S, f)
    return dict(t=T0 + t, f=f, W=W, S=S, floor=floor)
