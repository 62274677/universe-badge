"""Build the site CI publishes to GitHub Pages: the app's live/ files plus manifest.json.

    python tools/build_manifest.py --version 12-abc1234 --out dist
"""
import argparse
import hashlib
import json
import pathlib
import shutil

ROOT = pathlib.Path(__file__).resolve().parent.parent


def build(src, out, version):
    src, out = pathlib.Path(src), pathlib.Path(out)
    if out.exists():
        shutil.rmtree(out)
    files = {}
    for path in sorted(src.rglob("*")):
        rel = path.relative_to(src).as_posix()
        # The badge refuses hidden paths (.DS_Store would block every update).
        hidden = any(part.startswith(".") for part in rel.split("/"))
        if path.is_dir() or hidden or "__pycache__" in path.parts:
            continue
        data = path.read_bytes()
        files[rel] = {"sha256": hashlib.sha256(data).hexdigest(), "size": len(data)}
        dest = out / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
    manifest = {"version": version, "files": files}
    out.mkdir(parents=True, exist_ok=True)
    (out / "manifest.json").write_text(json.dumps(manifest, indent=1, sort_keys=True))
    return manifest


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--version", required=True)
    p.add_argument("--src", default=ROOT / "badge" / "apps" / "universe_badge" / "live")
    p.add_argument("--out", default=ROOT / "dist")
    args = p.parse_args()
    manifest = build(args.src, args.out, args.version)
    print("build %s: %d files" % (manifest["version"], len(manifest["files"])))


if __name__ == "__main__":
    main()
