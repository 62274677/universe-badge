# universe-badge

An app for the GitHub Universe 2026 badge, continuously deployed: push to `main` and every
badge running it installs the new code over WiFi, no cable and no restart.

## How it works

```
push to main ──► Actions: ruff, mpy-cross, pytest, simulator smoke test ──► GitHub Pages
                                                              manifest.json + live/**
badge app open ──► wifi.connect() ──► fetch manifest.json ──► new version?
                   download changed files, verify sha256, swap in, re-import live code
```

Nothing can push to a badge behind conference NAT, so it pulls: when the app opens, then every
5 minutes, it fetches `https://62274677.github.io/universe-badge/manifest.json`. Pages has no
API rate limit, which matters when thousands of attendees share one public IP, and needs no
token, so the repo stays public.

The badge firmware keeps `/system` (where apps live) read-only at runtime, so the app is split:

| Path | Updated by | Role |
|---|---|---|
| `badge/apps/universe_badge/__init__.py`, `ota.py` | USB Disk Mode, once | Loader: runs the live code, drives the updater a step per frame. Never updated over the air, so a bad push can't break the updater. |
| `badge/apps/universe_badge/live/**` | every push to `main` | Your app (`badge_app.py` defines `update()`). Installed to `/ota/universe_badge/` on the badge, which takes precedence over the copy bundled in `/system`. |

If the live code crashes, the loader shows the error and keeps checking, so pushing a fix
recovers the badge. An update downloads and checksums every changed file before replacing any;
a dropped connection leaves the old build running. A push that doesn't change `live/` records
the new version without reloading.

## See it before you push

```
npm ci --prefix tools/preview         # once
node tools/preview/preview.mjs        # runs the app headless, writes preview.png
node tools/preview/preview.mjs --press down,select --out after.png
node tools/preview/preview.mjs --live # browser window that reloads on save
node tools/preview/preview.mjs --ota  # exercise the real update path against Pages
```

This runs the [badger.github.io simulator](https://badger.github.io/simulator) (MicroPython
compiled to WebAssembly with the badge firmware's APIs) on your local code, using an installed
Chrome or Edge. CI runs the same thing on every push and PR: a traceback fails the run and
blocks the deploy, and the screenshot is attached to the run as the `preview` artifact.

The simulator doesn't model speed, memory, or real WiFi failures, so check new features on
the badge too. The web editor at badger.github.io runs a single `__init__.py`; this app needs
its loader and `ota.py` beside it, so use `preview.mjs` for it.

## First-time setup (USB Disk Mode, once per badge)

1. Connect USB-C and double-tap RESET. A `BADGER` drive appears.
2. Set `WIFI_SSID` and `WIFI_PASSWORD` in `secrets.py` on that drive.
3. `python tools/install.py`, then eject the drive. The badge restarts into the menu.
4. Open **Universe Badge**. The footer shows `build usb` until the first over-the-air build
   lands, then `build <run number>-<commit>`.

Repeat step 3 only when `__init__.py` or `ota.py` change.

## Day to day

Edit `badge/apps/universe_badge/live/badge_app.py`, preview it, push. Actions takes about a
minute. Open badges pick the build up within 5 minutes; reopen the app (HOME, then select it)
to check straight away. Badges install any build whose version differs from theirs, so
reverting a commit rolls them back too.

Checks locally: `pip install ruff pytest mpy-cross && ruff check . && pytest`.

## Caveat

The download is checksummed against the manifest, but both come from the same HTTPS origin and
the badge's TLS stack may not verify certificates, so a hostile network could serve its own
code. Fine for a badge; don't keep secrets on it beyond the WiFi password.
