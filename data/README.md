# data/

Put your recordings here. The folder is empty in the repository.

| Path | Content |
|---|---|
| `data/iq/<run>/<name>.iq` | Raw IQ samples |
| `data/iq/<run>/<name>.json` | The description: sample format, rate, frequency, time stamps |
| `data/iq/<run>/adsb_*.jsonl.gz` | Aircraft positions over the same time |
| `data/iq/<run>r/` | A repaired copy that the analysis writes and deletes |

The formats are described in [docs/usage.md](../docs/usage.md#your-own-receiver).

The `.json` file from the network recorder holds the server's address and the receiver's serial
number. Remove both before you share a recording.
