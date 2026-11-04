# Status

**Start here after a break.** What is live, what is still open, and how to pick the work back up.
[README.md](README.md) explains how the system works; [DEVLOG.md](DEVLOG.md) is the history
and the reasoning behind each decision.

Last updated 2026-11-03.

## Live

- Both apps are published at build `7-4140b6b`
  ([name badge manifest](https://62274677.github.io/universe-badge/manifest.json),
  [screensaver manifest](https://62274677.github.io/universe-badge/screensaver/manifest.json)).
- Max's badge has both apps installed. octobooth-13 ran `tools/install.py` on 2026-10-29,
  which also hooked the badge's `main.py` and menu (the originals are in `.badge-app-backups/`
  on the BADGER drive). The badge still boots and runs both apps.
- `62274677` is the only collaborator. octobooth-13 had write access from 18:16 to about 18:45
  UTC on 2026-10-29: long enough to merge PR #1 (the screensaver) and push DEVLOG.md.

## Open: on the badge

These need the physical badge. None of them can be checked in the simulator.

1. **The Settings app fails with `'module' object has no attribute 'locked'`.** On this
   firmware `secrets.py` is a Python module: as well as the settings, it defines `locked(name)`
   and `save(values)`, and Settings calls both (`badger/home`
   `badge/apps/settings/__init__.py`, `is_locked()` and `save_value()`). On 2026-10-29
   `secrets.py` on the badge was edited to add `WIFI_NETWORKS`, and the error says the file
   the badge now loads has no `locked()`. That is an inference: nobody has looked at the file
   since. To fix it:
   1. Double-tap RESET and open `secrets.py` at the top of the BADGER drive. Don't print it or
      paste it anywhere: it holds the WiFi password.
   2. If it has no `def locked`, copy the backup from `.badge-app-backups/` back over it, then
      add just the `WIFI_NETWORKS = [...]` lines below `WIFI_PASSWORD`.
   3. Eject the drive and open Settings. Editing WiFi in Settings may then rewrite the file
      through `save()` and drop `WIFI_NETWORKS`, so check it's still there afterwards.
2. **Check build 7 on the badge.**
   - The screensaver should run at up to 30 fps for its first minute (`SMOOTH_FPS`,
     `SMOOTH_FOR_MS`), then 12 fps.
   - Black holes should have black centres. Before build 7 some showed up as plain yellow
     ellipses (DEVLOG section 11). If the centres are black but the background still doesn't
     bend around them, lensing is off or still missing the shown frame. Check on the REPL:
     `print(type(screen.raw), screen.stride, screen.width, screen.height)` while the
     screensaver is in HIRES mode.
3. **Not yet confirmed on hardware:**
   - **WiFi for every app.** `badge/wifi_networks.py` replaces `wifi.connect()` and passes
     the network name and password to the firmware's own `connect()` on every frame. The
     firmware source isn't public. If a call with credentials restarts the connection each
     time, no app gets online, and over-the-air updates stop for both apps. Test: push a change
     to `live/`, open Universe Badge, and watch the footer's build number.
   - **Sleep.** The screensaver calls `badge.sleep()` after 30 minutes, but no stock app uses
     that function. If it doesn't exist, the screensaver returns to the menu instead, the menu
     reopens it 60 s later, and the badge never sleeps.

## Open: repo housekeeping

- **claude-repo** (branch `feature/network-audit` in the main checkout): `prototypes/universe-badge`
  is registered as a submodule but only staged, and the staged pointer is the old `836b3fb`.
  When that branch's other work is ready, run `git add prototypes/universe-badge` and commit it
  with the `CLAUDE.md` submodule-table row (also uncommitted).
- The `add-screensaver` branch is merged and can be deleted.

## Resume

```
npm ci --prefix tools/preview                       # once per machine
node tools/preview/preview.mjs                      # name badge in the simulator -> preview.png
node tools/preview/preview.mjs --app screensaver --ms 8000 --out saver.png
pip install ruff pytest mpy-cross && ruff check . && pytest
```

- **Platform reference:** in [badger/home](https://github.com/badger/home),
  `.github/skills/hyb26-skill/references/` covers the app contract, the Badgeware API, USB serial
  and USB Disk Mode. `badge/AGENTS.md` and `badge/apps/` hold real examples, such as `iss` for
  WiFi and `badge` for `fetch`. The simulator's revision is pinned by `HOME_REV` in
  `tools/preview/preview.mjs`.
- **REPL on the badge:** `mpremote devs` (look for `2e8a:1101`), then
  `mpremote connect <port> repl`. `/system` is read-only over serial; copy apps over USB Disk
  Mode (double-tap RESET).
- **Deploying** = push to `main`. A push that doesn't touch `live/` only records the new
  version, with no reload.
