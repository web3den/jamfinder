# results/

The analysis writes its output here. The folder is empty in the repository.

For a run named `site1`, the file names start with `site1r_`. The `r` marks the repaired copy of
the recording.

| File | Content |
|---|---|
| `site1r_rules_v31.json` | The verdict and what it rests on. Field `v32` is the current rule. |
| `site1r_fix_rxfit.json` | The main search: candidate places, scores, signal strength, aircraft used, and the fitted receiver position |
| `site1r_null.jsonl` | The control searches, one per line |
| `site1r_rules.json` | Inputs of the verdict, and the verdicts of older rules |
| `site1r_bb.npz` | The recording cut to a narrow band around the carrier, reused by later steps |
| `*.txt` | What each step printed |

## Main fields

Places are given in metres east (`e`) and north (`n`) of the receiver position you entered, and
as `lat` and `lon` where present. Scores are in units of the noise.

| Field | Meaning |
|---|---|
| `v32` | The verdict: `one` or `nothing`. `v1` to `v31` are older rules. |
| `best` | The best place |
| `second` | The score of the second-best place |
| `cands` | Candidate places, best first |
| `support` | The evidence each aircraft gives for the best place |
| `nulls` | The control searches: `flip` for the flipped frequency axis, `shift` for tracks moved by `delta` seconds. A search marked `degenerate` kept too little track inside the recording and does not count. |
| `largest_null` | The best score among the control searches that count |
| `residual` | The best score left after the echoes explained by the best place are erased |
| `conditions` | The tests behind the verdicts. `v32` uses `a1`, `b`, `c` and `d`, see below. |
| `cn0` | The carrier's strength at the receiver, in dB-Hz |
| `aircraft` | The number of aircraft with more than 10 seconds of usable track |
| `rx_e`, `rx_n`, `rx_lat`, `rx_lon` | The fitted receiver position |

`v32` is `one` only if all four of these are true:

| Key | Test |
|---|---|
| `a1` | The search with the flipped frequency axis finds nothing |
| `b` | The best score is at least 3 times `largest_null` |
| `c` | `residual` is below `largest_null` |
| `d` | The second-best place scores less than 0.75 times the best |

The fitted receiver position can be more precise than what the receiver's owner chose to
publish. If the receiver is not yours, do not publish `rx_e`, `rx_n`, `rx_lat` or `rx_lon`.
