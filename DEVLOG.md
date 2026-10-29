# Badge screensaver + OTA deployment — development log

A record of what we built, why we made the choices we did, and the problems we
ran into along the way. Written for the GitHub Universe 2026 badge (MonaOS 4.0
on a Pimoroni Tufty 2350 derivative).

Artifacts:
- App on the badge: `D:\apps\screensaver\`
- In the repo: `62274677/universe-badge`, PR #1 (merged), build `5-158910c`
- Published: `https://62274677.github.io/universe-badge/screensaver/manifest.json`

---

## 1. Goal

Build a battery-friendly, always-on screensaver for the badge: a starfield with
drifting nebulae, multicoloured clouds, aurora, dark globules and black holes
(with and without accretion disks). Then wire it into the user's existing
continuous-deployment setup so it can be improved remotely, and let the badge
remember several WiFi networks.

---

## 2. Understanding the hardware and platform

Before writing anything we worked out what the badge actually is and what the
API offers, because none of it is documented on the drive itself.

**What we found:**
- **Runtime:** MicroPython 1.29 on an RP2350B (dual Cortex-M33, 520 KB SRAM,
  16 MB flash, 8 MB PSRAM). Firmware is Pimoroni's `tufty2350` build with a
  GitHub "MonaOS 4.0" layer on top.
- **Display:** 320x240 colour IPS LCD (`HIRES`), or 160x120 (`LORES`). Not
  e-ink — the backlight dominates power use.
- **Graphics:** `picovector` (vector shapes, gradients, **fractal/fBm noise
  brushes**, image filters like blur/bloom), drawing into an `st7789` frame
  buffer. Globals like `badge`, `screen`, `color`, `shape`, `brush`, `run()`
  are injected into builtins; apps don't import them.
- **Power API:** `badge.battery_level()`, `badge.is_charging()`,
  `badge.usb_connected()`, `badge.caselights()` (4 single-colour PWM LEDs),
  `badge.sleep()` → `powman` deep sleep, `get_backlight()`/`set_backlight()`.
- **App model:** a folder under `apps/` with `__init__.py` that defines
  `update()` and calls `run(update)`. Returning non-`None` from `update()`
  exits. `on_exit()` cleans up. The menu auto-discovers apps.

**Sources we used** (all public):
- `pimoroni/tufty2350` — real firmware source for `badge.py`, `wifi.py`,
  `secrets.py`, `powman`.
- `pimoroni/badgeware-docs` — the `image`, `brush`, `color`, `shape`, `mat3`
  API docs. The fractal brush and the lensing idea came straight from here.
- `badger/home` `.github/skills/hyb26-skill/` — the U26 app contract, hardware
  notes, menu-icon rules, and `install.py`/`validate_app.py` tooling.
- `badger/badger.github.io` — the web simulator at `badger.github.io/simulator`
  and its MicroPython-in-WASM runtime, plus the `sparkle`/`wifi` sim stubs.

**Confirmed specs we couldn't read off the device:** 320x240 IPS LCD, 1000 mAh
LiPo, RP2350B — from `badgeware-docs/introduction/meet-your-badge.md` (the
Pimoroni shop page was rate-limiting us).

---

## 3. Design decisions

### Rendering strategy (the big one)
A full-screen 320x240 generative effect every frame is far too slow in
MicroPython. The approach that made it feasible:

- **Render the soft sky once at 160x120**, one layer per frame, into a small
  image, then cache it upscaled to 320x240. Most frames then only draw the
  cheap moving things (stars, black holes) over the cached background.
- **Let C do the heavy lifting.** The nebula is `brush.fractal()` (fBm noise
  generated in C as it's drawn) with a colour `ramp()`. No per-pixel Python.
- The sky regenerates about once a second (the `sky_layers()` generator yields
  after each layer, spreading the cost across frames so input stays responsive).

### Black-hole lensing
Rather than fake a dark circle, we wrote a real point-mass gravitational lens as
a `@micropython.viper` function operating on the raw framebuffer: each pixel at
offset *t* from the hole samples the background at `t·(1 − E²/|t|²)`, bending it
into an Einstein ring around a black shadow. Viper compiles to native code, so
this is fast enough per frame. Falls back to a plain dark circle if `screen.raw`
isn't available.

### Accretion disks
Drawn as `shape.custom()` segments in a tilted, foreshortened ellipse. Physics
touches we added: **relativistic Doppler beaming** (the side rotating toward the
viewer is brighter and bluer), a hot white inner edge cooling to red outward,
and the far side of the disk lensed up over the shadow (drawn after the lens).

### Power plan (user's spec)
- Backlight capped at 40% (or the user's setting if lower), breathing with the
  nebula. Never raises the user's own level.
- After 5 min: backlight → 12%, case lights almost off, frame rate halves.
- After 30 min: `badge.sleep()` deep sleep; any front button wakes it.
- Battery < 15%: start dimmed. < 5%: sleep immediately.

### Case lights
The 4 LEDs are single-colour, so they can't show "generative colours." Instead
each breathes with the nebula brightness, phase-shifted, so the glow travels
around the badge.

### Triggers (user's spec)
- Selectable app in the menu.
- Auto-start after 60 s idle in the menu.
- Hotkey UP+DOWN+BACK held in the menu.
Implemented by patching the menu's `update()` (idle timer + chord check) rather
than `main.py`, to keep the boot path untouched.

---

## 4. The simulator test loop

We used `badger.github.io/simulator` (MicroPython → WASM with the real badge
APIs) through the browser tools to see the output before touching the badge.

**This was the fiddliest part of the whole task.** Problems and fixes:

| Problem | Cause | Fix |
|---|---|---|
| Playwright MCP couldn't launch | Chrome not installed for it | Used the built-in `openBrowserPage`/`runPlaywrightCode` tools instead |
| `screenshotPage` on the canvas timed out / came back blurry | The page overlays its own 3D badge model and CSS backdrop effects over the `#badge-screen` canvas; DOM screenshots pick those up | Exported the canvas directly with `canvas.toDataURL('image/jpeg')`, decoded + 3x-upscaled it locally with System.Drawing, then viewed the PNG |
| "Replace this edited project?" dialog blocked the Run button | The sim keeps a draft; loading a file re-prompts | Click **Replace project** after the file chooser, before Run |
| A quick Select tap didn't exit the app | In the sim the Viper lens runs as slow Python, so a frame can be longer than a button tap, and `badge.pressed()` is edge-only | Held the button ~1.2 s to test; **and** hardened the real input loop (below) |

To inspect specific behaviour we made throwaway "debug" copies of the app with
constants tweaked (e.g. force a big disk black hole, speed up the 5-min/30-min
timers to seconds, print backlight/case-light/aurora state each second) and read
the values back from the sim console. The timing logic printed exactly the
expected ramp (dim at 5 min over 20 s, deep sleep at 30 min).

---

## 5. Iterations on the visuals

Driven by looking at decoded frames and the user's feedback.

**Round 1 (first working version):** nebula too washed out and uniformly
blurred; the whole thing felt flat. → Raised fractal persistence and ramp
opacity for denser, more contrasty nebula; reduced the blur.

**Round 2 (accretion disk realism):** the Doppler-beamed disk was so bright on
the approaching side that the receding side vanished. → Normalised each disk's
brightness and compressed it with a square root so the dim side stays visible;
softened the photon ring.

**Round 3 (user feedback):** three requests —
1. *Disks much brighter.* → Brighter, more opaque colour ramp with a gamma
   curve, higher brightness floor (0.5), stronger glow gradient, bolder ring.
2. *No band aurora — want sporadic patches fading in/out.* → Replaced the
   full-width curtain with an `AuroraPatch` class: up to 3 patches, random
   position/size, each lives 14–32 s with a `sin²` fade envelope and a flicker,
   drifting sideways, tapering to nothing at its ends. Soft body drawn before
   the blur; crisp rays + bright lower fringe after it.
3. *Some nebula unblurred, to imply depth.* → Added two **sharp** `brush.fractal`
   wisp layers composited at full 320x240 resolution over the blurred
   background, drifting faster than it (nearer layer fastest) for parallax.

**A subtlety we had to fix:** the sharp near layers drift, but the background
only regenerates ~once a second, so fast drift made them visibly jump at each
refresh. → Slowed every layer's drift and tightened the dim-mode regen interval.

Final look verified in the simulator: dense multicolour nebula, sharp wisps in
front, teal aurora patches, and a bright Doppler-beamed lensed disk.

---

## 6. Integrating with the user's CD setup

The user already had `62274677/universe-badge`: one app (`universe_badge`)
continuously deployed via **GitHub Pages pull-based OTA** (not GitHub Releases —
deliberately, because thousands of attendees share one conference IP and Pages
has no API rate limit and needs no token). Architecture:

```
push to main → Actions (ruff, mpy-cross, pytest, sim smoke test) → GitHub Pages
                                              manifest.json + live/**
app open → wifi.connect() → fetch manifest.json → new version?
           download changed files, verify sha256, swap in, re-import
```

Apps are split: a **loader** + `ota.py` installed once over USB (never updated
OTA, so a bad push can't brick the updater), and **`live/badge_app.py`** that
ships OTA.

**What we added to make the screensaver a second OTA app:**
- `badge/apps/screensaver/live/badge_app.py` — the screensaver, with its
  `run(update)` removed (the loader drives it) and `on_exit` preserved.
- `badge/apps/screensaver/__init__.py` — a loader like `universe_badge`'s but
  battery-aware: **one** update check per launch (5 s in), skipped below 25%
  charge unless on USB, and WiFi switched **off** when the check finishes.
- `badge/apps/screensaver/ota.py` — an identical copy of the existing updater.
- `build_manifest.py` now publishes every app with a `live/` folder;
  `universe_badge` stays at the site root (so already-installed loaders keep
  working), others go to `/<app>/`.
- `preview.mjs` gained `--app`; CI previews both apps and uploads both shots.
- `install.py` rewritten to install all apps + the WiFi helper and apply the
  menu/`main.py` hooks idempotently, with backups.

### Issue: Viper code passing CI but not really being checked
CI compiles every badge file with `mpy-cross` to catch MicroPython-only syntax.
The first run compiled with the default target, which **rejected the Viper
`ptr32` code with "invalid arch."** → Added `-march=armv7emsp` (the RP2350's
native target) so Viper is genuinely compiled, and told ruff about
`ptr8/16/32` as builtins.

### Tests added
`tests/test_screensaver_and_wifi.py`:
- Every `ota.py` copy is byte-identical (a fix must land in all at once).
- Loader URLs match where the site publishes each app.
- The multi-app site puts `universe_badge` at root, others in folders.
- WiFi network parsing, ranking, and failover (below).

All checks: **ruff clean, mpy-cross clean, 22 pytest passed, both sims render.**

---

## 7. Saved WiFi networks

The firmware `wifi.connect()` only knows `WIFI_SSID` / `WIFI_PASSWORD`. We added
`badge/wifi_networks.py`, installed to `/system/wifi_networks.py` and hooked into
`main.py` so it applies before any app runs.

- `secrets.py` can list `WIFI_NETWORKS = [(ssid, password), ...]`, most
  preferred first.
- `install()` wraps `wifi.connect()`: a call with no SSID picks a saved network
  instead. Order (per the user's choice, "first in list, then strongest"):
  **first listed network in range with a usable signal**, then weaker in-range
  ones strongest-first, then networks the scan didn't see (hidden), last.
- If a network doesn't come up within 15 s, it moves to the next.
- `WIFI_SSID` (what the Settings app edits) is appended last.

**Edge case we fixed:** after a successful connect, if a caller disconnects and
reconnects, the switch-timer must restart or it would immediately skip to the
next network. Reset `_started` to `None` on success so each new attempt gets a
fresh timer.

On the badge, `secrets.py` now has `WIFI_NETWORKS` seeded with the current
network plus commented examples. We backed `secrets.py` up first and never
printed its contents.

---

## 8. Deploying to the badge and the repo

**On the badge (`D:\`):**
- Backed up the menu and `secrets.py` to `D:\.badge-app-backups\` before editing.
- Ran the repo's `install.py --mount D:\`: installed `screensaver` (loader form),
  `universe_badge`, and `wifi_networks.py`; hooked `main.py`; the menu hook was
  already present from earlier. Verified the `install.py` menu patch **exactly
  reproduces** the menu already on the badge, and syntax-checked every file.

**To the repo:**
- This machine is logged in as the booth account `octobooth-13`, which initially
  had only read access to `62274677/universe-badge`. The user granted push
  access mid-task.
- Set a repo-local git identity for `octobooth-13` (not global), committed on
  branch `add-screensaver`, pushed, opened **PR #1**, CI passed (check + simulate;
  deploy correctly skipped on the PR), user approved, **merged**.
- The deploy run on `main` succeeded. Both manifests are live at build
  `5-158910c`. Verified the **published screensaver bytes match the merged git
  blob** (an initial mismatch was just CRLF in the Windows checkout).

---

## 9. Open items / caveats

- **Not yet run on the real badge.** Everything is verified in the simulator and
  by static checks only. The sim doesn't model real speed, memory, battery, or
  WiFi — so on-device frame rate, the 12% dim look, deep sleep/wake, and the
  first OTA pull are still unconfirmed. First real test: eject the drive, open
  the screensaver (or idle 60 s), watch for the ~5 s update and the one sky
  restart as build 5 swaps in.
- **`main.py` hook** is syntax-checked only; confirm the badge still boots to the
  menu after ejecting. Original is backed up.
- **Settings app + `WIFI_NETWORKS`:** the firmware source for how Settings writes
  `secrets.py` isn't public; if you edit WiFi in Settings, check `WIFI_NETWORKS`
  survived.
- **No custom menu icon** (`icon.png`): this badge's menu only uses built-in
  icons, so the tile shows the default. Not fixable without patching the menu's
  icon loader.
- **OTA trust:** download is checksummed, but manifest and files share one HTTPS
  origin and the badge's TLS may not verify certs — a hostile network could
  serve its own code. Fine for a badge; keep nothing secret on it beyond the
  WiFi password.
- **Collaborator access:** commits are authored as `octobooth-13`. Revoke its
  access after you're done pushing from this machine if you like.

---

## 10. Tuning knobs (for later)

Top of `live/badge_app.py`:
- `STAR_COUNT`, `MAX_HOLES`, `BRIGHT_FPS` / `DIM_FPS` — the main perf levers.
- `BACKLIGHT_BRIGHT` / `BACKLIGHT_DIM`, `CASE_BRIGHT` / `CASE_DIM` — power vs.
  brightness.
- `DIM_AFTER_MS`, `SLEEP_AFTER_MS`, `LOW_BATTERY`, `CRITICAL_BATTERY` — timing.
- `DISK_RINGS` / `DISK_SEGMENTS` — disk detail vs. cost.

To iterate remotely now: edit `badge/apps/screensaver/live/badge_app.py`,
`node tools/preview/preview.mjs --app screensaver` to preview, push to `main`.
Badges pick it up next time the screensaver opens.
