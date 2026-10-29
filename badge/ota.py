"""Pull-based over-the-air updates from the GitHub Pages site CI publishes.

Only files under app/ are installed this way. main.py and ota.py are the
bootloader: they change only over USB (tools/flash.py), so a bad push can
never break the code that installs the fix.

Runs on MicroPython and CPython (the tests): no os.path, no hexdigest().
"""
import binascii
import hashlib
import json
import os
import time

STATE_FILE = "ota_state.json"
CHUNK = 1024


def _chunks(url):
    """Yield the body of a GET in pieces. The only network code; tests replace it."""
    try:
        import requests
    except ImportError:
        import urequests as requests
    r = requests.get(url)
    try:
        if r.status_code != 200:
            raise OSError("HTTP %d: %s" % (r.status_code, url))
        while True:
            buf = r.raw.read(CHUNK)
            if not buf:
                break
            yield buf
    finally:
        r.close()


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


def _makedirs(root, rel):
    cur = root
    for part in rel.split("/")[:-1]:
        cur += part
        try:
            os.mkdir(cur)
        except OSError:
            pass
        cur += "/"


def _download(url, path):
    """Stream url into path. Returns (sha256 hex, size)."""
    h = hashlib.sha256()
    size = 0
    with open(path, "wb") as f:
        for buf in _chunks(url):
            h.update(buf)
            f.write(buf)
            size += len(buf)
    return binascii.hexlify(h.digest()).decode(), size


def read_state(root="/"):
    try:
        with open(root + STATE_FILE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def update(base_url, root="/"):
    """Install the published build if it differs from ours.

    Returns the new version, or None if already current. Every changed file
    is downloaded and checksummed before any is replaced, so a failed
    update leaves the installed build untouched.
    """
    base_url = base_url.rstrip("/") + "/"
    # The query string bypasses the Pages CDN cache (max-age 10 min).
    raw = b"".join(_chunks(base_url + "manifest.json?t=%d" % time.time()))
    manifest = json.loads(raw.decode())
    state = read_state(root)
    if manifest["version"] == state.get("version"):
        return None

    new = manifest["files"]
    old = state.get("files", {})
    for rel in new:
        if not rel.startswith("app/") or ".." in rel:
            raise ValueError("refusing to write outside app/: " + rel)

    staged = []
    try:
        for rel, meta in new.items():
            if old.get(rel) == meta["sha256"] and _exists(root + rel):
                continue
            _makedirs(root, rel)
            staged.append(rel)
            digest, size = _download(
                base_url + rel + "?v=" + meta["sha256"][:12], root + rel + ".new"
            )
            if digest != meta["sha256"] or size != meta["size"]:
                raise ValueError("checksum mismatch: " + rel)
    except Exception:
        for rel in staged:
            _remove(root + rel + ".new")
        raise

    for rel in staged:
        _remove(root + rel)  # FAT can't rename over an existing file
        os.rename(root + rel + ".new", root + rel)
    for rel in old:
        if rel not in new:
            _remove(root + rel)
    with open(root + STATE_FILE, "w") as f:
        json.dump({"version": manifest["version"],
                   "files": {rel: meta["sha256"] for rel, meta in new.items()}}, f)
    return manifest["version"]
