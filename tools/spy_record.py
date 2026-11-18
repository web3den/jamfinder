#!/usr/bin/env python3
"""Record narrowband IQ from a public SpyServer (Airspy network protocol).

Writes raw interleaved IQ in the server's format to <out>.iq and a sidecar
<out>.json with sample rate, centre frequency and, for every message, the
wall-clock time, first sample index and digital gain in dB (so sample index
-> UTC is recoverable to ~0.1 s and samples can be rescaled).
Stdlib only.

usage: spy_record.py host port freq_hz want_rate_hz seconds out_prefix
                     [gain_index|-1] [digital_gain_db]
                     [require_tune=0|1] [tune_timeout=60] [iq_timeout=30]

The key=value words may stand anywhere after the six required arguments; they are taken out before the
positional ones are read, so a command line without them behaves exactly as it always did.

Tune check (added 2026-11-16, after public servers accepted a frequency and never retuned, or sent no IQ, and
that was found only minutes into a recording). The sidecar always carries tuned_confirmed (true once a SYNC that
arrives after our settings reports iq_cf within 1 Hz of freq_hz), tune_confirmed_after_s and first_iq_after_s
(seconds since connect; null until it happens). IQ that arrives before the confirming SYNC is still written; the
sample index of that SYNC is in "syncs". Without require_tune, a tune not confirmed tune_timeout seconds after
connect only prints one warning line. With require_tune=1 the recorder stops (disable setting, close), writes the
sidecar with "aborted" and exits with code 2 ("not tuned": no confirming SYNC within tune_timeout seconds) or
code 3 ("no IQ data": no IQ message within iq_timeout seconds); both clocks run from connect. The same two
outcomes apply if the recording ends (time up, connection lost) before the tune is confirmed or any IQ arrives.
Real servers confirmed a retune after 21, 55 and 179 s (2026-11-16), so raise tune_timeout for slow ones.
"""
import json
import os
import select
import socket
import struct
import sys
import time

PROTO = (2 << 24) | (0 << 16) | 1700
CMD_HELLO, CMD_SET = 0, 2
S_MODE, S_ENABLED, S_GAIN = 0, 1, 2
S_IQ_FORMAT, S_IQ_FREQ, S_IQ_DECIM, S_IQ_DGAIN = 100, 101, 102, 103
FMT_UINT8, FMT_INT16, FMT_FLOAT = 1, 2, 4
MSG_DEVINFO, MSG_SYNC = 0, 1
MSG_IQ = {100: ("u8", 1), 101: ("i16", 2), 102: ("i24", 3), 103: ("f32", 4)}
OPT_DEFAULTS = {"require_tune": False, "tune_timeout": 60.0, "iq_timeout": 30.0}
EXIT_NOT_TUNED, EXIT_NO_IQ = 2, 3


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


def split_options(words):
    """Take require_tune= / tune_timeout= / iq_timeout= out of the command line; return (other words, options).

    Any other NAME=value word is refused: a misspelt safety option must not be ignored silently."""
    opts, rest = dict(OPT_DEFAULTS), []
    for w in words:
        key, eq, val = w.partition("=")
        if key not in OPT_DEFAULTS and not (eq and key.replace("-", "_").isidentifier()):
            rest.append(w)                  # a positional argument: host, number, path
            continue
        ok = False
        if key == "require_tune":
            ok = val in ("0", "1")
            opts[key] = val == "1"
        elif key in OPT_DEFAULTS:
            try:
                opts[key] = float(val)
                ok = opts[key] > 0          # also refuses nan
            except ValueError:
                pass
        if not ok:
            sys.exit(f"spy_record: bad option {w!r}; allowed: require_tune=0|1 tune_timeout=SECONDS iq_timeout=SECONDS")
    return rest, opts


def main(host, port, freq, want_rate, seconds, out, gain, dgain=0xFFFFFFFF,
         require_tune=False, tune_timeout=60.0, iq_timeout=30.0):
    s = socket.create_connection((host, port), timeout=15)
    t_conn = time.monotonic()               # tune_timeout, iq_timeout and the *_after_s fields count from here
    s.settimeout(15)
    cmd(s, CMD_HELLO, struct.pack("<I", PROTO) + b"jamfinder-research")
    dev = sync = None
    while dev is None or sync is None:
        mt, _, _, body = read_msg(s)
        if mt == MSG_DEVINFO:
            keys = ("type", "serial", "max_rate", "max_bw", "decim_stages", "gain_stages",
                    "max_gain", "min_freq", "max_freq", "resolution", "min_iq_decim", "forced_fmt")
            dev = dict(zip(keys, struct.unpack("<12I", body[:48])))
        elif mt == MSG_SYNC:
            keys = ("can_control", "gain", "dev_cf", "iq_cf", "fft_cf", "min_iq_cf",
                    "max_iq_cf", "min_fft_cf", "max_fft_cf")
            sync = dict(zip(keys, struct.unpack("<9I", body[:36])))
    print("device", dev, flush=True)
    print("sync", sync, flush=True)
    # decimation stage closest to (but not below) the wanted rate
    stage = dev["min_iq_decim"]
    for d in range(dev["min_iq_decim"], dev["decim_stages"] + 1):
        if dev["max_rate"] / (1 << d) >= want_rate:
            stage = d
    rate = dev["max_rate"] / (1 << stage)
    fmt = dev["forced_fmt"] or FMT_INT16
    setting(s, S_MODE, 1)
    setting(s, S_IQ_FORMAT, fmt)
    setting(s, S_IQ_DECIM, stage)
    setting(s, S_IQ_FREQ, int(freq))
    # digital gain in dB after decimation; 0xFFFFFFFF = server picks it.
    # Without it an 8-bit stream throws away the decimation gain.
    setting(s, S_IQ_DGAIN, dgain)
    if gain >= 0 and sync["can_control"]:
        setting(s, S_GAIN, gain)
    setting(s, S_ENABLED, 1)
    meta = {"host": host, "port": port, "freq": freq, "rate": rate, "stage": stage,
            "fmt": fmt, "dev": dev, "sync0": sync, "t_start": time.time(), "msgs": [],
            "tuned_confirmed": False, "tune_confirmed_after_s": None, "first_iq_after_s": None}
    t_end = time.time() + seconds
    nsamp, last_seq, drops, kind = 0, None, 0, None

    def since_connect():
        return time.monotonic() - t_conn

    def last_iq_cf():
        return meta["syncs"][-1][5] if meta.get("syncs") else sync["iq_cf"]

    def save(final):
        # also called once a minute, so a partial recording can be read (or survives a lost connection)
        meta.update({"kind": kind, "nsamp": nsamp, "drops": drops, "t_end": time.time(), "partial": not final})
        with open(out + ".json.tmp", "w") as g:
            json.dump(meta, g)
        os.replace(out + ".json.tmp", out + ".json")

    t_save, err, warned, aborted = time.time() + 60, None, False, None
    with open(out + ".iq", "wb") as f:
        while time.time() < t_end:
            # The tune check: two clocks that run from connect. With require_tune they end the recording;
            # without it an unconfirmed tune only prints one warning.
            clocks = []                     # seconds left on each clock that is still running
            if not meta["tuned_confirmed"]:
                left = tune_timeout - since_connect()
                if left > 0:
                    clocks.append(left)
                elif require_tune:
                    aborted = "not tuned"
                    break
                elif not warned:
                    warned = True
                    print(f"WARNING: tune not confirmed {tune_timeout:g} s after connect: no SYNC with iq_cf within "
                          f"1 Hz of {freq:.0f} Hz yet (last iq_cf {last_iq_cf()}); recording continues", flush=True)
            if require_tune and meta["first_iq_after_s"] is None:
                left = iq_timeout - since_connect()
                if left <= 0:
                    aborted = "no IQ data"
                    break
                clocks.append(left)
            if require_tune and clocks and not select.select([s], [], [], min(clocks + [1.0]))[0]:
                continue                    # nothing to read yet: a silent server must not hide the clocks in read_msg
            try:
                mt, dg, seq, body = read_msg(s)
            except (OSError, ConnectionError) as e:
                err = repr(e)
                break
            if time.time() > t_save:
                f.flush()
                save(False)
                t_save = time.time() + 60
            if mt == MSG_SYNC:
                sy = struct.unpack("<9I", body[:36])
                meta.setdefault("syncs", []).append([round(time.time(), 3), nsamp] + list(sy))
                if not meta["tuned_confirmed"] and abs(sy[3] - freq) <= 1.0:
                    meta["tuned_confirmed"] = True
                    meta["tune_confirmed_after_s"] = round(since_connect(), 3)
                continue
            if mt not in MSG_IQ:
                continue
            kind, bps = MSG_IQ[mt]
            if meta["first_iq_after_s"] is None:
                meta["first_iq_after_s"] = round(since_connect(), 3)
            if last_seq is not None and seq != (last_seq + 1) & 0xFFFFFFFF:
                drops += 1
            last_seq = seq
            f.write(body)
            meta["msgs"].append([round(time.time(), 4), nsamp, dg])
            nsamp += len(body) // (2 * bps)
    if require_tune and aborted is None:    # the recording ended (time up, connection lost) before the checks were passed
        if not meta["tuned_confirmed"]:
            aborted = "not tuned"
        elif meta["first_iq_after_s"] is None:
            aborted = "no IQ data"
    try:
        setting(s, S_ENABLED, 0)
        s.close()
    except OSError:
        pass
    if aborted:
        meta["aborted"] = aborted
    save(True)
    if err:
        print("connection lost:", err, flush=True)
    if aborted:
        if aborted == "not tuned":
            print(f"aborted: not tuned (no SYNC with iq_cf within 1 Hz of {freq:.0f} Hz {since_connect():.1f} s after "
                  f"connect; last iq_cf {last_iq_cf()}); exit code {EXIT_NOT_TUNED}", flush=True)
            return EXIT_NOT_TUNED
        print(f"aborted: no IQ data (no IQ message {since_connect():.1f} s after connect); exit code {EXIT_NO_IQ}", flush=True)
        return EXIT_NO_IQ
    dur = meta["t_end"] - meta["t_start"]
    print(f"done: {nsamp} samples ({kind}) at {rate:.1f} Hz nominal, "
          f"{nsamp/dur:.1f} Hz observed, drops={drops}", flush=True)
    return 0


if __name__ == "__main__":
    words, opt = split_options(sys.argv[1:])
    a = [sys.argv[0]] + words
    sys.exit(main(a[1], int(a[2]), float(a[3]), float(a[4]), float(a[5]), a[6],
                  int(a[7]) if len(a) > 7 else -1,
                  int(a[8]) if len(a) > 8 else 0xFFFFFFFF,
                  require_tune=opt["require_tune"], tune_timeout=opt["tune_timeout"], iq_timeout=opt["iq_timeout"]))
