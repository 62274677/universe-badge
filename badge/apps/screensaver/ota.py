"""Over-the-air updates for this app's live/ code, from the GitHub Pages site
CI publishes on every push to main.

The Updater advances one small step per frame (the badge firmware's wifi and
fetch modules are both polled state machines), so the app keeps drawing and
HOME keeps working while a download is in flight.

This file and the loader (__init__.py) are installed over USB Disk Mode and
never replaced over the air, so a bad push can't break the code that installs
the fix. /system is read-only at runtime; builds go to a directory on / instead.
"""
import binascii
import json
import os
import random

import fetch
import wifi

try:
    import hashlib
except ImportError:  # some ports lack it; the size check still runs
    hashlib = None

IDLE, CONNECTING, MANIFEST, FILES = 0, 1, 2, 3
STATE = "/.ota.json"
MANIFEST_TMP = "/.manifest.tmp"

# Set by the loader before it imports live code: the build that is running.
build = None


def _exists(path):
    try:
        os.stat(path)
        return True
    except OSError:
        return False


def _remove(path):
    try:
        os.remove(path)
    except OSError:
        pass


def _mkdirs(path):
    """mkdir -p for an absolute path, without os.path (MicroPython has none)."""
    parts = path.split("/")
    cur = parts[0]
    for part in parts[1:]:
        if not part:
            continue
        cur += "/" + part
        try:
            os.mkdir(cur)
        except OSError:
            pass


def _measure(path):
    """Returns (size, sha256 hex or None if hashlib is unavailable)."""
    h = hashlib.sha256() if hashlib else None
    size = 0
    with open(path, "rb") as f:
        while True:
            buf = f.read(1024)
            if not buf:
                break
            size += len(buf)
            if h:
                h.update(buf)
    return size, binascii.hexlify(h.digest()).decode() if h else None


def _read_json(path):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def _check_path(rel):
    if rel.startswith("/") or rel.startswith(".") or "\\" in rel or ".." in rel.split("/"):
        raise ValueError("bad path in manifest: " + rel)


def _wifi_configured():
    try:
        import secrets
    except ImportError:
        return False
    return bool(getattr(secrets, "WIFI_SSID", ""))


def current_version(install_dir):
    """Version of the build installed in install_dir, or None."""
    return _read_json(install_dir + STATE).get("version")


class Updater:
    def __init__(self, base_url, install_dir, every_ms=300000, retry_ms=60000,
                 connect_ms=30000, fetch_ms=60000):
        self.base = base_url.rstrip("/") + "/"
        self.dir = install_dir
        self.every_ms = every_ms
        self.retry_ms = retry_ms
        self.connect_ms = connect_ms
        self.fetch_ms = fetch_ms
        self.status = "waiting to check"
        # Set when a new build lands; the loader reloads the app and clears it.
        self.installed = False
        self._phase = IDLE
        self._next = 0
        self._deadline = 0
        self._req = None
        self._manifest = None
        self._todo = []
        self._staged = []
        self._current = None

    @property
    def busy(self):
        return self._phase != IDLE

    def step(self, now):
        """Advance by one step. now is badge.ticks (milliseconds)."""
        try:
            self._step(now)
        except Exception as e:
            self._fail(now, e)

    def _step(self, now):
        if self._phase == IDLE:
            if now < self._next:
                return
            if not _wifi_configured():
                self.status = "no WIFI_SSID in /system/secrets.py"
                self._next = now + self.every_ms
                return
            self._phase = CONNECTING
            self._deadline = now + self.connect_ms
            self.status = "connecting to wifi"

        if self._phase == CONNECTING:
            if wifi.connect():
                _mkdirs(self.dir)
                # The query string bypasses the Pages CDN cache (max-age 10 min).
                self._fetch(now, "manifest.json?nocache=%d" % random.getrandbits(30),
                            self.dir + MANIFEST_TMP)
                self._phase = MANIFEST
                self.status = "checking for update"
            elif now > self._deadline:
                raise OSError("wifi: %s" % (wifi.status()[1],))
            return

        if self._phase == MANIFEST:
            if not self._done(now):
                return
            manifest = _read_json(self.dir + MANIFEST_TMP)
            _remove(self.dir + MANIFEST_TMP)
            if "version" not in manifest or "files" not in manifest:
                raise ValueError("bad manifest")
            if manifest["version"] == current_version(self.dir):
                self._finish(now, "up to date")
                return
            self._plan(manifest)
            self._phase = FILES

        if self._phase == FILES:
            if self._req is not None:
                if not self._done(now):
                    return
                self._verify(self._current)
            if self._todo:
                self._start(now, self._todo.pop())
                return
            self._apply(now)

    def _fetch(self, now, rel_url, dest):
        self._req = fetch.url(self.base + rel_url).to(dest)
        self._deadline = now + self.fetch_ms

    def _done(self, now):
        req = self._req
        if req:
            self._req = None
            return True
        if req.error:
            self._req = None
            raise OSError("download failed: %s" % (req.error,))
        if now > self._deadline:
            self._req = None
            raise OSError("download timed out")
        return False

    def _plan(self, manifest):
        files = manifest["files"]
        for rel in files:
            _check_path(rel)
        have = _read_json(self.dir + STATE).get("files", {})
        self._manifest = manifest
        self._staged = []
        self._todo = [rel for rel, meta in files.items()
                      if have.get(rel) != meta["sha256"] or not _exists(self.dir + "/" + rel)]

    def _start(self, now, rel):
        meta = self._manifest["files"][rel]
        path = self.dir + "/" + rel
        _mkdirs(path.rsplit("/", 1)[0])
        self._current = rel
        self._staged.append(rel)
        self._fetch(now, rel + "?v=" + meta["sha256"][:12], path + ".new")
        self.status = "downloading " + rel

    def _verify(self, rel):
        meta = self._manifest["files"][rel]
        size, digest = _measure(self.dir + "/" + rel + ".new")
        if size != meta["size"] or (digest is not None and digest != meta["sha256"]):
            raise ValueError("checksum mismatch: " + rel)

    def _apply(self, now):
        """Every changed file is downloaded and verified; swap them all in."""
        files = self._manifest["files"]
        old = _read_json(self.dir + STATE).get("files", {})
        for rel in self._staged:
            path = self.dir + "/" + rel
            _remove(path)  # FAT can't rename over an existing file
            os.rename(path + ".new", path)
        removed = [rel for rel in old if rel not in files]
        for rel in removed:
            _remove(self.dir + "/" + rel)
        with open(self.dir + STATE, "w") as f:
            json.dump({"version": self._manifest["version"],
                       "files": {rel: meta["sha256"] for rel, meta in files.items()}}, f)
        changed = bool(self._staged or removed)
        self.installed = self.installed or changed
        version = self._manifest["version"]
        self._staged = []
        self._manifest = None
        self._finish(now, ("installed build " if changed else "up to date: ") + version)

    def _finish(self, now, status):
        self._phase = IDLE
        self._next = now + self.every_ms
        self.status = status

    def _fail(self, now, error):
        for rel in self._staged:
            _remove(self.dir + "/" + rel + ".new")
        _remove(self.dir + MANIFEST_TMP)
        self._req = None
        self._manifest = None
        self._todo = []
        self._staged = []
        self._phase = IDLE
        self._next = now + self.retry_ms
        self.status = "update failed: %s" % (error,)
        print("[ota]", self.status)
