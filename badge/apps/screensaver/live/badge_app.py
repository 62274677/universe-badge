"""
Starfield screensaver: drifting nebulae, clouds, aurora patches, dark
globules and black holes, with and without accretion disks.

This is the live code: CI publishes it on every push to main and the loader
(../__init__.py) installs it over the air and calls update() each frame.

Any button returns to the menu. The menu opens this after 60 s without input,
or straight away with UP + DOWN + BACK held together.

Power: the backlight is capped and the frame rate limited. The soft sky is
rendered at half resolution a layer per frame and cached, so each frame only
draws the stars and black holes. After 5 minutes everything dims, and after 30
minutes the badge goes into deep sleep (any front button wakes it).
"""

import math
import random
import time
from array import array

import micropython

try:
    from badgeware import get_backlight, set_backlight
except ImportError:
    get_backlight = set_backlight = None

badge.mode(HIRES)
previous_clear = badge.default_clear
badge.default_clear = None
screen.antialias = image.X2

W, H = screen.width, screen.height
LW, LH = W // 2, H // 2

BRIGHT_FPS = 12
DIM_FPS = 6
BRIGHT_REGEN_MS = 1200
DIM_REGEN_MS = 2500
DIM_AFTER_MS = 5 * 60 * 1000
DIM_FADE_MS = 20 * 1000
SLEEP_AFTER_MS = 30 * 60 * 1000
INPUT_GRACE_MS = 600
BATTERY_CHECK_MS = 30 * 1000
LOW_BATTERY = 15
CRITICAL_BATTERY = 5

# backlight percentages, never above the user's own setting
BACKLIGHT_BRIGHT = 40
BACKLIGHT_DIM = 12
CASE_BRIGHT = 0.45
CASE_DIM = 0.06

STAR_COUNT = 160
LAYER_SPEED = (0.6, 1.3, 2.8)
MAX_HOLES = 2
HOLE_CHECK_MS = 18 * 1000
HOLE_FADE_MS = 10 * 1000
DISK_RINGS = 4
DISK_SEGMENTS = 20

CLEAR = color.rgb(0, 0, 0, 0)
TAU = math.pi * 2

random.seed(time.ticks_us())


def rand(low, high):
    return low + (high - low) * random.random()


def clamp(value, low, high):
    return low if value < low else high if value > high else value


def oklch(light, chroma, hue, alpha=255):
    return color.oklch(int(clamp(light, 0, 255)), int(clamp(chroma, 0, 255)), int(hue) % 256,
                       int(clamp(alpha, 0, 255)))


def nebula_level(seconds):
    """Slow, irregular breathing of the whole sky, 0..1."""
    wave = 0.3 * math.sin(TAU * seconds / 41) + 0.2 * math.sin(TAU * seconds / 17 + 1.3)
    return clamp(0.5 + wave, 0.0, 1.0)


class Backlight:
    def __init__(self):
        self.original = None
        self.fraction = False
        self.current = None
        if get_backlight is None:
            return
        try:
            self.original = get_backlight()
        except Exception:  # noqa: BLE001
            return
        self.fraction = isinstance(self.original, float) and self.original <= 1.0

    def ceiling(self):
        return self.original * 100 if self.fraction else self.original

    def write(self, value):
        try:
            set_backlight(value, save=False)
        except TypeError:
            set_backlight(value)

    def set(self, percent):
        if self.original is None:
            return
        level = int(clamp(percent, 1, self.ceiling()))
        if level != self.current:
            self.current = level
            self.write(level / 100 if self.fraction else level)

    def restore(self):
        if self.original is not None:
            self.write(self.original)


backlight = Backlight()


# -- the sky: rendered at 160x120, a layer per frame, then scaled into bg --

lo = image(LW, LH)
bg = image(W, H)
lo.antialias = image.X2


def fractal(scale, octaves, persistence):
    return brush.fractal(scale, octaves, persistence, 256 >> (octaves - 1), random.getrandbits(16))


nebula_a = fractal(60, 4, 0.62)
nebula_b = fractal(44, 4, 0.6)
clouds = [fractal(rand(18, 30), 4, 0.55) for _ in range(4)]
CLOUD_HUES = (30, 115, 160, 205)
lanes = fractal(30, 3, 0.5)
rays = fractal(5, 2, 0.5)
# fine, unblurred filaments drawn at full resolution and drifting faster, so
# they read as nearer than the soft nebula behind them
wisps = brush.fractal(48, 4, 0.75, 32, random.getrandbits(16))
wisps_far = brush.fractal(64, 4, 0.7, 32, random.getrandbits(16))

hue_base = random.getrandbits(8)
drift = [(rand(-1.2, 1.2), rand(-0.8, 0.8)) for _ in range(9)]


def wrapped(field, index, seconds, speed=0.4):
    period = field.repeat * field.scale
    vx, vy = drift[index]
    return mat3().translate((seconds * vx * speed) % period, (seconds * vy * speed) % period)


class DarkSpot:
    def __init__(self):
        self.x = rand(0, LW)
        self.y = rand(LH * 0.3, LH)
        self.r = rand(8, 18)
        self.vx = rand(-0.5, 0.5)
        self.vy = rand(-0.25, 0.25)
        self.lobes = [(rand(-0.6, 0.6), rand(-0.4, 0.4), rand(0.5, 0.9)) for _ in range(3)]

    def position(self, seconds):
        span_x = LW + self.r * 4
        span_y = LH + self.r * 4
        x = (self.x + self.vx * seconds + self.r * 2) % span_x - self.r * 2
        y = (self.y + self.vy * seconds + self.r * 2) % span_y - self.r * 2
        return x, y

    def draw(self, seconds, depth):
        x, y = self.position(seconds)
        for ox, oy, scale in [(0, 0, 1.0)] + self.lobes:
            cx = x + ox * self.r
            cy = y + oy * self.r
            r = self.r * scale
            lo.pen = brush.gradient(brush.RADIAL, cx, cy, cx + r, cy, [
                (0.0, color.rgb(0, 0, 0, depth)),
                (0.55, color.rgb(0, 0, 0, depth * 2 // 3)),
                (1.0, CLEAR),
            ])
            lo.shape(shape.circle(cx, cy, r))


spots = [DarkSpot() for _ in range(4)]


class AuroraPatch:
    """A short curtain of aurora that glows up, flickers and fades away."""

    def __init__(self, seconds):
        self.born = seconds
        self.life = rand(14, 32)
        self.width = rand(40, 80)
        self.height = rand(18, 34)
        self.x = rand(-6, LW - self.width + 6)
        self.y = rand(self.height + 6, LH - 4)
        self.vx = rand(-0.5, 0.5)
        self.tone = rand(92, 135)
        self.crown = rand(190, 230)
        self.phase = rand(0, TAU)

    def alive(self, seconds):
        return seconds - self.born < self.life

    def strength(self, seconds):
        age = seconds - self.born
        if age <= 0 or age >= self.life:
            return 0.0
        envelope = math.sin(math.pi * age / self.life) ** 2
        return envelope * (0.8 + 0.2 * math.sin(age * 1.9 + self.phase))

    def slices(self, seconds):
        """Vertical strips of the curtain, each with its own taper."""
        left = self.x + self.vx * (seconds - self.born)
        count = 10
        edge = []
        for k in range(count + 1):
            x = left + self.width * k / count
            edge.append((x, self.y + 3 * math.sin(x / 9 + seconds / 4 + self.phase)))
        strips = []
        for k in range(count):
            (x0, y0), (x1, y1) = edge[k], edge[k + 1]
            taper = math.sin(math.pi * (k + 0.5) / count)
            top = self.height * (0.35 + 0.65 * taper)
            curtain = shape.custom(array("f", (x0, y0, x1, y1, x1, y1 - top, x0, y0 - top)))
            fringe = shape.custom(array("f", (x0, y0, x1, y1, x1, y1 - 2.5, x0, y0 - 2.5)))
            strips.append((taper, curtain, fringe))
        return strips

    def gradient(self):
        return brush.gradient(brush.LINEAR, 0, self.y - self.height, 0, self.y, [
            (0.0, CLEAR),
            (0.4, oklch(110, 110, self.crown, 60)),
            (0.78, oklch(165, 150, self.tone + 12, 150)),
            (1.0, oklch(215, 160, self.tone, 210)),
        ])

    def draw_glow(self, seconds, level):
        """Soft body of the curtain, drawn before the blur."""
        strength = self.strength(seconds) * (0.65 + 0.35 * level)
        if strength < 0.03:
            return
        lo.pen = self.gradient()
        for taper, curtain, _fringe in self.slices(seconds):
            lo.alpha = int(255 * strength * taper * taper)
            lo.shape(curtain)

    def draw_detail(self, seconds, level):
        """Crisp rays and the bright lower fringe, drawn after the blur."""
        strength = self.strength(seconds) * (0.65 + 0.35 * level)
        if strength < 0.03:
            return
        rays.ramp([
            (0.0, CLEAR), (0.45, CLEAR),
            (0.7, oklch(200, 160, self.tone + 10, 130)),
            (1.0, oklch(245, 90, self.tone, 210)),
        ])
        glow = oklch(235, 120, self.tone, 190)
        for taper, curtain, fringe in self.slices(seconds):
            lo.alpha = int(200 * strength * taper * taper)
            lo.pen = rays
            lo.shape(curtain)
            lo.pen = glow
            lo.shape(fringe)


MAX_AURORAS = 3
auroras = []


def manage_auroras(seconds):
    auroras[:] = [patch for patch in auroras if patch.alive(seconds)]
    if len(auroras) < MAX_AURORAS and (not auroras or random.random() < 0.12):
        auroras.append(AuroraPatch(seconds))


def sky_layers(seconds):
    level = nebula_level(seconds)
    hue = hue_base + seconds * 0.35
    nebula_alpha = int(110 + 145 * level)

    lo.alpha = 255
    lo.pen = brush.gradient(brush.LINEAR, 0, 0, LW * 0.4, LH, [
        (0.0, oklch(14, 30, hue + 180)),
        (1.0, oklch(22, 45, hue + 30)),
    ])
    lo.clear()
    yield

    lo.alpha = nebula_alpha
    nebula_b.ramp([
        (0.0, CLEAR), (0.6, CLEAR),
        (0.75, oklch(80, 110, hue + 70, 100)),
        (0.92, oklch(145, 130, hue + 80, 180)),
        (1.0, oklch(210, 70, hue + 90, 220)),
    ])
    nebula_b.transform = wrapped(nebula_b, 0, seconds)
    lo.pen = nebula_b
    lo.clear()
    yield

    nebula_a.ramp([
        (0.0, CLEAR), (0.55, CLEAR),
        (0.7, oklch(90, 120, hue, 110)),
        (0.86, oklch(155, 135, hue + 8, 185)),
        (0.96, oklch(210, 90, hue + 16, 225)),
        (1.0, oklch(240, 40, hue + 20, 240)),
    ])
    nebula_a.transform = wrapped(nebula_a, 1, seconds)
    lo.pen = nebula_a
    lo.clear()
    yield

    for index, cloud in enumerate(clouds):
        tint = hue + CLOUD_HUES[index] + 20 * math.sin(seconds / 60 + index)
        cloud.ramp([
            (0.0, CLEAR), (0.86, CLEAR),
            (0.93, oklch(125, 140, tint, 130)),
            (1.0, oklch(200, 110, tint + 10, 200)),
        ])
        cloud.transform = wrapped(cloud, 2 + index, seconds, 0.65)
        lo.pen = cloud
        lo.clear()
        yield

    lo.alpha = 255
    lanes.ramp([
        (0.0, color.rgb(0, 0, 0, 190)),
        (0.12, color.rgb(0, 0, 0, 110)),
        (0.25, CLEAR), (1.0, CLEAR),
    ])
    lanes.transform = wrapped(lanes, 6, seconds, 0.3)
    lo.pen = lanes
    lo.clear()
    yield

    lo.alpha = 255
    for spot in spots:
        spot.draw(seconds, 200)
    manage_auroras(seconds)
    for patch in auroras:
        patch.draw_glow(seconds, level)
    lo.alpha = 255
    yield

    lo.blur(0.9)
    yield

    # aurora rays go on after the blur so they stay crisp
    rays.transform = mat3().translate((seconds * 1.5) % (rays.repeat * rays.scale), 0).scale(1, 10)
    for patch in auroras:
        patch.draw_detail(seconds, level)
    lo.alpha = 255
    yield

    # sharp near layers are composed in the same step as the upscale so a
    # frame never shows the sky without them
    wisps_far.ramp([
        (0.0, CLEAR), (0.74, CLEAR),
        (0.88, oklch(120, 120, hue + 140, 70)),
        (1.0, oklch(190, 100, hue + 150, 150)),
    ])
    wisps_far.transform = wrapped(wisps_far, 7, seconds, 0.9)
    wisps.ramp([
        (0.0, CLEAR), (0.82, CLEAR),
        (0.92, oklch(140, 140, hue + 40, 80)),
        (0.98, oklch(200, 120, hue + 50, 150)),
        (1.0, oklch(230, 70, hue + 55, 190)),
    ])
    wisps.transform = wrapped(wisps, 8, seconds, 1.5)
    bg.blit(lo, rect(0, 0, W, H), image.BILINEAR)
    bg.alpha = int(120 + 135 * level)
    bg.pen = wisps_far
    bg.clear()
    bg.pen = wisps
    bg.clear()
    bg.alpha = 255
    stars.occlude(seconds)


# -- stars --

STAR_TINTS = (
    (170, 200, 255),
    (215, 228, 255),
    (255, 255, 255),
    (255, 236, 200),
    (255, 200, 150),
    (255, 160, 130),
)
STAR_LEVELS = 8
STAR_COLORS = [
    [color.rgb(r * (n + 1) // STAR_LEVELS, g * (n + 1) // STAR_LEVELS, b * (n + 1) // STAR_LEVELS)
     for n in range(STAR_LEVELS)]
    for r, g, b in STAR_TINTS
]


class Stars:
    def __init__(self, count):
        self.count = count
        self.x = array("f", [rand(0, W) for _ in range(count)])
        self.y = array("f", [rand(0, H) for _ in range(count)])
        self.layer = bytearray([random.getrandbits(8) % 3 for _ in range(count)])
        self.tint = bytearray([min(5, int(random.random() ** 1.5 * 6)) for _ in range(count)])
        # a few stars are much brighter than the rest
        self.base = array("f", [rand(1.0, 4.0) + (3.0 if random.random() < 0.08 else 0.0)
                                for _ in range(count)])
        self.phase = array("f", [rand(0, TAU) for _ in range(count)])
        self.rate = array("f", [rand(0.6, 3.0) for _ in range(count)])
        self.shade = bytearray(count)
        self.offset = [[0.0, 0.0] for _ in LAYER_SPEED]

    def advance(self, seconds, dt):
        heading = seconds * 0.004 + 0.6
        dx, dy = math.cos(heading), math.sin(heading) * 0.5
        for index, speed in enumerate(LAYER_SPEED):
            offset = self.offset[index]
            offset[0] = (offset[0] + dx * speed * dt) % W
            offset[1] = (offset[1] + dy * speed * dt) % H

    def occlude(self, seconds):
        circles = []
        for spot in spots:
            x, y = spot.position(seconds)
            circles.append((x * 2, y * 2, (spot.r * 2) ** 2))
        for i in range(self.count):
            offset = self.offset[self.layer[i]]
            sx = (self.x[i] + offset[0]) % W
            sy = (self.y[i] + offset[1]) % H
            shade = 0
            for cx, cy, r2 in circles:
                d2 = (sx - cx) ** 2 + (sy - cy) ** 2
                if d2 < r2 * 0.4:
                    shade = 4
                elif d2 < r2 and shade < 2:
                    shade = 2
            self.shade[i] = shade

    def draw(self, seconds, twinkle):
        sin = math.sin
        for i in range(self.count):
            offset = self.offset[self.layer[i]]
            x = int((self.x[i] + offset[0]) % W)
            y = int((self.y[i] + offset[1]) % H)
            shimmer = twinkle * sin(seconds * self.rate[i] + self.phase[i])
            level = self.base[i] + shimmer - self.shade[i]
            if level < 0.5:
                continue
            level = int(level) if level < STAR_LEVELS else STAR_LEVELS - 1
            ramp = STAR_COLORS[self.tint[i]]
            if level >= 5:
                screen.pen = ramp[level - 4]
                screen.rectangle(x - 1, y, 3, 1)
                screen.rectangle(x, y - 1, 1, 3)
                if level >= 6:
                    screen.pen = ramp[1]
                    screen.put(x - 2, y)
                    screen.put(x + 2, y)
                    screen.put(x, y - 2)
                    screen.put(x, y + 2)
            screen.pen = ramp[level]
            screen.put(x, y)


stars = Stars(STAR_COUNT)


# -- black holes --

@micropython.viper
def lens(buf, stride: int, cx: int, cy: int, radius: int, e2: int, s2: int, tmp):
    """Point-mass gravitational lens over a square region of the screen.

    Each pixel at offset t from the hole shows what was at t * (1 - E^2 / |t|^2),
    so the background bends into an Einstein ring of radius E. Inside the
    shadow radius nothing escapes. The deflection eases off towards the region
    edge so there is no seam.
    """
    dst = ptr32(buf)
    src = ptr32(tmp)
    row = stride >> 2
    size = radius * 2 + 1
    j = 0
    while j < size:
        base = (cy - radius + j) * row + cx - radius
        i = 0
        while i < size:
            src[j * size + i] = dst[base + i]
            i += 1
        j += 1
    r2 = radius * radius
    j = 0
    while j < size:
        dy = j - radius
        base = (cy + dy) * row + cx
        i = 0
        while i < size:
            dx = i - radius
            d2 = dx * dx + dy * dy
            if d2 < r2:
                if d2 < s2:
                    dst[base + dx] = -16777216
                else:
                    wq = ((r2 - d2) << 12) // r2
                    k = (e2 * ((wq * wq) >> 12)) // d2
                    f = 4096 - k
                    sx = (dx * f) >> 12
                    sy = (dy * f) >> 12
                    if sx < 0 - radius:
                        sx = 0 - radius
                    if sx > radius:
                        sx = radius
                    if sy < 0 - radius:
                        sy = 0 - radius
                    if sy > radius:
                        sy = radius
                    dst[base + dx] = src[(sy + radius) * size + sx + radius]
            i += 1
        j += 1


try:
    FRAMEBUFFER = screen.raw
    STRIDE = screen.stride
    LENSING = True
except AttributeError:
    FRAMEBUFFER = None
    STRIDE = 0
    LENSING = False

# blackbody-ish ramp from the hot inner disk out to the cool rim
DISK_TINTS = (
    (200, 225, 255),
    (240, 245, 255),
    (255, 240, 215),
    (255, 215, 150),
    (255, 170, 90),
    (250, 120, 50),
    (210, 70, 30),
    (140, 35, 20),
)
DISK_LEVELS = 16
DISK_COLORS = []
for _r, _g, _b in DISK_TINTS:
    _ramp = []
    for _n in range(DISK_LEVELS):
        _f = (_n / (DISK_LEVELS - 1)) ** 0.6
        _ramp.append(color.rgb(int(_r * _f), int(_g * _f), int(_b * _f), min(255, 110 + _n * 12)))
    DISK_COLORS.append(_ramp)
RING_WARM = color.rgb(255, 235, 200, 220)
RING_PALE = color.rgb(200, 215, 255, 60)


class Segment:
    def __init__(self, contour, ring, phi, front, glow, warmth):
        self.shape = shape.custom(array("f", contour))
        self.ring = ring
        self.phi = phi
        self.front = front
        self.glow = glow
        self.warmth = warmth


class BlackHole:
    def __init__(self, now, has_disk, others):
        self.has_disk = has_disk
        self.born = now
        self.life = int(rand(70, 160) * 1000)
        self.shadow = rand(5.5, 10.0) if has_disk else rand(4.0, 7.0)
        self.einstein = self.shadow * (1.55 if has_disk else 1.8)
        if has_disk:
            self.inner = self.shadow * 1.7
            self.outer = self.shadow * 4.2
            self.radius = int(self.outer * 1.1) + 2
        else:
            self.radius = int(self.einstein * 3.2) + 2
        self.tmp = bytearray((self.radius * 2 + 1) ** 2 * 4)
        margin = self.radius + 2
        for _ in range(12):
            self.x = rand(margin, W - margin)
            self.y = rand(margin, H - margin)
            if all((self.x - o.x) ** 2 + (self.y - o.y) ** 2 > (self.radius + o.radius) ** 2
                   for o in others):
                break
        heading = rand(0, TAU)
        speed = rand(1.0, 2.5)
        self.vx, self.vy = math.cos(heading) * speed, math.sin(heading) * speed
        self.ring = shape.circle(0, 0, self.shadow * 1.04).stroke(1.1 if has_disk else 0.6)
        self.segments = self.build_disk() if has_disk else []
        self.glow = None
        if has_disk:
            self.glow = brush.gradient(brush.RADIAL, 0, 0, self.outer * 1.3, 0, [
                (0.0, color.rgb(255, 210, 150, 150)),
                (0.35, color.rgb(255, 160, 90, 70)),
                (1.0, CLEAR),
            ])
            self.glow_shape = shape.circle(0, 0, self.outer * 1.3)

    def build_disk(self):
        flatten = rand(0.16, 0.3)
        tilt = math.radians(rand(-25, 25))
        spin = 1 if random.random() < 0.5 else -1
        cos_t, sin_t = math.cos(tilt), math.sin(tilt)
        self.spin = spin
        self.modes = [(random.getrandbits(2) + 2, rand(0, TAU)) for _ in range(DISK_RINGS)]
        growth = self.outer / self.inner
        radii = [self.inner * growth ** (n / DISK_RINGS) for n in range(DISK_RINGS + 1)]

        def point(r, phi):
            x = r * math.cos(phi)
            y = -r * math.sin(phi) * flatten
            return x * cos_t - y * sin_t, x * sin_t + y * cos_t

        segments = []
        step = TAU / DISK_SEGMENTS
        for ring in range(DISK_RINGS):
            r0, r1 = radii[ring], radii[ring + 1]
            r_mid = (r0 + r1) / 2
            beta = 0.4 * math.sqrt(self.inner / r_mid)
            gamma = 1 / math.sqrt(1 - beta * beta)
            emission = (self.inner / r_mid) ** 1.4
            for n in range(DISK_SEGMENTS):
                a0, a1 = n * step, (n + 1) * step
                contour = []
                for k in range(4):
                    contour.extend(point(r1, a0 + (a1 - a0) * k / 3))
                for k in range(3, -1, -1):
                    contour.extend(point(r0, a0 + (a1 - a0) * k / 3))
                phi = (a0 + a1) / 2
                # line-of-sight speed: one side of the disk comes towards us
                approach = -spin * math.cos(phi) * beta
                doppler = 1 / (gamma * (1 - approach))
                glow = emission * doppler ** 3
                warmth = clamp(int(ring * 2 + 1 - approach * 6), 0, len(DISK_TINTS) - 1)
                segments.append(Segment(contour, ring, phi, math.sin(phi) < 0, glow, warmth))
        # the eye compresses brightness, so the dim receding side stays visible
        peak = max(segment.glow for segment in segments)
        for segment in segments:
            segment.glow = math.sqrt(segment.glow / peak)
        return segments

    def fade(self, now):
        age = now - self.born
        return clamp(min(age, self.life - age) / HOLE_FADE_MS, 0.0, 1.0)

    def alive(self, now):
        return now - self.born < self.life

    def move(self, dt):
        margin = self.radius + 2
        self.x += self.vx * dt
        self.y += self.vy * dt
        if self.x < margin or self.x > W - margin:
            self.vx = -self.vx
            self.x = clamp(self.x, margin, W - margin)
        if self.y < margin or self.y > H - margin:
            self.vy = -self.vy
            self.y = clamp(self.y, margin, H - margin)

    def draw_disk(self, front, seconds, fade, place):
        spin = self.spin
        turns = []
        for ring in range(DISK_RINGS):
            r_ratio = (DISK_RINGS - ring) / DISK_RINGS
            turns.append(spin * seconds * 0.9 * r_ratio ** 1.5)
        for segment in self.segments:
            if segment.front != front:
                continue
            m, offset = self.modes[segment.ring]
            swirl = 0.8 + 0.2 * math.sin(m * (segment.phi - turns[segment.ring]) + offset)
            # the far side is magnified as the hole bends it up over the shadow
            boost = 1.15 if front else 1.4
            level = int(DISK_LEVELS * fade * (0.5 + 0.5 * segment.glow) * swirl * boost)
            if level <= 0:
                continue
            ramp = DISK_COLORS[segment.warmth]
            screen.pen = ramp[level if level < DISK_LEVELS else DISK_LEVELS - 1]
            segment.shape.transform = place
            screen.shape(segment.shape)

    def draw(self, now, seconds):
        fade = self.fade(now)
        if fade <= 0:
            return
        cx, cy = int(self.x), int(self.y)
        place = mat3().translate(cx, cy)
        if self.has_disk:
            self.glow.geometry(cx, cy, cx + self.outer * 1.3, cy)
            screen.pen = self.glow
            self.glow_shape.transform = place
            screen.alpha = int(255 * fade)
            screen.shape(self.glow_shape)
            screen.alpha = 255
            self.draw_disk(False, seconds, fade, place)
        if LENSING:
            e2 = int(self.einstein * self.einstein * fade)
            s2 = max(1, int(self.shadow * self.shadow * fade * fade))
            lens(FRAMEBUFFER, STRIDE, cx, cy, self.radius, e2, s2, self.tmp)
        else:
            screen.pen = color.rgb(0, 0, 0, int(255 * fade))
            screen.shape(shape.circle(cx, cy, self.shadow * fade))
        if self.has_disk:
            self.draw_disk(True, seconds, fade, place)
        screen.pen = RING_WARM if self.has_disk else RING_PALE
        screen.alpha = int(255 * fade)
        self.ring.transform = place
        screen.shape(self.ring)
        screen.alpha = 255


holes = []
next_hole_check = 0


def manage_holes(now):
    global next_hole_check
    holes[:] = [hole for hole in holes if hole.alive(now)]
    if now < next_hole_check:
        return
    next_hole_check = now + HOLE_CHECK_MS
    if len(holes) < MAX_HOLES and (not holes or random.random() < 0.55):
        holes.append(BlackHole(now, random.random() < 0.6, holes))


# -- lights, power and the frame loop --

def case_lights(seconds, ceiling):
    lights = []
    for index in range(4):
        level = nebula_level(seconds - index * 2.5)
        breath = 0.8 + 0.2 * math.sin(TAU * seconds / 6 + index * 1.7)
        lights.append(ceiling * (0.2 + 0.8 * level) * breath)
    badge.caselights(*lights)


def on_battery():
    try:
        return not badge.usb_connected()
    except AttributeError:
        return not badge.is_charging()


def battery_level():
    try:
        return badge.battery_level() if on_battery() else 100
    except Exception:  # noqa: BLE001
        return 100


def deep_sleep():
    badge.caselights(0)
    backlight.restore()
    try:
        badge.sleep()
    except Exception:  # noqa: BLE001
        pass


started = time.ticks_ms()
last_frame = started
sky = None
next_regen = 0
next_battery = 0
battery = battery_level()


def update():
    global last_frame, sky, next_regen, next_battery, battery

    frame_start = time.ticks_ms()
    now = time.ticks_diff(frame_start, started)
    dt = time.ticks_diff(frame_start, last_frame) / 1000
    last_frame = frame_start
    seconds = now / 1000

    if now > INPUT_GRACE_MS and badge.pressed():
        return True

    if now >= next_battery:
        battery = battery_level()
        next_battery = now + BATTERY_CHECK_MS
    if now >= SLEEP_AFTER_MS or battery <= CRITICAL_BATTERY:
        deep_sleep()
        return True

    dim = 1.0 if battery <= LOW_BATTERY else clamp((now - DIM_AFTER_MS) / DIM_FADE_MS, 0.0, 1.0)
    level = nebula_level(seconds)

    if sky is None and now >= next_regen:
        sky = sky_layers(seconds)
        next_regen = now + (DIM_REGEN_MS if dim >= 1.0 else BRIGHT_REGEN_MS)
        top = BACKLIGHT_BRIGHT + (BACKLIGHT_DIM - BACKLIGHT_BRIGHT) * dim
        backlight.set(top * (0.82 + 0.18 * level))
    if sky is not None:
        try:
            next(sky)
        except StopIteration:
            sky = None

    stars.advance(seconds, dt)
    manage_holes(now)
    for hole in holes:
        hole.move(dt)

    screen.blit(bg, vec2(0, 0))
    stars.draw(seconds, 1.5 * (1.0 - 0.5 * dim))
    for hole in holes:
        hole.draw(now, seconds)

    case_lights(seconds, CASE_BRIGHT + (CASE_DIM - CASE_BRIGHT) * dim)

    # wait out the rest of the frame, but keep watching the buttons so a quick
    # tap is never missed at the low dimmed frame rate
    deadline = time.ticks_add(frame_start, 1000 // (BRIGHT_FPS if dim < 1.0 else DIM_FPS))
    while True:
        spare = time.ticks_diff(deadline, time.ticks_ms())
        if spare <= 0:
            break
        time.sleep_ms(min(spare, 25))
        badge.poll()
        if now > INPUT_GRACE_MS and (badge.pressed() or badge.held()):
            return True
    return None


def on_exit():
    badge.caselights(0)
    backlight.restore()
    badge.default_clear = previous_clear


# draw the whole sky once before the first frame so it never starts black
for _ in sky_layers(0):
    pass
