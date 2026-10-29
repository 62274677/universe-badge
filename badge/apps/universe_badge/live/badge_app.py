"""Your badge app. Everything in live/ ships over the air on each push to main.

The loader imports this module and calls update() once per frame (screen is
160x120 unless you call badge.mode(HIRES)). Define on_exit() to clean up when
HOME is pressed. Preview it before pushing: node tools/preview/preview.mjs
"""
import math

import ota

NAME = "Max"
HANDLE = "@62274677"

BG = color.rgb(13, 17, 23)
FG = color.rgb(240, 246, 252)
DIM = color.rgb(125, 133, 144)
GREENS = [color.rgb(14, 68, 41), color.rgb(0, 109, 50),
          color.rgb(38, 166, 65), color.rgb(57, 211, 83)]

screen.antialias = image.X2


def _centred(text, y):
    width, _ = screen.measure_text(text)
    screen.text(text, (screen.width - width) / 2, y)


def _contribution_strip(t):
    """A row of contribution-graph squares rippling left to right."""
    size, gap = 8, 2
    count = (screen.width - 8) // (size + gap)
    x0 = (screen.width - count * (size + gap) + gap) / 2
    for i in range(count):
        level = int(2 + 2 * math.sin(t * 3 - i * 0.6))
        screen.pen = GREENS[max(0, min(3, level))]
        screen.shape(shape.rounded_rectangle(x0 + i * (size + gap), 72, size, size, 2))


def update():
    t = badge.ticks / 1000
    screen.pen = BG
    screen.clear()

    screen.font = font.ziplock
    screen.pen = FG
    _centred(NAME, 18)

    screen.font = font.nope
    screen.pen = GREENS[3]
    _centred(HANDLE, 50)

    _contribution_strip(t)

    screen.pen = DIM
    _centred("build " + str(ota.build), screen.height - 14)
