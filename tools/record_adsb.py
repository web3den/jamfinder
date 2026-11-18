#!/usr/bin/env python3
"""Poll a readsb-style ADS-B API around a point and save every reply.

Used next to an IQ recording, so timing matters: each line keeps our clock
before and after the request plus the server's own "now".

usage: record_adsb.py out.jsonl.gz url seconds interval_s
  url example: https://opendata.adsb.fi/api/v3/lat/45.29/lon/-75.73/dist/40
Line format: {"t0": unix, "t1": unix, "now": server_now, "ac": [...]}
Stdlib only. Keep the rate at or under 1 request per second.
"""
import gzip, json, sys, time, urllib.request

UA = "jamfinder research recorder (non-commercial test)"
KEEP = ("hex", "type", "flight", "t", "category", "alt_baro", "alt_geom", "gs", "tas",
        "ias", "mach", "track", "true_heading", "mag_heading", "baro_rate", "geom_rate",
        "lat", "lon", "nic", "rc", "seen_pos", "seen", "version", "nac_p", "nac_v",
        "sil", "rssi", "messages", "roll", "track_rate", "nav_qnh", "wd", "ws")


def main(out, url, seconds, interval):
    t_end = time.time() + seconds
    ok = err = 0
    with gzip.open(out, "at") as f:
        while time.time() < t_end:
            t0 = time.time()
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=10) as r:
                    d = json.loads(r.read())
                t1 = time.time()
                acs = d.get("ac") or d.get("aircraft") or []
                rec = {"t0": round(t0, 3), "t1": round(t1, 3), "now": d.get("now"),
                       "ac": [{k: a[k] for k in KEEP if k in a} for a in acs]}
                f.write(json.dumps(rec, separators=(",", ":")) + "\n")
                ok += 1
                if ok % 50 == 0:
                    f.flush()
            except Exception as e:
                err += 1
                print(f"warn: {e}", file=sys.stderr, flush=True)
                time.sleep(2.0)
            time.sleep(max(0.2, interval - (time.time() - t0)))
    print(f"done ok={ok} err={err}", flush=True)


if __name__ == "__main__":
    a = sys.argv
    main(a[1], a[2], float(a[3]), float(a[4]))
