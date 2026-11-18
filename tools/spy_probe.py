#!/usr/bin/env python3
"""Pre-flight for a public SpyServer: does it let us tune, and is the wanted carrier there?

In one night of November 2026, five of seven public servers that answered TCP either kept their old centre frequency
(our setting ignored, another client holding control, or a server quirk) or showed no carrier at all, and that
was only found after minutes of recording. This connects, asks for the frequency, waits for a sync that confirms
the device centre, takes a few seconds of IQ, reports level / carrier offset / C/N0 and disconnects. One server at
a time; it holds the slot for well under a minute. Stdlib + numpy.

usage: spy_probe.py host port freq_hz [want_rate_hz=12000] [seconds=8] [gain_index=-1] [digital_gain_db=auto]
exit code 0 = a carrier within +-3 kHz of the centre at >= 25 dB-Hz; 2 = fewer than 2 s of IQ data; 3 = no carrier, or a spur.
A server that sends no sync for the retune is judged by its signal after 20 s, so exit 0 does not prove the tune:
read "tuned_sync" in the printed JSON."""
import json
import socket
import struct
import sys
import time

import numpy as np

PROTO = (2 << 24) | (0 << 16) | 1700
CMD_HELLO, CMD_SET = 0, 2
S_MODE, S_ENABLED, S_GAIN = 0, 1, 2
S_IQ_FORMAT, S_IQ_FREQ, S_IQ_DECIM, S_IQ_DGAIN = 100, 101, 102, 103
FMT_UINT8, FMT_INT16 = 1, 2
MSG_DEVINFO, MSG_SYNC = 0, 1
MSG_IQ = {100: ("u8", 1), 101: ("i16", 2), 102: ("i24", 3), 103: ("f32", 4)}


def recvn(s, n):
    buf = bytearray()
    while len(buf) < n:
        chunk = s.recv(min(65536, n - len(buf)))
        if not chunk:
            raise ConnectionError("server closed")
        buf += chunk
    return bytes(buf)


def cmd(s, ctype, body):
    s.sendall(struct.pack("<II", ctype, len(body)) + body)


def setting(s, stype, *vals):
    cmd(s, CMD_SET, struct.pack("<I", stype) + b"".join(struct.pack("<I", v) for v in vals))


def read_msg(s):
    pid, mtype, stype, seq, size = struct.unpack("<IIIII", recvn(s, 20))
    if size > (1 << 20):
        raise ValueError(f"body too large: {size}")
    return mtype & 0xFFFF, mtype >> 16, seq, recvn(s, size)


def main(host, port, freq, want_rate=12000.0, seconds=8.0, gain=-1, dgain=0xFFFFFFFF):
    t_start = time.time()
    s = socket.create_connection((host, port), timeout=15)
    s.settimeout(15)
    cmd(s, CMD_HELLO, struct.pack("<I", PROTO) + b"jamfinder-research")
    dev = sync = None
    while dev is None or sync is None:
        mt, _, _, body = read_msg(s)
        if mt == MSG_DEVINFO:
            keys = ("type", "serial", "max_rate", "max_bw", "decim_stages", "gain_stages", "max_gain", "min_freq", "max_freq",
                    "resolution", "min_iq_decim", "forced_fmt")
            dev = dict(zip(keys, struct.unpack("<12I", body[:48])))
        elif mt == MSG_SYNC:
            keys = ("can_control", "gain", "dev_cf", "iq_cf", "fft_cf", "min_iq_cf", "max_iq_cf", "min_fft_cf", "max_fft_cf")
            sync = dict(zip(keys, struct.unpack("<9I", body[:36])))
    stage = dev["min_iq_decim"]
    for d in range(dev["min_iq_decim"], dev["decim_stages"] + 1):
        if dev["max_rate"] / (1 << d) >= want_rate:
            stage = d
    rate = dev["max_rate"] / (1 << stage)
    fmt = dev["forced_fmt"] or FMT_INT16
    out = dict(host=host, port=port, freq=freq, device_type=dev["type"], bits=dev["resolution"], can_control=sync["can_control"],
               gain_at_connect=sync["gain"], dev_cf_at_connect=sync["dev_cf"], rate=rate, fmt=fmt)
    setting(s, S_MODE, 1)
    setting(s, S_IQ_FORMAT, fmt)
    setting(s, S_IQ_DECIM, stage)
    setting(s, S_IQ_FREQ, int(freq))
    setting(s, S_IQ_DGAIN, dgain)
    if gain >= 0 and sync["can_control"]:
        setting(s, S_GAIN, gain)
    setting(s, S_ENABLED, 1)
    tuned, chunks, nsamp, kind = False, [], 0, None
    deadline = time.time() + 45
    while time.time() < deadline:
        mt, dg, seq, body = read_msg(s)
        if mt == MSG_SYNC:
            sy = struct.unpack("<9I", body[:36])
            if abs(sy[3] - freq) < 1.0:
                tuned = True
            continue
        if mt in MSG_IQ:
            kind, bps = MSG_IQ[mt]
            if tuned:
                chunks.append(body)
                nsamp += len(body) // (2 * bps)
                if nsamp >= seconds * rate:
                    break
            elif time.time() - t_start > 20 and not tuned:
                # some servers never send a sync for the retune: fall back to judging by the signal after 20 s
                chunks.append(body)
                nsamp += len(body) // (2 * bps)
                if nsamp >= seconds * rate:
                    break
    try:
        setting(s, S_ENABLED, 0)
        s.close()
    except OSError:
        pass
    out.update(tuned_sync=tuned, seconds=nsamp / rate if rate else 0, kind=kind, probe_s=round(time.time() - t_start, 1))
    if nsamp < 2 * rate:
        out["verdict"] = "no IQ data"
        print(json.dumps(out))
        return 2
    raw = np.frombuffer(b"".join(chunks), dtype={"u8": np.uint8, "i16": np.int16}[kind]).astype(np.float32)
    x = (raw - 127.5) / 127.5 if kind == "u8" else raw / 32768.0
    z = x[0::2] + 1j * x[1::2]
    nfft = int(round(rate)); nb = len(z) // nfft
    w = np.hanning(nfft)
    P = np.zeros(nfft)
    for k in range(nb):
        P += np.abs(np.fft.fft(z[k * nfft:(k + 1) * nfft] * w)) ** 2
    f = np.fft.fftfreq(nfft, 1 / rate); o = np.argsort(f); f, P = f[o], P[o] / max(nb, 1) / (np.sum(w) ** 2 / 4)
    Pdb = 10 * np.log10(P + 1e-30)
    win = (np.abs(f) <= 3000) & (np.abs(f) > 20)         # the carrier is expected within +-3 kHz of the centre, not at DC
    k = int(np.argmax(np.where(win, Pdb, -999)))
    noise = float(np.median(Pdb[(np.abs(f - f[k]) > 3) & (np.abs(f - f[k]) < 140)]))
    def rel(off):
        j = int(np.argmin(np.abs(f - (f[k] + off))))
        return round(float(Pdb[j] - Pdb[k]), 1)
    out.update(peak_dbfs=round(float(20 * np.log10(np.abs(z).max() + 1e-12)), 1), rms_dbfs=round(float(20 * np.log10(np.sqrt(np.mean(np.abs(z) ** 2)) + 1e-12)), 1),
               carrier_offset_hz=round(float(f[k]), 1), carrier_dbfs=round(float(Pdb[k]), 1), cn0_dbhz=round(float(Pdb[k] - noise), 1),
               # a VOR carries 30 Hz AM and a 9960 Hz subcarrier, each about -16 dB; a receiver spur carries neither and has
               # an image and harmonics at the carrier's own level
               am30_db=max(rel(30), rel(-30)), sub9960_db=max(rel(9960), rel(-9960)) if rate > 2 * 9960 else None,
               image_db=round(float(Pdb[int(np.argmin(np.abs(f + f[k])))] - Pdb[k]), 1), harmonic2_db=rel(f[k]))
    out["verdict"] = "carrier" if out["cn0_dbhz"] >= 25 else "no carrier"
    if out["verdict"] == "carrier" and out["image_db"] > -10 and out["harmonic2_db"] > -10:
        out["verdict"] = "spur (image and harmonic at carrier level)"
    print(json.dumps(out))
    return 0 if out["verdict"] == "carrier" else 3


if __name__ == "__main__":
    a = sys.argv
    sys.exit(main(a[1], int(a[2]), float(a[3]), float(a[4]) if len(a) > 4 else 12000.0, float(a[5]) if len(a) > 5 else 8.0,
                  int(a[6]) if len(a) > 6 else -1, int(a[7]) if len(a) > 7 else 0xFFFFFFFF))
