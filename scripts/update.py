import requests
import time
import re
from pathlib import Path

URLS = [
    "https://raw.githubusercontent.com/ngosang/trackerslist/master/trackers_best.txt",
    "https://raw.githubusercontent.com/ngosang/trackerslist/refs/heads/master/trackers_best_ip.txt",
    "https://raw.githubusercontent.com/XIU2/TrackersListCollection/master/best.txt",
    "https://raw.githubusercontent.com/adysec/tracker/main/trackers_best.txt",
    "https://raw.githubusercontent.com/pkgforge-security/Trackers/main/trackers_stable.txt",
    "https://raw.githubusercontent.com/scriptzteam/BitTorrent-Tracker-List/main/trackers_best.txt",
    "https://raw.githubusercontent.com/scriptzteam/BitTorrent-Tracker-List/refs/heads/main/trackers_best_ip.txt",
    "https://newtrackon.com/api/stable?include_ipv4_only_trackers=true&include_ipv6_only_trackers=false",
    "https://trackers.run/s/rw_ws_up_hp_hs_v4.txt",
]

OUT_FILE = Path("best.txt")

# === SADECE GEÇERLİ TRACKER PROTOKOLLERİ ===
TRACKER_RE = re.compile(r"^(udp|http|https|wss?)://", re.IGNORECASE)

# === HTTP AYARLARI ===
TIMEOUT = 15
RETRIES = 3
BACKOFF = 1.5  # saniye

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "tracker-aggregator/1.0 (+https://github.com/your-repo)"
})


def fetch(url):
    for attempt in range(1, RETRIES + 1):
        try:
            r = SESSION.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            return r.text.splitlines()

        except Exception as e:
            if attempt == RETRIES:
                print(f"[FAIL] {url} → {e}")
                return []

            sleep_time = BACKOFF ** attempt
            print(f"[RETRY {attempt}] {url} (sleep {sleep_time:.1f}s)")
            time.sleep(sleep_time)


def main():
    trackers = set()

    for url in URLS:
        lines = fetch(url)
        if not lines:
            continue

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue

            if not TRACKER_RE.match(line):
                continue

            trackers.add(line)

    # === DETERMINISTIK ÇIKTI ===
    result = sorted(trackers)

    OUT_FILE.write_text("\n".join(result) + "\n", encoding="utf-8")
    print(f"✔ Written {len(result)} trackers")


if __name__ == "__main__":
    main()
