"""The badge app. Everything under app/ ships over the air on each push to main.

Edit freely: if this crashes, the bootloader shows the error and keeps
polling, so the next push fixes it.
"""
import json
import time

NAME = "Max"
TAGLINE = "@62274677"


def _version():
    try:
        with open("/ota_state.json") as f:
            return json.load(f)["version"]
    except (OSError, ValueError, KeyError):
        return "usb"


class Screen:
    """Draws on a Pimoroni Badger 2040 W if present, else prints."""

    def __init__(self):
        try:
            import badger2040
        except ImportError:
            self._d = None
            return
        self._d = badger2040.Badger2040()
        self._width = badger2040.WIDTH

    def show(self, title, subtitle, footer):
        d = self._d
        if d is None:
            print(title, subtitle, footer, sep="\n")
            return
        w = self._width - 20
        d.set_pen(15)
        d.clear()
        d.set_pen(0)
        d.set_font("bitmap8")
        d.text(title, 10, 15, w, 5)
        d.text(subtitle, 10, 65, w, 3)
        d.text(footer, 10, 110, w, 1)
        d.update()


def run(check_for_update):
    Screen().show(NAME, TAGLINE, "build " + _version())
    while True:
        time.sleep(30)
        check_for_update()
