"""Install the bootloader, WiFi config and current app over USB.

Needed once per badge, and again only when main.py or ota.py change.
Everything else arrives over the air.

    pip install mpremote
    python tools/flash.py [--port COM5]
"""
import argparse
import pathlib
import subprocess
import sys

BADGE = pathlib.Path(__file__).resolve().parent.parent / "badge"

# Forget the installed version so the next WiFi connect reinstalls the
# published build over whatever was just copied from this checkout.
FORGET_VERSION = "import os\ntry:\n os.remove('ota_state.json')\nexcept OSError:\n pass"


def main():
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--port", help="serial port, e.g. COM5 (default: first found)")
    args = p.parse_args()
    if not (BADGE / "wifi_config.py").exists():
        sys.exit("copy badge/wifi_config.example.py to badge/wifi_config.py "
                 "and add your networks first")

    cmd = [sys.executable, "-m", "mpremote"]
    if args.port:
        cmd += ["connect", args.port]
    cmd += ["cp", str(BADGE / "main.py"), str(BADGE / "ota.py"),
            str(BADGE / "wifi_config.py"), ":", "+",
            "cp", "-r", str(BADGE / "app"), ":", "+",
            "exec", FORGET_VERSION, "+",
            "reset"]
    subprocess.run(cmd, check=True)


if __name__ == "__main__":
    main()
