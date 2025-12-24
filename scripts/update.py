import requests
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

def fetch(url):
    r = requests.get(url, timeout=15)
    r.raise_for_status()
    return r.text.splitlines()

def main():
    trackers = set()

    for url in URLS:
        for line in fetch(url):
            line = line.strip()
            if not line:
                continue
            if line.startswith("#"):
                continue
            trackers.add(line)

    # deterministik çıktı (diff temiz olsun)
    result = sorted(trackers)

    OUT_FILE.write_text("\n".join(result) + "\n", encoding="utf-8")
    print(f"Written {len(result)} trackers")

if __name__ == "__main__":
    main()
