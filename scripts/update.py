import requests
import time
import re
import socket
import ipaddress
import asyncio
from pathlib import Path
from urllib.parse import urlparse
from concurrent.futures import ThreadPoolExecutor

# ===================== KAYNAKLAR =====================

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

# ===================== AYARLAR =====================

TRACKER_RE = re.compile(r"^(udp|http|https|wss?)://", re.IGNORECASE)

TIMEOUT = 15
RETRIES = 3
BACKOFF = 1.5

CONNECT_TIMEOUT = 3
MAX_WORKERS = 200   # paralellik seviyesi (GitHub Actions için ideal)

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "tracker-aggregator/1.0 (+https://github.com/your-repo)"
})

# ===================== YARDIMCI =====================

def fetch(url):
    for attempt in range(1, RETRIES + 1):
        try:
            r = SESSION.get(url, timeout=TIMEOUT)
            r.raise_for_status()
            return r.text.splitlines()
        except Exception:
            if attempt == RETRIES:
                return []
            time.sleep(BACKOFF ** attempt)


def normalize_tracker(url: str) -> str:
    url = url.rstrip("/")
    if url.startswith(("ws://", "wss://")):
        return url
    if not url.lower().endswith("/announce"):
        return url + "/announce"
    return url


def is_ipv6_literal(url: str) -> bool:
    try:
        host = urlparse(url).hostname
        if not host:
            return False
        return ipaddress.ip_address(host).version == 6
    except Exception:
        return False


def udp_test(host: str, port: int) -> bool:
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(CONNECT_TIMEOUT)
        sock.sendto(b"\x00", (host, port))
        sock.close()
        return True
    except Exception:
        return False


def tcp_test(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=CONNECT_TIMEOUT):
            return True
    except Exception:
        return False


def sync_test_tracker(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port
    if not host or not port:
        return False

    scheme = parsed.scheme.lower()
    if scheme == "udp":
        return udp_test(host, port)
    return tcp_test(host, port)


# ===================== ASYNC TEST =====================

async def test_all(trackers: list[str]) -> list[str]:
    loop = asyncio.get_running_loop()
    alive = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as pool:
        tasks = [
            loop.run_in_executor(pool, sync_test_tracker, tracker)
            for tracker in trackers
        ]

        for tracker, result in zip(trackers, await asyncio.gather(*tasks)):
            if result:
                alive.append(tracker)

    return alive


# ===================== MAIN =====================

def main():
    trackers = set()

    # --- TOPLA ---
    for src in URLS:
        for line in fetch(src):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if not TRACKER_RE.match(line):
                continue
            if is_ipv6_literal(line):
                continue
            trackers.add(normalize_tracker(line))

    trackers = sorted(trackers)
    print(f"[INFO] Collected {len(trackers)} trackers")

    # --- ASYNC TEST ---
    alive = asyncio.run(test_all(trackers))
    print(f"[INFO] Alive trackers: {len(alive)}")

    # --- YAZ ---
    OUT_FILE.write_text("\n".join(sorted(alive)) + "\n", encoding="utf-8")
    print(f"✔ Written {len(alive)} trackers to {OUT_FILE}")


if __name__ == "__main__":
    main()
