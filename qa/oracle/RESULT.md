# Test oracle experiment: tests from the code against tests from the requirement

The function: bistatic Doppler shift of an echo. The planted mistake: the sign of the transmitter leg (`qa/oracle/subject.py`). Each suite ran against the wrong code and against the right code, in the sandbox.

| arm | sample | passed on the WRONG code | passed on the RIGHT code | verdict |
|---|---|---|---|---|
| A: tests from the code | 1 | 6/6 | 1/6 | common-mode: passes the bug, rejects the right code |
| A: tests from the code | 2 | 6/6 | 1/6 | common-mode: passes the bug, rejects the right code |
| A: tests from the code | 3 | 4/6 | 2/6 | caught it, but also rejects the right code |
| A: tests from the code | 4 | 6/6 | 1/6 | common-mode: passes the bug, rejects the right code |
| B: tests from the requirement | 1 | 2/6 | 6/6 | caught the bug |
| B: tests from the requirement | 2 | 1/6 | 6/6 | caught the bug |
| B: tests from the requirement | 3 | 2/6 | 6/6 | caught the bug |
| B: tests from the requirement | 4 | 2/6 | 4/6 | caught it, but also rejects the right code |
| C: independent oracle | | 0/4 checks | 4/4 checks | caught the bug |

Totals:

- **A, tests from the code:** common-mode: passes the bug, rejects the right code: 3; caught it, but also rejects the right code: 1
- **B, tests from the requirement:** caught the bug: 3; caught it, but also rejects the right code: 1
- **C, independent oracle:** caught the bug in 8 ways; on the right code no complaint.

What the independent oracle reported on the wrong code:

- path-length rate: expected 56.495 Hz, got -14.571 Hz
- path-length rate: expected 130.316 Hz, got -11.411 Hz
- path-length rate: expected 78.683 Hz, got -0.420 Hz
- radar limit (tx = rx): expected 93.368 Hz, got -0.000 Hz
- swapping tx and rx changed the shift: -14.571 vs 14.571 Hz
- swapping tx and rx changed the shift: -11.411 vs 11.411 Hz
- swapping tx and rx changed the shift: -0.420 vs 0.420 Hz
- hand calculation: expected -63.718 Hz, got -0.000 Hz

Model: gpt-5.4-mini, 4 samples per arm. Model cost: $0.06 when recorded (replays are free).
