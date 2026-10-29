# Screensaver

A battery-friendly starfield with drifting nebulae, aurora, dark globules and gravitationally lensed black holes.

## Starting it

- Open **Screensaver** from the menu.
- Hold **UP + DOWN + BACK** together in the menu.
- Leave the menu untouched for 60 seconds.

Any button returns to the menu.

## Updates

Only `live/badge_app.py` is the screensaver; it's published on every push to `main` and
installed over the air. The loader in `__init__.py` checks once per launch, five seconds in,
skips the check below 25% battery (unless on USB), and switches WiFi off again when it's done.

## What you see

- Twinkling stars in three parallax layers, tinted from hot blue to cool red.
- Soft, blurred nebula layers and multicoloured clouds far away, with sharp, unblurred wisps drifting faster in front of them for depth. Hues drift slowly, and everything breathes brighter and dimmer together.
- Sporadic aurora patches that glow up, flicker and fade away, each with crisp rays and a bright lower fringe.
- Dark globules drifting in front of the nebula and hiding the stars behind them.
- Black holes that appear, wander and fade away. Each pixel around one shows the sky bent by a point-mass gravitational lens, so the background wraps into an Einstein ring around a black shadow. Some have a thin accretion disk: hotter and whiter on the inside, brighter on the side moving towards you (relativistic beaming), with the far side of the disk lensed up over the shadow.

The case lights breathe in time with the nebula, each a little behind the last so the glow travels around the badge.

## Power

- Backlight is capped at 40% (or your own setting if lower), breathing slightly with the nebula.
- It runs at up to 30 fps for the first minute, then 12 fps.
- After 5 minutes the backlight drops to 12%, the case lights almost off and the frame rate halves.
- After 30 minutes the badge goes into deep sleep. Press any front button to wake it.
- On battery below 15% it starts dimmed; below 5% it goes straight to sleep.

The sky is rendered at 160x120 one layer per frame and cached, so most frames only draw the stars and black holes. Nothing uses the motion sensor.
