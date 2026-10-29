# universe-badge

MicroPython app for a conference badge, continuously deployed: push to `main` and the
badge installs the new build the next time it is on WiFi.

## How it works

```
push to main ──► Actions: ruff, mpy-cross, pytest ──► GitHub Pages
                                                       manifest.json + app/**
badge on WiFi ──► GET manifest.json ──► new version? download, verify sha256, swap, reboot
```

The badge sits behind conference NAT, so nothing can push to it. It pulls instead: at boot,
then every 5 minutes, it fetches `https://62274677.github.io/universe-badge/manifest.json`.
Pages has no API rate limit, which matters when thousands of attendees share one public IP.

| Path | Updated by | Role |
|---|---|---|
| `badge/main.py`, `badge/ota.py` | USB only | Bootloader: WiFi, update check, runs the app. Never sent over the air, so a bad push can't break the updater. |
| `badge/app/**` | every push to `main` | The app. If it crashes, the bootloader shows the error and keeps polling, so pushing a fix recovers the badge. |
| `badge/wifi_config.py` | USB only, gitignored | WiFi networks, tried in order. |

An update downloads and checksums every changed file before it replaces any, so a dropped
connection partway through leaves the old build running. The manifest may only name paths
under `app/`.

## First-time setup (USB, once)

1. Flash MicroPython firmware for your board if it isn't already on it.
2. `cp badge/wifi_config.example.py badge/wifi_config.py` and add the conference network
   and a phone hotspot.
3. `pip install mpremote` and `python tools/flash.py` (add `--port COM5` if it picks the wrong
   port). This replaces the badge's stock `main.py`, such as the Badger OS launcher. Back it up
   first with `mpremote cp :main.py stock-main.py` if you want it back later.

## Day to day

Edit `badge/app/main.py`, push to `main`, and watch the Actions run. The badge picks the build up
within 5 minutes; press reset to check straight away. The build number in the footer is
`<run number>-<commit>`. Badges only install a build whose version differs from their own, so
reverting a commit rolls them back too.

Run the checks locally: `pip install ruff pytest mpy-cross && ruff check . && pytest`.

## Caveat

MicroPython does not verify TLS certificates, so a hostile WiFi network could serve a matching
manifest and code. Fine for a badge; keep secrets other than WiFi passwords off it.
