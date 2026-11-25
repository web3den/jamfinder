# Property-based testing

An example-based test checks five inputs someone thought of. A property-based test states a rule that must
hold for every input; [Hypothesis](https://hypothesis.readthedocs.io) then generates thousands of inputs, looks
for one that breaks the rule, and shrinks it to the simplest case that still does.

    python -m pytest qa/properties

## What is checked

| property | code | holds? |
|---|---|---|
| v3.2 says "one" exactly when its written conditions hold | `jf/rules.py` | yes |
| the unit of the scores does not matter (all conditions are ratios) | `jf/rules.py` | yes |
| the order of the control searches does not matter | `jf/rules.py` | yes |
| a degenerate control search has no say | `jf/rules.py` | yes |
| a stronger best spot never lowers confidence | `jf/rules.py` | yes |
| **a louder control search never raises confidence** | `jf/rules.py` | **no: FINDING-001** |
| the local frame's origin is (0, 0, 0); its axes are orthonormal | `jf/geo.py` | yes |
| distances do not change between frames | `jf/geo.py` | yes |
| to the local frame and back is exact within 100 km | `jf/geo.py` | yes |
| **to the local frame and back is exact everywhere on Earth** | `jf/geo.py` | **no: FINDING-002** |
| an echo never shifts more than 2 x speed / wavelength | `jf/tracks.py` | yes |
| transmitter and receiver can swap places | `jf/tracks.py` | yes |
| flying backwards flips the sign; flying square to both legs gives no shift | `jf/tracks.py` | yes |

Both failing properties are kept as strict `xfail` tests: CI stays green while they are known, and turns red
the day either is fixed, so the fix is noticed and the test is promoted.

## FINDING-001: a stronger control search can turn "nothing" into "one"

A control search looks for the transmitter where it cannot be (spectrum flipped, aircraft times shifted). Its
best score measures how loud false spots get. More of that evidence should never make the rule more willing to
report. Hypothesis found, and shrank to this, an input where it does:

| | best spot | flip control | residual | condition (b): best >= 3 x control | condition (c): residual < control | verdict |
|---|---|---|---|---|---|---|
| before | 3 | 0 | 0 | yes | no (0 < 0 is false) | nothing |
| after | 3 | **1** | 0 | yes | **yes** | **one** |

A realistic version: best 100, control 5, residual 7 gives "nothing"; raise the control to 10 and it gives "one".
The cause is condition (c): it compares the blanking residual with the control score, so a louder control makes
(c) easier, while (b) gets harder. Whether that is intended is a question for the rule's owner, not a bug to
fix silently: it is filed as proposed requirement REQ-GATE-005 in `qa/specs/requirements.toml`.

Also seen on the way: rule v3.2 has no absolute floor (that was v1's job), so with very quiet controls a best
score of 3, well under the pure-noise maximum of about 8, can be reported. On real data the controls are never
that quiet.

## FINDING-002: `Frame.to_geo` fails at the poles

Shrunk case: a frame at (0°, 0°), a point at the North Pole at sea level. `to_enu` then `to_geo` returns
`(nan, 0.0, nan)`. A frame at 89° gives a height of -352 km for a point 1000 m up at the pole. The cause:
height is computed as `rho / cos(lat) - n`, and `cos(90°)` is 0. Everywhere else the round trip is exact to
under a micrometre. No receiver is near a pole, so it is low priority (proposed REQ-GEO-003); the standard fix
computes height from `z / sin(lat)` near the poles.

## Files

- `strategies.py`: what a valid input of the reporting rule looks like (shared with `qa/jit`)
- `test_gate_properties.py`, `test_geometry_properties.py`: the properties
