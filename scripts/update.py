import requests
import time
import re
import socket
import ipaddress
from pathlib import Path
from urllib.parse import urlparse

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

CONNECT_TIMEOUT = 3   # tracker connect testi
MAX_TESTS = 0

SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "tracker-aggregator/1.0 (+https://github.com/your-repo)"
})

# ===================== YARDIMCI FONKSİYONLAR =====================

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


def normalize_tracker(url: str) -> str:
    """ /announce yoksa ekle (ws/wss hariç) """
    url = url.rstrip("/")

    if url.startswith(("ws://", "wss://")):
        return url

    if not url.lower().endswith("/announce"):
        return url + "/announce"

    return url


def is_ipv6_literal(url: str) -> bool:
    """ Host kısmı IPv6 literal ise True """
    try:
        parsed = urlparse(url)
        host = parsed.hostname
        if not host:
            return False
        ip = ipaddress.ip_address(host)
        return ip.version == 6
    except ValueError:
        return False


def tcp_connect_test(host: str, port: int) -> bool:
    """ Basit TCP connect testi (http/https/ws/wss) """
    try:
        with socket.create_connection((host, port), timeout=CONNECT_TIMEOUT):
            return True
    except Exception:
        return False


def udp_connect_test(host: str, port: int) -> bool:
    """
    UDP için basit socket açma testi.
    (Gerçek announce değil, sadece ulaşılabilir mi)
    """
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.settimeout(CONNECT_TIMEOUT)
        sock.sendto(b"\x00", (host, port))
        sock.close()
        return True
    except Exception:
        return False


def is_tracker_reachable(url: str) -> bool:
    parsed = urlparse(url)
    host = parsed.hostname
    port = parsed.port

    if not host or not port:
        return False

    scheme = parsed.scheme.lower()

    if scheme == "udp":
        return udp_connect_test(host, port)

    if scheme in ("http", "https", "ws", "wss"):
        return tcp_connect_test(host, port)

    return False


# ===================== MAIN =====================

def main():
    trackers = set()

    # --- TOPLA ---
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

            if is_ipv6_literal(line):
                continue

            normalized = normalize_tracker(line)
            trackers.add(normalized)

    print(f"[INFO] Collected {len(trackers)} unique trackers")

    # --- CONNECT TEST ---
    alive = []
    tested = 0

    for tracker in sorted(trackers):
        if tested >= MAX_TESTS:
            break

        if is_tracker_reachable(tracker):
            alive.append(tracker)

        tested += 1

    print(f"[INFO] Alive after test: {len(alive)} / tested {tested}")

    # --- YAZ ---
    OUT_FILE.write_text("\n".join(sorted(alive)) + "\n", encoding="utf-8")
    print(f"✔ Written {len(alive)} trackers to {OUT_FILE}")


if __name__ == "__main__":
    main()
