# Universe Badge

A name badge that updates itself over WiFi whenever new code is pushed to GitHub.

Open it from the menu. It shows the code in `live/`, checks
`https://62274677.github.io/universe-badge/` when opened and every 5 minutes after, and
swaps in a new build without a restart. A green dot in the top-right corner means a check or
download is in progress.

Needs `WIFI_SSID` and `WIFI_PASSWORD` in `secrets.py` on the BADGER drive.
