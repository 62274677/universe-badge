# Copy to wifi_config.py (gitignored); tools/flash.py puts it on the badge.
# Tried in order, skipping any network that isn't in range.
NETWORKS = [
    ("conference-ssid", "password"),
    ("phone-hotspot", "password"),
]
