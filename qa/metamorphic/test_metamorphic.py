"""Metamorphic tests of the whole pipeline: simulated signal -> waterfall -> map search.

Nobody can say in advance exactly where the search will put its best spot for a given scene: that depends on
noise, cell size and the zoom steps. But some RELATIONS between two runs are certain. Change the scene in a
controlled way, and the answer must change in the matching way (or not at all):

  relation                                      expected                              tolerance
  the same scene an hour later                  same spot, same score                 exact
  the scene turned by 90, 180, 270 degrees      the spot turned by the same angle     exact
  the scene mirrored east-west                  the spot mirrored                     exact
  aircraft listed in another order              same spot                             exact
  receiver gain and phase changed               same spot                             0.01 m
  receiver tuned 5 Hz off the carrier           same spot                             5 m
  transmitter moved 806 m                       spot moves by the same 806 m          50 m
  a different draw of the receiver noise        about the same spot                   100 m

Each tolerance says what is promised: exact relations follow from symmetry; the last three are physics with
noise in it. One run takes about 5 s.
"""
import numpy as np
import pytest

from qa.metamorphic import scene as S

EXACT = 0.01   # metres: floating-point noise only


@pytest.fixture(scope="module")
def base():
    sc = S.base_scene()
    bb = S.signal(sc)
    found = S.locate(bb, sc.aircraft)
    assert found.verdict == "one" and found.distance(*S.TX[:2]) < 100.0     # the starting point is itself sound
    return sc, bb, found


def test_the_same_scene_an_hour_later_gives_the_same_answer(base):
    sc, _, f0 = base
    later = S.shifted_in_time(sc, 3600.0)
    f = S.locate(S.signal(later), later.aircraft)
    assert f.distance(f0.east, f0.north) < EXACT and f.score == pytest.approx(f0.score, rel=1e-9)


@pytest.mark.parametrize("quarter_turns", [1, 2, 3])
def test_a_turned_scene_gives_a_turned_answer(base, quarter_turns):
    sc, _, f0 = base
    c, s = [1, 0, -1, 0][quarter_turns], [0, 1, 0, -1][quarter_turns]
    turned = S.turned(sc, quarter_turns)
    f = S.locate(S.signal(turned), turned.aircraft)
    assert f.distance(c * f0.east - s * f0.north, s * f0.east + c * f0.north) < EXACT
    assert f.score == pytest.approx(f0.score, rel=1e-9)


def test_a_mirrored_scene_gives_a_mirrored_answer(base):
    sc, _, f0 = base
    mirrored = S.mirrored(sc)
    f = S.locate(S.signal(mirrored), mirrored.aircraft)
    assert f.distance(-f0.east, f0.north) < EXACT


def test_the_order_of_the_aircraft_does_not_matter(base):
    sc, bb, f0 = base
    assert S.locate(bb, S.reordered(sc.aircraft)).distance(f0.east, f0.north) < EXACT


def test_receiver_gain_and_phase_do_not_matter(base):
    sc, bb, f0 = base
    f = S.locate(S.scaled(bb, 1000.0 * np.exp(1j)), sc.aircraft)
    assert f.distance(f0.east, f0.north) < EXACT


def test_a_receiver_tuned_5_hz_off_finds_the_same_spot(base):
    sc, bb, f0 = base
    assert S.locate(S.detuned(bb, 5.0), sc.aircraft).distance(f0.east, f0.north) < 5.0


def test_moving_the_transmitter_moves_the_answer_by_as_much(base):
    sc, _, f0 = base
    moved = S.with_transmitter_moved(sc, 700.0, -400.0)
    f = S.locate(S.signal(moved), moved.aircraft)
    assert f.distance(f0.east + 700.0, f0.north - 400.0) < 50.0


def test_another_noise_draw_lands_close(base):
    sc, _, f0 = base
    assert S.locate(S.signal(sc, seed=1), sc.aircraft).distance(f0.east, f0.north) < 100.0
