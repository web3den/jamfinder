"""Synthetic receiver signal: one transmitter, many aircraft echoes, noise.

The output has the same form as jf.scatter.baseband(), so the real search
code runs on it unchanged. The transmitter can be put anywhere, which gives
tests with exact truth.

Signal model, at 1250 samples/s around the carrier:

    y(t) = e^{j phi_rx(t)} s(t) [ A_d + sum_k a_k(t) e^{-j 2 pi (R1_k + R2_k - R0) / lambda} ] + n(t)

    s(t)      transmitter: carrier with slow drift, phase noise and (optional) voice AM
    A_d       direct signal (set by C/N0 of the direct path)
    a_k       echo amplitude: radar equation x receiver sky mask x slow fading
    R1, R2    transmitter-aircraft and aircraft-receiver distances; R0 the direct distance
    phi_rx    receiver oscillator wander
    n         white noise, variance 1 per sample

Echo strength follows what was measured at Helsinki on 135.075 MHz
(a fit to two Boeing 737 arrivals and ten weaker aircraft, 497 blocks of 10 s):
    echo power / noise density = K - 20 log10(R1 R2) + G(elevation) + A(aspect) + size + fading   [dB-Hz]
    K         174.5 dB for a 10 W transmitter, airliner seen from the side (see below)
    G         0 dB above 8 degrees elevation from the receiver, below that 20 log10(sin el / sin 8 deg)
              (a receiving antenna a few metres above a flat roof or ground does this)
    A         -12 dB when the aircraft points at (or away from) the transmitter and receiver
    size      -10 dB for aircraft that are not airliners
    fading    6 dB, changing over about 10 s
The direct signal there is 39 dB weaker than free space (the transmitter is hidden from the receiver).

How far to trust it. The shape of the law was fitted to the clearly visible echo blocks, which gave
K = 182.5 dB. With that value the simulated search scores came out 2.5 times the real ones at every
power level (three attempts at a better shape did not close the gap: the visible blocks are the lucky
ones, departures low over the airfield are much weaker than the law says, and real echoes are short).
So K is set 8 dB lower, to the one value that makes the simulated scores match the real ones at
full power and at 10, 15 and 20 dB less (the real recording with noise added).
Use the simulator for geometry questions (where can a transmitter be found, mirror images, coverage
shape). For "how weak can it be", trust it to about +-5 dB and prefer the real recordings.
"""
import numpy as np
from scipy.interpolate import CubicSpline

K_DB = 174.5          # echo power / N0 at R1 R2 = 1 m^2 for 10 W, side view: the value that makes simulated
                      # search scores equal the real ones (the visible echo blocks alone give 182.5)
K_PEAK_DB = 182.5     # fitted to the clearly visible blocks only
ASPECT_DB = -12.0     # nose-on or tail-on, relative to side view
DIRECT_FS_DB = 175.2  # direct power / N0 at 1 m in free space for 10 W (taking K = 184.2 dB as 100 m^2)


AIRLINERS = ("A3", "A2", "B7", "B3", "BCS", "E1", "E2", "E7", "E9", "AT7", "DH8", "CRJ", "MD", "B4")


def sky_mask_db(el_deg, plateau_deg=8.0):
    """Receiver gain towards an aircraft at this elevation (dB): 0 above plateau_deg, falling as sin^2 below."""
    el = np.radians(np.maximum(np.asarray(el_deg, float), 0.05))
    return np.minimum(0.0, 20 * np.log10(np.sin(el) / np.sin(np.radians(plateau_deg))))


def size_db(actype, small=-10.0):
    """Airliners 0 dB; anything else (light aircraft, helicopters, unknown military types) weaker."""
    return 0.0 if str(actype).upper().startswith(AIRLINERS) or str(actype) in ("?", "SIM") else small


def aspect_db(vel, d1, d2, depth=ASPECT_DB):
    """Echo strength against viewing direction: weakest nose-on or tail-on, strongest from the side.

    vel: aircraft velocity; d1, d2: vectors from transmitter and receiver to the aircraft.
    """
    b = -(d1 / np.linalg.norm(d1, axis=1, keepdims=True) + d2 / np.linalg.norm(d2, axis=1, keepdims=True))
    nb = np.linalg.norm(b, axis=1)
    nv = np.linalg.norm(vel, axis=1)
    c = np.abs(np.sum(vel * b, axis=1)) / np.maximum(nb * nv, 1e-9)
    return depth * c * c


def _slow_noise(rng, n, fs, tau, sigma):
    """Gauss-Markov sequence with standard deviation sigma and correlation time tau (s)."""
    if sigma <= 0:
        return np.zeros(n)
    rho = np.exp(-1.0 / (tau * fs))
    w = rng.standard_normal(n) * sigma * np.sqrt(1 - rho * rho)
    x = np.empty(n)
    acc = rng.standard_normal() * sigma
    for i in range(n):
        acc = rho * acc + w[i]
        x[i] = acc
    return x


class Scene:
    """What the simulator needs to know about one site."""

    def __init__(self, paths, rx, lam, t0, dur, fs=1250.0):
        self.paths, self.rx, self.lam = paths, np.asarray(rx, float), lam
        self.t0, self.dur, self.fs = float(t0), float(dur), float(fs)
        self.n = int(round(dur * fs))

    def synth(self, tx, power_db=0.0, direct_cn0_db=None, obstruction_db=39.1, k_db=K_DB,
              plateau_deg=8.0, aspect=ASPECT_DB, fade_db=6.0, fade_tau=10.0, glint_rad=0.5, glint_tau=3.0,
              latency=(0.0, 0.5), pos_sigma=10.0, rx_drift_hz=3.0, tx_drift_hz=0.3, am_rms=0.0,
              direct=True, only=None, seed=0, tx_vel=None, extra=()):
        """Make a capture. Returns (bb, truth).

        power_db       transmitter power relative to 10 W
        direct_cn0_db  C/N0 of the direct signal; default: free space minus obstruction_db
        latency        each aircraft's position reports are late by a value drawn from this range (s)
        pos_sigma      each aircraft's reported track is off by a fixed horizontal error of this size (m)
        direct=False   no direct signal at all (transmitter hidden from the receiver)
        only           if given, only these aircraft (hex codes) scatter
        extra          more transmitters on the same channel: [(tx2, power2_db, offset_hz), ...]; each has its own
                       direct signal (same obstruction) and echoes, and sits offset_hz away from the first carrier
        """
        rng = np.random.default_rng(seed)
        tx = np.asarray(tx, float)
        fs, n, lam = self.fs, self.n, self.lam
        t = self.t0 + np.arange(n) / fs
        R0 = float(np.linalg.norm(tx - self.rx))
        if direct_cn0_db is None:
            direct_cn0_db = DIRECT_FS_DB + power_db - 20 * np.log10(R0) - obstruction_db
        A_d = np.sqrt(10 ** (direct_cn0_db / 10.0) / fs) if direct else 0.0
        tc = self.t0 + np.arange(0.0, self.dur + 0.2, 0.1)   # coarse time grid, 10 Hz
        truth = dict(latency={}, bias={}, cn0={}, direct_cn0_db=float(direct_cn0_db) if direct else None)
        # the same lateness and track error for every transmitter: they belong to the aircraft, not the signal
        ac = {}
        for h, p in self.paths.items():
            if only is not None and h not in only:
                continue
            ac[h] = (float(rng.uniform(*latency)), np.r_[rng.standard_normal(2) * pos_sigma, 0.0])

        def echoes(txk, pwk):
            out = np.zeros(n, np.complex128)
            R0k = float(np.linalg.norm(txk - self.rx))
            for h, p in self.paths.items():
                if h not in ac:
                    continue
                lat, bias = ac[h]
                ok = p.valid(tc + lat)
                if ok.sum() < 20:
                    continue
                pos = p.pos(tc + lat) + bias
                d1, d2 = pos - txk, pos - self.rx
                R1, R2 = np.linalg.norm(d1, axis=1), np.linalg.norm(d2, axis=1)
                el2 = np.degrees(np.arcsin(np.clip(d2[:, 2] / R2, -1, 1)))
                p_db = (k_db + pwk - 20 * np.log10(np.maximum(R1 * R2, 1e4))
                        + sky_mask_db(el2, plateau_deg) + aspect_db(p.vel(tc + lat), d1, d2, aspect) + size_db(p.actype)
                        + _slow_noise(rng, len(tc), 10.0, fade_tau, fade_db))
                p_db = np.where(ok, p_db, -300.0)
                amp_c = np.sqrt(10 ** (p_db / 10.0) / fs)
                ph_c = -2 * np.pi * (R1 + R2 - R0k) / lam + _slow_noise(rng, len(tc), 10.0, glint_tau, glint_rad)
                i0, i1 = np.searchsorted(t, [tc[ok][0], tc[ok][-1]])
                if i1 - i0 < 10:
                    continue
                ts = t[i0:i1]
                amp = np.interp(ts, tc, amp_c)
                ph = CubicSpline(tc, ph_c)(ts)
                out[i0:i1] += amp * np.exp(1j * ph)
                if txk is tx:
                    truth["latency"][h], truth["bias"][h] = lat, bias
                    truth["cn0"][h] = float(np.max(p_db))
            return out

        echo = echoes(tx, power_db)
        others = np.zeros(n, np.complex128)
        truth["extra"] = []
        for tx2, pw2, off in extra:
            tx2 = np.asarray(tx2, float)
            cn0_2 = DIRECT_FS_DB + pw2 - 20 * np.log10(float(np.linalg.norm(tx2 - self.rx))) - obstruction_db
            A_2 = np.sqrt(10 ** (cn0_2 / 10.0) / fs) if direct else 0.0
            others += (A_2 + echoes(tx2, pw2)) * np.exp(2j * np.pi * off * (np.arange(n) / fs))
            truth["extra"].append(dict(tx=tx2.tolist(), power_db=float(pw2), offset_hz=float(off), direct_cn0_db=float(cn0_2)))
        # transmitter and receiver oscillators: slow wander, common to direct signal and echoes
        tsec = np.arange(n) / fs
        f_tx = _slow_noise(rng, int(self.dur) + 2, 1.0, 120.0, tx_drift_hz)
        f_rx = _slow_noise(rng, int(self.dur) + 2, 1.0, 200.0, rx_drift_hz)
        f_osc = np.interp(tsec, np.arange(len(f_tx)), f_tx + f_rx)
        osc = np.exp(2j * np.pi * np.cumsum(f_osc) / fs)
        truth["f0"] = (self.t0 + np.arange(len(f_tx), dtype=float), f_tx + f_rx)   # carrier frequency path (Hz)
        s = 1.0
        if am_rms > 0:   # voice: amplitude modulation, mostly above 140 Hz
            from scipy import signal
            sos = signal.butter(4, [140 / (fs / 2), 600 / (fs / 2)], btype="band", output="sos")
            m = signal.sosfilt(sos, rng.standard_normal(n))
            s = 1.0 + am_rms * m / m.std()
        if tx_vel is not None:
            raise NotImplementedError("moving transmitter")
        noise = (rng.standard_normal(n) + 1j * rng.standard_normal(n)) / np.sqrt(2)
        y = osc * (s * (A_d + echo) + others) + noise
        bb = dict(y=y.astype(np.complex64), fs=np.float64(fs), t0=np.float64(self.t0), scale=np.float64(1.0),
                  carrier_hz=np.float64(0.0))
        return bb, truth


class Line:
    """A made-up aircraft: straight flight at constant speed and height (same interface as tracks.Path)."""

    def __init__(self, t_start, t_end, p0, v, name="SIM"):
        self.t0, self.t1 = float(t_start), float(t_end)
        self.p0, self.v = np.asarray(p0, float), np.asarray(v, float)
        self.flight, self.actype, self.src = name, "SIM", "sim"

    def valid(self, t):
        t = np.asarray(t, float)
        return (t >= self.t0) & (t <= self.t1)

    def pos(self, t):
        t = np.clip(np.asarray(t, float), self.t0, self.t1)
        return self.p0 + (t - self.t0)[..., None] * self.v

    def vel(self, t):
        return np.broadcast_to(self.v, np.shape(t) + (3,)).copy()
