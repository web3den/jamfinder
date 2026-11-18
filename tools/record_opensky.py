#!/usr/bin/env python3
"""Poll the OpenSky Network (anonymous) around a point and save replies in the same shape as record_adsb.py.

OpenSky gives state vectors (icao24, callsign, position, baro/geo altitude in m, velocity in m/s, true track,
vertical rate in m/s, time_position, last_contact, position_source). They are rewritten as readsb-style "ac"
entries so jf.tracks can read the file unchanged. Anonymous access: about 10 s resolution and 400 credits a day,
so keep the interval at 15 s or more and the box small.

usage: record_opensky.py out.jsonl.gz lamin lomin lamax lomax seconds interval_s
"""
import gzip
import json
import sys
import time
import urllib.request

UA = "jamfinder research recorder (non-commercial test)"
FT, KT = 1 / 0.3048, 1 / 0.514444


def convert(d):
    now = float(d.get("time") or time.time())
    out = []
    for s in d.get("states") or []:
        if s[5] is None or s[6] is None:
            continue
        a = dict(hex=s[0], flight=(s[1] or "").strip(), lat=s[6], lon=s[5],
                 seen_pos=max(0.0, now - (s[3] or now)), seen=max(0.0, now - (s[4] or now)),
                 type="adsb_icao" if (s[16] if len(s) > 16 else 0) == 0 else "other")
        if s[8]:
            a["alt_baro"] = "ground"
        elif s[7] is not None:
            a["alt_baro"] = round(s[7] * FT)
        if s[13] is not None:
            a["alt_geom"] = round(s[13] * FT)
        if s[9] is not None:
            a["gs"] = round(s[9] * KT, 1)
        if s[10] is not None:
            a["track"] = s[10]
        if s[11] is not None:
            a["baro_rate"] = round(s[11] * FT * 60)
        if s[14] is not None:
            a["squawk"] = s[14]
        out.append(a)
    return now, out


def main(out, box, seconds, interval):
    lamin, lomin, lamax, lomax = box
    url = f"https://opensky-network.org/api/states/all?lamin={lamin}&lomin={lomin}&lamax={lamax}&lomax={lomax}"
    t_end = time.time() + seconds
    ok = err = 0
    with gzip.open(out, "at") as f:
        while time.time() < t_end:
            t0 = time.time()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=15) as r:
                    d = json.loads(r.read())
                t1 = time.time()
                now, ac = convert(d)
                f.write(json.dumps({"t0": round(t0, 3), "t1": round(t1, 3), "now": now, "ac": ac}, separators=(",", ":")) + "\n")
                ok += 1
                if ok % 10 == 0:
                    f.flush()
            except Exception as e:
                err += 1
                print(f"warn: {e}", file=sys.stderr, flush=True)
                time.sleep(5.0)
            time.sleep(max(1.0, interval - (time.time() - t0)))
    print(f"done ok={ok} err={err}", flush=True)


if __name__ == "__main__":
    a = sys.argv
    main(a[1], [float(v) for v in a[2:6]], float(a[6]), float(a[7]))
