"""Build the site CI publishes to GitHub Pages: badge/app/** plus manifest.json.

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
    for path in sorted((src / "app").rglob("*")):
        if path.is_dir() or "__pycache__" in path.parts:
            continue
        rel = path.relative_to(src).as_posix()
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
    p.add_argument("--src", default=ROOT / "badge")
    p.add_argument("--out", default=ROOT / "dist")
    args = p.parse_args()
    manifest = build(args.src, args.out, args.version)
    print("build %s: %d files" % (manifest["version"], len(manifest["files"])))


if __name__ == "__main__":
    main()
