#!/usr/bin/env python3
"""List VHF navaids and airport broadcast frequencies near a point.

usage: nearby.py <ourairports_dir> lat lon radius_km
"""
import csv, math, sys

def km(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    a = math.sin((p2 - p1) / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(a))

def bearing(lat1, lon1, lat2, lon2):
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dl = math.radians(lon2 - lon1)
    y = math.sin(dl) * math.cos(p2)
    x = math.cos(p1) * math.sin(p2) - math.sin(p1) * math.cos(p2) * math.cos(dl)
    return (math.degrees(math.atan2(y, x)) + 360) % 360

d, lat, lon, rad = sys.argv[1], float(sys.argv[2]), float(sys.argv[3]), float(sys.argv[4])
print("== navaids (VOR family) ==")
rows = []
for r in csv.DictReader(open(f"{d}/navaids.csv", encoding="utf-8")):
    if "VOR" not in r["type"]:
        continue
    try:
        la, lo = float(r["latitude_deg"]), float(r["longitude_deg"])
    except ValueError:
        continue
    dist = km(lat, lon, la, lo)
    if dist <= rad:
        rows.append((dist, r["ident"], r["name"], r["type"], r["frequency_khz"], la, lo, r["elevation_ft"], r["power"], bearing(lat, lon, la, lo)))
for x in sorted(rows):
    print(f"{x[0]:6.1f} km brg {x[9]:5.1f}  {x[1]:4s} {x[2][:22]:22s} {x[3]:8s} {int(x[4])/1000:8.3f} MHz  {x[5]:.6f} {x[6]:.6f} elev {x[7]} pwr {x[8]}")
print("== airports with frequencies ==")
ap = {}
for r in csv.DictReader(open(f"{d}/airports.csv", encoding="utf-8")):
    try:
        la, lo = float(r["latitude_deg"]), float(r["longitude_deg"])
    except ValueError:
        continue
    dist = km(lat, lon, la, lo)
    if dist <= rad and r["type"] in ("large_airport", "medium_airport", "small_airport"):
        ap[r["ident"]] = (dist, r["name"], la, lo, r["type"], bearing(lat, lon, la, lo))
for r in csv.DictReader(open(f"{d}/airport-frequencies.csv", encoding="utf-8")):
    if r["airport_ident"] in ap:
        a = ap[r["airport_ident"]]
        t = r["type"].upper()
        if any(k in t for k in ("ATIS", "AWOS", "ASOS", "VOLMET", "AFIS", "INFO")) or "ATIS" in r["description"].upper():
            print(f"{a[0]:6.1f} km brg {a[5]:5.1f}  {r['airport_ident']:5s} {a[1][:28]:28s} {r['type']:8s} {r['description'][:22]:22s} {r['frequency_mhz']} MHz  ({a[2]:.4f},{a[3]:.4f})")
