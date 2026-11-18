# results/

This folder is empty on purpose. The scripts write the outputs of your runs here. No results
of earlier runs are included.

## What the analysis writes

For a recording named `site1`, the commands in
[docs/try_it_yourself.md](../docs/try_it_yourself.md) write these files. The trailing `r` in
the names means the recording went through the repair of lost samples first.

| File | What it holds |
|---|---|
| `site1r_fix_drops.txt` | The printout of the repair step |
| `site1r_fix_rxfit.json`, `site1r_site_run.txt` | The main search, twice: with the receiver at the position given on the command line, and with the receiver's position fitted too |
| `site1r_null.jsonl`, `site1r_null.txt` | The wrong-track tests, one row per test |
| `site1r_rules.json`, `site1r_rules.txt` | The verdicts of the early rules (v1, v2, v2.2), their six conditions, the best wrong-track score and the blanking test |
| `site1r_rules_v31.json` | The verdicts of rules v3, v3.1 and v3.2, their conditions, and every wrong-track test. Field `v32` is the final rule. |
| `site1r_bb.npz` | An intermediate file: the recording cut down to a narrow band around the carrier. Later steps reuse it. |

## Fields

Positions are in metres east (`e`) and north (`n`) of the receiver position given on the
command line. Where a spot also has `lat` and `lon`, they are the same place. Scores are in
units of the map's own noise.

| Field | Meaning |
|---|---|
| `written` | When the file was written, UTC |
| `args` | The command line of the run |
| `seconds` | Length of the recording |
| `cn0` | Loudness of the carrier at the receiver, in dB-Hz |
| `aircraft` | Number of aircraft with more than ten seconds of usable track inside the recording. The printouts count every aircraft with any track. That number is larger. |
| `listed`, `fitted` | The two searches of the main file: receiver at the given position, and receiver position fitted too |
| `cands` | Candidate spots, best first. In the main file each has named values: `score`, `e`, `n`, the time offset `dt` in seconds, `lat`, `lon`. In the rule files and the wrong-track file each is a plain list: score, east, north, `dt`. |
| `best`, `second` | The best candidate, and the runner-up's score |
| `z_map` | How far the best cell of the wide map stands above the map's middle value, in units of the map's spread |
| `support` | Evidence per aircraft at the best spot: callsign, transponder code, value. The wrong-track file gives only the four largest values for each candidate. |
| `clocks` | Time offset fitted per aircraft, in seconds, by transponder code |
| `verdict`, `v1`, `v2`, `v22`, `v3`, `v31`, `v32` | What a rule said: `one`, `ambiguous` or `nothing`. `v22` is rule v2.2, `v31` is v3.1 and `v32` is v3.2. |
| `conditions` | The tests a rule rests on, true or false, see below |
| `nulls` | The wrong-track tests. `kind` is `flip` for the mirrored spectrum, `shift` for tracks moved by `delta` seconds, or `wrongtime` for the tracks of another recording at the same site. `best` is the test's best score. `frac` is the share of the track time that still lies inside the recording. A test with `frac` under a half is marked `degenerate` and does not count. |
| `null_best`, `largest_null` | The best score among the wrong-track tests. `null_best`, in the early rule file, is taken over all tests. `largest_null`, in the later one, leaves out the degenerate tests. |
| `null_runs` | How many wrong-track tests were run |
| `residual` | The best score left after the echo lines of the best spot were erased |
| `residual_zmap` | The `z_map` of that second search |
| `rx_e`, `rx_n`, `rx_lat`, `rx_lon` | The fitted receiver position: metres from the given position, and as latitude and longitude |

The conditions, as defined at the top of `jf/rules.py`:

| Key | Test |
|---|---|
| `a` | Every wrong-track test says "nothing" under rule v1 |
| `a1` | The test with the spectrum mirrored says "nothing" under rule v1 |
| `b` | The best score is at least 3 times the best wrong-track score |
| `c` | After erasing the best spot's echo lines, what is left scores below the best wrong-track score |
| `d` | The runner-up scores below 0.75 times the best |
| `e` | At least 3 aircraft each give support of 10 or more |
| `f` | The second-strongest aircraft gives at least a quarter of the strongest |

The final rule, v3.2, says "one" only if `a1`, `b`, `c` and `d` all hold. Otherwise it says
"nothing".

A fitted receiver position can say more about a volunteer's antenna than its owner chose to
publish. If the receiver is not yours, do not publish `rx_e`, `rx_n`, `rx_lat` or `rx_lon`.
