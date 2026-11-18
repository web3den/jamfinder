# Script index

One line per file, taken from the file's own docstring or leading comment. Regenerate with
`python tools/make_script_index.py`. Usage lines and details are at the top of each file.

## `jf/`: the method

| File | What it does |
|---|---|
| `jf/blind.py` | Search when the receiver cannot hear the transmitter itself. |
| `jf/field.py` | Matched-field search that also works when no single line is visible. |
| `jf/geo.py` | WGS84 helpers: geodetic <-> ECEF <-> local east/north/up. |
| `jf/iq.py` | Load spy_record captures and turn them into a clean carrier-referenced signal. |
| `jf/locate.py` | Find the transmitter: try candidate positions, keep the one whose predicted aircraft Doppler tracks collect the most energy in the measured waterfall. |
| `jf/pipeline.py` | The whole fix as two calls: blind grid search, then least squares on measured lines. |
| `jf/ridge.py` | Pick the measured Doppler of each aircraft off the waterfall and solve for the transmitter (and, if asked, the receiver and clock offsets) by least squares. |
| `jf/rules.py` | The reporting rules v1, v2, v2.2, v3, v3.1 and v3.2 as one pure function. |
| `jf/scatter.py` | From a raw capture to a whitened Doppler waterfall, ready for track matching. |
| `jf/tracks.py` | Aircraft tracks from readsb-style JSON snapshots, and predicted Doppler. |

## `sim/`: the simulator

| File | What it does |
|---|---|
| `sim/synth.py` | Synthetic receiver signal: one transmitter, many aircraft echoes, noise. |

## `examples/`: examples

| File | What it does |
|---|---|
| `examples/demo_synthetic.py` | Smallest end-to-end demonstration: plant a transmitter in a made-up scene and let the search find it. |

## `tools/`: recording, repair, screening and run scripts

| File | What it does |
|---|---|
| `tools/blind_pipeline.sh` | The whole analysis of one recording, run in one go so that no step is tuned by hand |
| `tools/fix_drops.py` | Put back the blocks of samples that a busy SDR server left out of a recording. |
| `tools/make_script_index.py` | Write docs/script_index.md: one line per script, taken from its docstring or leading comment. |
| `tools/make_stub_bb.py` | Write a stub baseband cache that only carries a start time and a length, for simulations on a position capture that has no recording (analysis/sim_v3_check.py reads results/<name>_bb.npz for t0 and len(y)/fs and nothing ... |
| `tools/merge_adsb.py` | Merge several position-snapshot files (readsb-style lines, possibly with a truncated tail) into one, in time order. |
| `tools/nearby.py` | List VHF navaids and airport broadcast frequencies near a point. |
| `tools/probe.py` | How well does a short capture hear a steady carrier? Prints its offset and carrier-to-noise density. |
| `tools/quick_look.py` | First look at a running or finished SpyServer recording: is the carrier there, where, how strong, how clean? |
| `tools/record_adsb.py` | Poll a readsb-style ADS-B API around a point and save every reply. |
| `tools/record_opensky.py` | Poll the OpenSky Network (anonymous) around a point and save replies in the same shape as record_adsb.py. |
| `tools/run_after.sh` | Wait for an IQ recording to finish, then run the analysis once, untouched, and the rules v3 to v3.2. |
| `tools/spy_probe.py` | Pre-flight for a public SpyServer: does it let us tune, and is the wanted carrier there? |
| `tools/spy_record.py` | Record narrowband IQ from a public SpyServer (Airspy network protocol). |

## `analysis/`: the pipeline steps, pictures, and simulations on real aircraft tracks

| File | What it does |
|---|---|
| `analysis/first_look.py` | First look: carrier-referenced Doppler waterfall of a (possibly partial) capture. |
| `analysis/null_try.py` | What does the search report when the aircraft tracks do not belong to the echoes? |
| `analysis/null_wrongtime.py` | Wrong-time-tracks null: search a recording with the aircraft tracks of ANOTHER recording of the same site. |
| `analysis/overlay.py` | Waterfall with predicted aircraft Doppler tracks drawn on top. |
| `analysis/rule_v2.py` | Apply the reporting rules v1, v2 and v2.2 to a site, as defined in jf/rules.py, and print the verdicts. |
| `analysis/rule_v31.py` | Rules v3, v3.1 and v3.2 from a finished pipeline run — no search of its own. |
| `analysis/sim_run.py` | Plant a made-up transmitter among real aircraft tracks and see whether the search finds it. |
| `analysis/sim_v3_check.py` | Does the whole verdict (rule v3) pass on a planted transmitter among real aircraft tracks? |
| `analysis/site_pic.py` | Picture: wide search map with the candidates, and the whitened waterfall with the predicted echo lines of the strongest aircraft drawn for the best spot. |
| `analysis/site_run.py` | Search at a site where we do not know where the transmitter is. |

## `tests/`: tests

| File | What it does |
|---|---|
| `tests/common.py` | Shared constants and synthetic scenes for the tests. |
| `tests/conftest.py` | Shared pytest fixtures: the receiver position, the synthetic aircraft lines, and a waterfall of pure noise. |
| `tests/test_detection_sim.py` | End-to-end logic checks on synthetic scenes with exact truth (sim/synth.py). |
| `tests/test_geometry.py` | The geometry the whole method rests on, checked against finite differences. |
| `tests/test_levers_l1.py` | The optional statistics of jf/field.py, weight="pass" and weight="multi": the logic, checked on synthetic inputs. |
| `tests/test_levers_spec.py` | Checks on the registry of statistics in jf/field.py. |
| `tests/test_noise_injection.py` | Noise injection: add_noise_db must lower the carrier-to-noise ratio by exactly the requested amount, because every "how weak can it be" figure measured on a real recording is read off this axis. |
| `tests/test_null_statistics.py` | What the search reports when there is nothing: the calibration every threshold rests on. |
| `tests/test_rules.py` | The edge cases of jf.rules follow the written definitions. |
| `tests/test_spy_record.py` | tools/spy_record.py must confirm the tune and be able to stop when it cannot. |
| `tests/test_track_gaps.py` | Position feeds at 20-s cadence (OpenSky, adsb.fi far from a receiver) must not silently empty the tracks. |
| `tests/test_truth_isolation.py` | The search package must be truth-free: no path into data/ref, no unsealing, no truth coordinates. |
