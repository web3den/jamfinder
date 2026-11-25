# Metamorphic testing

For the whole pipeline (simulated signal, waterfall, map search) nobody can say in advance exactly where the
best spot will land: that depends on noise, cell size and the zoom steps. But some relations between two runs
are certain. Change the scene in a controlled way and the answer must change in the matching way.

    python -m pytest qa/metamorphic          # about 50 s: ten full searches

| relation | expected | tolerance | result |
|---|---|---|---|
| the same scene an hour later | same spot, same score | exact | 0.000 m |
| the scene turned by 90°, 180°, 270° | the spot turned the same way | exact | 0.000 m |
| the scene mirrored east-west | the spot mirrored | exact | 0.000 m |
| the aircraft listed in another order | same spot | exact | 0.000 m |
| receiver gain x1000 and phase +1 rad | same spot | 0.01 m | 0.0001 m |
| receiver tuned 5 Hz off the carrier | same spot | 5 m | 0.3 m |
| transmitter moved 806 m | the spot moves 806 m | 50 m | 7 m off |
| another draw of the receiver noise | about the same spot | 100 m | 6 m |

Each tolerance states the promise: exact relations follow from symmetry, the last three are physics with noise
in it.

A lesson from building it. The first version of the turn and mirror relations missed by 10 to 29 m. The search
was not at fault: the simulator gives each aircraft a fixed 10-m track error drawn in north/east coordinates, and
those errors do not turn with the scene, so the turned scene was a slightly different scene. With exact position
reports the relations hold to the millimetre. A metamorphic relation is only as good as the transformation: it
must keep exactly what the relation assumes.

Files: `scene.py` (the scene, the pipeline and the transformations), `test_metamorphic.py` (the relations).
