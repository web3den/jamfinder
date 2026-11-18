"""tools/spy_record.py must confirm the tune and be able to stop when it cannot.

Found 2026-11-16: public SpyServers accepted a frequency and never retuned, or sent no IQ at all, and that was only
noticed minutes into a recording. spy_record now records whether a SYNC after our settings reported the requested
centre (tuned_confirmed), and with require_tune=1 gives up after tune_timeout / iq_timeout seconds (exit 2 / exit 3).

Everything runs against a fake SpyServer on 127.0.0.1; nothing else is contacted. The fake speaks only the part of
the protocol spy_record uses. On HELLO it sends DEVINFO and a SYNC with the device at 100 MHz. It reads and remembers
the settings the client sends. After IQ_FREQ a server set to honour the tune sends a SYNC carrying the requested
frequency (after `tune_delay` seconds, if given); one that ignores the tune says nothing. Once the stream is enabled
it sends uint8 IQ messages, 20 a second, until the client disconnects (or none at all if told not to). spy_record
runs as a subprocess with its files in tmp_path."""
import json
import select
import socket
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

SPY_RECORD = Path(__file__).resolve().parents[1] / "tools" / "spy_record.py"
PROTO = (2 << 24) | 1700
CMD_HELLO, CMD_SET = 0, 2
S_ENABLED, S_GAIN, S_IQ_FREQ, S_IQ_DGAIN = 1, 2, 101, 103
MSG_DEVINFO, MSG_SYNC, MSG_IQ_U8 = 0, 1, 100
FREQ = 114198500                # a VOR carrier, inside the fake device's range
START_CF = 100000000            # where the fake device sits until it is retuned
DEVINFO = struct.pack("<12I", 3, 0, 2400000, 2000000, 9, 0, 29, 24000000, 1800000000, 8, 0, 1)
IQ_BODY = bytes(range(200))     # 100 uint8 IQ samples


def message(mtype, body, seq=0, stream=0):
    """Header of five uint32 (protocol id, type with the digital gain in the upper 16 bits, stream, sequence, size)."""
    return struct.pack("<IIIII", PROTO, mtype, stream, seq, len(body)) + body


def sync(freq):
    """SYNC: can_control 1, gain 10, the three centre frequencies, then the limits."""
    return message(MSG_SYNC, struct.pack("<9I", 1, 10, freq, freq, freq, 25000000, 1799000000, 25000000, 1799000000))


class FakeSpyServer:
    """One client, one thread, a free port on 127.0.0.1."""

    def __init__(self, honour_tune=True, stream=True, tune_delay=0.0):
        self.honour_tune, self.stream, self.tune_delay = honour_tune, stream, tune_delay
        self.settings = []              # (setting type, values) in the order the client sent them
        self._stop = threading.Event()
        self._listener = socket.socket()
        self._listener.bind(("127.0.0.1", 0))
        self._listener.listen(1)
        self.port = self._listener.getsockname()[1]
        self._thread = threading.Thread(target=self._serve, daemon=True)
        self._thread.start()

    def _serve(self):
        self._listener.settimeout(0.1)
        try:
            while not self._stop.is_set():
                try:
                    conn, _ = self._listener.accept()
                except socket.timeout:
                    continue
                with conn:
                    self._talk(conn)
                return
        except OSError:
            pass                        # the client went away in the middle of a send
        finally:
            self._listener.close()

    def _talk(self, conn):
        inbuf, seq, enabled = b"", 0, False
        next_iq, sync_due = 0.0, None
        while not self._stop.is_set():
            if select.select([conn], [], [], 0.02)[0]:
                data = conn.recv(4096)
                if not data:
                    return              # the client closed the connection
                inbuf += data
                while len(inbuf) >= 8 and len(inbuf) >= 8 + struct.unpack_from("<II", inbuf)[1]:
                    ctype, size = struct.unpack_from("<II", inbuf)
                    body, inbuf = inbuf[8:8 + size], inbuf[8 + size:]
                    if ctype == CMD_HELLO:
                        conn.sendall(message(MSG_DEVINFO, DEVINFO) + sync(START_CF))
                    elif ctype == CMD_SET:
                        stype, *vals = struct.unpack(f"<{len(body) // 4}I", body)
                        self.settings.append((stype, tuple(vals)))
                        if stype == S_ENABLED:
                            enabled, next_iq = bool(vals[0]), time.monotonic()
                        elif stype == S_IQ_FREQ and self.honour_tune:
                            sync_due = (time.monotonic() + self.tune_delay, vals[0])
            now = time.monotonic()
            if sync_due and now >= sync_due[0]:
                conn.sendall(sync(sync_due[1]))
                sync_due = None
            if enabled and self.stream and now >= next_iq:
                conn.sendall(message(MSG_IQ_U8, IQ_BODY, seq=seq, stream=1))
                seq += 1
                next_iq = now + 0.05

    def finish(self):
        """Wait for the client to disconnect (spy_record does when it exits), then stop the thread."""
        self._thread.join(5)
        self._stop.set()
        self._thread.join(5)


@pytest.fixture
def fake_server():
    started = []

    def start(**kw):
        started.append(FakeSpyServer(**kw))
        return started[-1]

    yield start
    for srv in started:
        srv.finish()


def record(tmp_path, srv, seconds, *words):
    """Run spy_record against the fake; return (finished process, wall seconds, sidecar, iq bytes)."""
    prefix = str(tmp_path / "rec")
    t0 = time.monotonic()
    p = subprocess.run([sys.executable, str(SPY_RECORD), "127.0.0.1", str(srv.port), str(FREQ), "12000", str(seconds),
                        prefix, *words], capture_output=True, text=True, timeout=20)
    wall = time.monotonic() - t0
    srv.finish()
    assert Path(prefix + ".json").exists(), f"no sidecar (exit {p.returncode})\n{p.stdout}\n{p.stderr}"
    return p, wall, json.loads(Path(prefix + ".json").read_text()), Path(prefix + ".iq").read_bytes()


def test_honoured_tune_is_confirmed_and_recorded(tmp_path, fake_server):
    p, wall, meta, iq = record(tmp_path, fake_server(honour_tune=True), 3)
    assert p.returncode == 0, p.stdout + p.stderr
    assert "done:" in p.stdout and "WARNING" not in p.stdout and "aborted" not in p.stdout
    assert meta["tuned_confirmed"] is True
    # seconds since connect, and the SYNC comes before the first IQ message
    assert 0 <= meta["tune_confirmed_after_s"] <= meta["first_iq_after_s"] < 3
    assert any(abs(row[5] - FREQ) <= 1 for row in meta["syncs"])        # row: wall time, nsamp, can_control, gain, dev_cf, iq_cf, ...
    assert "aborted" not in meta and meta["partial"] is False and meta["drops"] == 0
    assert meta["kind"] == "u8" and meta["nsamp"] > 0
    assert len(iq) == 2 * meta["nsamp"] and iq == IQ_BODY * (len(iq) // len(IQ_BODY))
    assert wall >= 3


def test_ignored_tune_aborts_with_exit_2(tmp_path, fake_server):
    srv = fake_server(honour_tune=False)
    p, wall, meta, iq = record(tmp_path, srv, 60, "require_tune=1", "tune_timeout=2")
    assert p.returncode == 2, p.stdout + p.stderr
    assert "aborted: not tuned" in p.stdout
    assert meta["aborted"] == "not tuned" and meta["partial"] is False
    assert meta["tuned_confirmed"] is False and meta["tune_confirmed_after_s"] is None
    assert meta["first_iq_after_s"] is not None                         # IQ flowed all along; only the tune was missing
    assert 2 <= wall < 8                                                # stopped at tune_timeout, not after the 60 s asked for
    assert srv.settings[-1] == (S_ENABLED, (0,))                        # streaming was switched off before closing


def test_tuned_but_silent_server_aborts_with_exit_3(tmp_path, fake_server):
    srv = fake_server(honour_tune=True, stream=False)
    p, wall, meta, iq = record(tmp_path, srv, 60, "require_tune=1", "iq_timeout=2")
    assert p.returncode == 3, p.stdout + p.stderr
    assert "aborted: no IQ data" in p.stdout
    assert meta["aborted"] == "no IQ data" and meta["partial"] is False
    assert meta["tuned_confirmed"] is True and meta["first_iq_after_s"] is None
    assert meta["nsamp"] == 0 and iq == b""
    assert 2 <= wall < 8                                                # not after read_msg's own 15 s socket timeout
    assert srv.settings[-1] == (S_ENABLED, (0,))


def test_without_require_tune_an_ignored_tune_only_warns_once(tmp_path, fake_server):
    p, wall, meta, iq = record(tmp_path, fake_server(honour_tune=False), 2.5, "tune_timeout=1")
    assert p.returncode == 0, p.stdout + p.stderr
    assert len([ln for ln in p.stdout.splitlines() if "not confirmed" in ln]) == 1
    assert meta["tuned_confirmed"] is False and "aborted" not in meta
    assert meta["nsamp"] > 0 and wall >= 2.5                            # it kept recording to the end


def test_late_confirmation_inside_the_timeout_is_accepted(tmp_path, fake_server):
    p, wall, meta, iq = record(tmp_path, fake_server(honour_tune=True, tune_delay=0.8), 2.5, "require_tune=1", "tune_timeout=10")
    assert p.returncode == 0, p.stdout + p.stderr
    assert meta["tuned_confirmed"] is True and "aborted" not in meta
    assert 0.8 <= meta["tune_confirmed_after_s"] < 2.5
    assert meta["first_iq_after_s"] < meta["tune_confirmed_after_s"]    # IQ before the SYNC is kept (the old frequency)
    assert meta["nsamp"] > 0


def test_recording_that_ends_unconfirmed_is_not_a_success(tmp_path, fake_server):
    p, wall, meta, iq = record(tmp_path, fake_server(honour_tune=False), 1, "require_tune=1")
    assert p.returncode == 2, p.stdout + p.stderr
    assert meta["aborted"] == "not tuned" and meta["tuned_confirmed"] is False


def test_option_words_may_stand_between_positional_arguments(tmp_path, fake_server):
    srv = fake_server(honour_tune=True)
    p, wall, meta, iq = record(tmp_path, srv, 1, "require_tune=1", "13", "tune_timeout=30", "40", "iq_timeout=10")
    assert p.returncode == 0, p.stdout + p.stderr
    assert (S_GAIN, (13,)) in srv.settings and (S_IQ_DGAIN, (40,)) in srv.settings
    assert meta["tuned_confirmed"] is True


@pytest.mark.parametrize("word", ["require_tune=yes", "require_tun=1", "require_tune", "tune_timeout=0", "iq_timeout=abc"])
def test_bad_option_is_refused_before_connecting(tmp_path, word):
    p = subprocess.run([sys.executable, str(SPY_RECORD), "127.0.0.1", "1", str(FREQ), "12000", "1", str(tmp_path / "rec"), word],
                       capture_output=True, text=True, timeout=20)
    assert p.returncode == 1 and "bad option" in p.stderr and word in p.stderr
    assert list(tmp_path.iterdir()) == []                               # no connection attempt, nothing written
