# data/

This folder is empty on purpose. The scripts expect recordings here. None are included.

## The layout the scripts expect

| Path | Content |
|---|---|
| `data/iq/<run>/<prefix>.iq` | A recording: raw samples |
| `data/iq/<run>/<prefix>.json` | Its description: sample format, rate, frequency, time stamps |
| `data/iq/<run>/adsb_*.jsonl.gz` | Aircraft positions recorded over the same time |
| `data/iq/<run>r/` | The repaired copy that the analysis writes |

The file formats are described under "Level 3" in
[docs/try_it_yourself.md](../docs/try_it_yourself.md).

The description file that the network recorder writes holds the server's address and the
receiver's hardware serial number. Remove both before you share a recording.
