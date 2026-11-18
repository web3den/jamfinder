#!/usr/bin/env python3
"""Put back the blocks of samples that a busy SDR server left out of a recording.

Some public servers lose whole blocks of samples now and then. The recording then holds fewer samples than
its length in seconds says, its time base wanders, and the steady carrier jumps in phase at every loss.
We find the losses on the carrier itself: N missing samples turn the carrier by 2*pi*f_c*N/fs, so with
blocks of `block` samples every loss shows as a phase step of a known size (or two, three times that size).
Each loss is filled with a stretch of plain carrier of the right length. The first samples after a loss
come out of the server's filters disturbed, so they are replaced the same way.

Nothing here knows about aircraft or about where the transmitter is.

Checks printed at the end, both independent of how the losses were found:
  - how many phase steps are left when the same detector runs on the repaired recording
  - the sample rate and the wander of the time base from the message arrival times, before and after

usage: fix_drops.py in_prefix out_prefix [block=32 thr=0.3 tol=0.2 max_units=4 before=4 after=40 car_lo= car_hi=]
"""
import json
import os
import sys

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from jf import iq  # noqa: E402


def find_steps(x, fs, fc0, thr):
    """Sudden turns of the carrier phase. Returns ([(raw index, size in rad, carrier Hz)], robust sigma, window, threshold).

    The step measure compares the mean phase over L samples before and after each point. For a weak carrier the
    measure is noisy, so L grows until its scatter is about 0.08 rad (at most 0.2 s), and the threshold is at
    least four times the scatter.
    """
    y, fs2 = iq.to_baseband(x, fs, fc0)
    q = int(round(fs / fs2))
    yf, ftrack = iq.remove_drift(y, fs2)
    c = np.concatenate([[0.0], np.cumsum(yf.astype(np.complex128))])
    g, L = 2, 12
    for _ in range(3):
        n = np.arange(L + g, len(yf) - L - g)
        s = np.angle((c[n + g + L] - c[n + g]) * np.conj(c[n - g] - c[n - g - L]))
        sig = 1.4826 * np.median(np.abs(s - np.median(s)))
        if sig <= 0.08 or L >= 240:
            break
        L = int(min(240, max(L + 1, 12 * (sig / 0.08) ** 2)))
    thr_eff = max(thr, 4 * sig)
    big = np.flatnonzero(np.abs(s) > thr_eff)
    out, i = [], 0
    while i < len(big):
        j = i
        while j + 1 < len(big) and big[j + 1] - big[j] <= max(int(0.03 * fs2), L):
            j += 1
        seg = big[i:j + 1]
        k = seg[np.argmax(np.abs(s[seg]))]
        out.append((int(n[k]) * q, float(s[k]), fc0 + float(ftrack[n[k]])))
        i = j + 1
    return out, float(sig), L, float(thr_eff)


def clock_check(meta):
    """Sample rate and wander of the time base (ms) from the message arrival times."""
    m = np.array([(a[0], a[1]) for a in meta["msgs"]], dtype=float)
    t0, rate = iq.sample_clock(meta, int(meta["nsamp"]))
    resid = m[:, 0] - (t0 + m[:, 1] / rate)
    per_min = int(60 * meta["rate"] / 96)
    low = np.array([resid[a:a + per_min].min() for a in range(0, len(resid) - per_min, per_min)])
    return rate, 1e3 * (low.min() - np.median(low)), 1e3 * (low.max() - np.median(low))


if __name__ == "__main__":
    src, dst = sys.argv[1:3]
    opt = dict(a.split("=", 1) for a in sys.argv[3:])
    block, thr, tol = int(opt.get("block", 32)), float(opt.get("thr", 0.3)), float(opt.get("tol", 0.2))
    max_units = int(opt.get("max_units", 4))
    pre, post = int(opt.get("before", 4)), int(opt.get("after", 40))
    x, fs, meta = iq.load(src)
    x = x[:int(meta["nsamp"])]
    lo, hi = opt.get("car_lo"), opt.get("car_hi")
    fc0 = iq.find_carrier(x, fs, float(lo), float(hi)) if lo is not None else iq.find_carrier(x, fs)
    steps, sig, L, thr_eff = find_steps(x, fs, fc0, thr)
    print(f"{len(x)} samples, carrier near {fc0:+.1f} Hz; {len(steps)} phase steps above {thr_eff:.2f} rad "
          f"(window {L} samples, ordinary scatter of the step measure {sig:.3f} rad)", flush=True)

    # look at each step at the full sample rate: where exactly, and how large once things have settled
    H, W = 400, 152
    found, odd = [], []
    for n0, size, fc in steps:
        if n0 - H < 0 or n0 + H + 64 > len(x):
            continue
        w = 2 * np.pi * fc / fs
        xd = x[n0 - H:n0 + H].astype(np.complex128) * np.exp(-1j * w * np.arange(-H, H))
        c = np.concatenate([[0.0], np.cumsum(xd)])
        a = c[H - 80] / (H - 80)
        ks = np.arange(H - 60, H + 60)
        d = np.abs((c[ks + 12] - c[ks]) / 12 - a) - np.abs((c[ks] - c[ks - 12]) / 12 - a)
        k = int(ks[np.argmax(d)])
        before = c[k - 8] - c[k - 8 - W]
        after = c[k + post + 4 + W] - c[k + post + 4]
        step = float(np.angle(after * np.conj(before)))
        unit = float(np.angle(np.exp(1j * w * block)))          # one lost block turns the carrier this much
        u = int(round(step / unit)) if abs(unit) > 0.05 else 0
        if 1 <= u <= max_units and abs(step - u * unit) < tol:
            found.append([n0 - H + k, u, fc, step, unit])
        else:
            odd.append([n0 / fs, size, step])
    found = np.array(found).reshape(-1, 5)
    grid = int(np.bincount(found[:, 0].astype(int) % block, minlength=block).argmax()) if len(found) else 0
    off = (found[:, 0].astype(int) - grid + block // 2) % block - block // 2
    print(f"{len(found)} steps fit a whole number of lost blocks of {block} samples: " +
          ", ".join(f"{int((found[:, 1] == u).sum())} x {u}" for u in range(1, max_units + 1) if (found[:, 1] == u).any()) +
          f"; {len(odd)} steps do not fit and are left alone")
    if len(found):
        print(f"   one block turns the carrier by {np.median(found[:, 4]):+.3f} rad; measured for single losses "
              f"{np.median(found[found[:, 1] == 1, 3]) if (found[:, 1] == 1).any() else float('nan'):+.3f}, for double losses "
              f"{np.median(found[found[:, 1] == 2, 3]) if (found[:, 1] == 2).any() else float('nan'):+.3f}")
        print(f"   losses sit at sample index = {grid} modulo {block}: {int((np.abs(off) <= 2).sum())} of {len(found)} within 2 samples")
    for t, s0, s1 in odd[:12]:
        print(f"   left alone: at {t:8.1f} s, quick measure {s0:+.2f} rad, settled {s1:+.2f} rad")

    # build the repaired recording
    parts, shift_at, shift_by, pos, added = [], [], [], 0, 0
    for k, u, fc, step, unit in found:
        k = int(k)
        o = (k - grid + block // 2) % block - block // 2
        if abs(o) <= 8:
            k -= o                                   # losses fall on the server's block grid
        p0, p1, G = k - pre, k + post, int(u) * block
        if p0 - 96 < pos or p1 + 96 > len(x):
            continue
        w = 2 * np.pi * fc / fs
        cb = np.mean(x[p0 - 96:p0] * np.exp(-1j * w * (np.arange(p0 - 96, p0) - k)))
        ca = np.mean(x[p1:p1 + 96] * np.exp(-1j * w * (np.arange(p1, p1 + 96) + G - k)))
        m = np.arange(p0 - k, p1 - k + G)
        frac = (m - m[0] + 0.5) / len(m)
        fill = (cb + (ca - cb) * frac) * np.exp(1j * w * m)
        parts.append(x[pos:p0])
        parts.append(fill.astype(np.complex64))
        pos = p1
        added += G
        shift_at.append(p1)
        shift_by.append(added)
    parts.append(x[pos:])
    # sanity gate, independent of the detector: the message arrival times say how many samples are missing in total
    r0, a0, b0 = clock_check(meta)
    missing = max(0.0, len(x) / fs * (1 - r0 / fs))
    planned = added / fs
    if len(found) == 0 or planned > 1.5 * missing + 0.5:
        reason = "no lost blocks found" if len(found) == 0 else \
            f"the detector proposed {planned:.2f} s but the arrival-time clock says only {missing:.2f} s are missing"
        print(f"repair NOT applied ({reason}); the recording is written through unchanged", flush=True)
        y, shift_at, shift_by, added, applied = x, [], [], 0, False
    else:
        y, applied = np.concatenate(parts), True
        print(f"put back {added} samples ({added / fs:.3f} s) at {len(shift_at)} places (clock deficit {missing:.2f} s); "
              f"{len(x)} -> {len(y)} samples", flush=True)
    del parts

    os.makedirs(os.path.dirname(dst), exist_ok=True)
    y.view(np.float32).tofile(dst + ".iq")
    new = dict(meta)
    idx = np.array([m[1] for m in meta["msgs"]])
    moved = idx + np.concatenate([[0], shift_by])[np.searchsorted(shift_at, idx, side="right")]
    new["msgs"] = [[m[0], int(i), 0] for m, i in zip(meta["msgs"], moved)]
    new.update(kind="f32", nsamp=int(len(y)))
    new["repaired"] = dict(source=os.path.abspath(src), applied=applied, block=block, places=len(shift_at), samples_added=int(added),
                           singles=int((found[:, 1] == 1).sum()), doubles=int((found[:, 1] == 2).sum()),
                           left_alone=[[float(v) for v in o] for o in odd], grid=grid,
                           where=[[int(a), int(b)] for a, b in zip(shift_at, shift_by)])
    with open(dst + ".json", "w") as g:
        json.dump(new, g)

    # checks
    left, sig2, _, _ = find_steps(y, fs, fc0, thr)
    print(f"check 1: the same detector on the repaired recording finds {len(left)} steps (before: {len(steps)}); "
          f"scatter of the step measure {sig2:.3f} rad")
    r0, a0, b0 = clock_check(meta)
    r1, a1, b1 = clock_check(new)
    print(f"check 2: sample rate from arrival times {r0:.3f} Hz ({1e6 * (r0 / fs - 1):+.0f} ppm) -> {r1:.3f} Hz "
          f"({1e6 * (r1 / fs - 1):+.0f} ppm); time base wander per minute {a0:+.0f}..{b0:+.0f} ms -> {a1:+.0f}..{b1:+.0f} ms")
    print("written", dst + ".iq")
