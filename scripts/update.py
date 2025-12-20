import asyncio
import aiohttp
import struct
import socket
import time
import random
import re
import logging
from urllib.parse import urlparse
from pathlib import Path
import os

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

OUTPUT_FILE = "best.txt"
MAX_TRACKERS = 300  # En iyi kaç tanesini kaydedelim? (Hepsini istersen bu sayıyı büyüt)
TIMEOUT = 5        # Zaman aşımı (saniye)
CONCURRENCY = 500   # Aynı anda kaç bağlantı test edilsin

# UDP Protokol Sabitleri (BEP 15)
UDP_CONNECTION_ID = 0x41727101980
UDP_ACTION_CONNECT = 0

# Logger Ayarları
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# ===================== YARDIMCI FONKSİYONLAR =====================

def get_random_transaction_id():
    return random.getrandbits(32)

def pack_udp_connect_request(trans_id):
    # BEP 15: connection_id (64-bit), action (32-bit), transaction_id (32-bit)
    return struct.pack("!QII", UDP_CONNECTION_ID, UDP_ACTION_CONNECT, trans_id)

def unpack_udp_connect_response(data):
    # BEP 15: action (32-bit), transaction_id (32-bit), connection_id (64-bit)
    if len(data) < 16:
        return None
    return struct.unpack("!IIQ", data[:16])

# ===================== PROTOKOL TESTLERİ =====================

class TrackerTester:
    def __init__(self):
        self.results = []

    async def check_udp(self, url):
        parsed = urlparse(url)
        host, port = parsed.hostname, parsed.port
        if not host or not port:
            return None

        trans_id = get_random_transaction_id()
        packet = pack_udp_connect_request(trans_id)
        
        start_time = time.time()
        
        loop = asyncio.get_running_loop()
        
        # UDP Transport oluştur
        transport = None
        protocol = None
        
        class UdpClientProtocol(asyncio.DatagramProtocol):
            def __init__(self):
                self.received = asyncio.Future()
            def connection_made(self, transport):
                self.transport = transport
                self.transport.sendto(packet)
            def datagram_received(self, data, addr):
                if not self.received.done():
                    self.received.set_result(data)
            def error_received(self, exc):
                pass
            def connection_lost(self, exc):
                pass

        try:
            # IP adresini çöz (DNS)
            # await loop.getaddrinfo(host, port) # Opsiyonel: DNS süresini ayırabiliriz
            
            transport, protocol = await asyncio.wait_for(
                loop.create_datagram_endpoint(
                    lambda: UdpClientProtocol(),
                    remote_addr=(host, port)
                ), timeout=TIMEOUT
            )
            
            data = await asyncio.wait_for(protocol.received, timeout=TIMEOUT)
            latency = (time.time() - start_time) * 1000 # ms
            
            unpacked = unpack_udp_connect_response(data)
            if unpacked:
                action, res_trans_id, _ = unpacked
                # Action 0 (Connect) ve Transaction ID eşleşmeli
                if action == 0 and res_trans_id == trans_id:
                    return latency

        except (asyncio.TimeoutError, OSError):
            return None
        finally:
            if transport:
                transport.close()
        return None

    async def check_http(self, url, session):
        # HTTP Trackerları genellikle GET isteği ile test edilir.
        # Rastgele bir info_hash ile deneriz. Hata dönse bile sunucu ayakta demektir.
        params = {
            'info_hash': b'01234567890123456789', # 20 byte dummy
            'peer_id': b'-PC0001-012345678900',
            'port': 6881,
            'uploaded': 0,
            'downloaded': 0,
            'left': 0,
            'compact': 1
        }
        
        start_time = time.time()
        try:
            async with session.get(url, params=params, timeout=TIMEOUT, allow_redirects=True) as response:
                # 200 OK veya tracker spesifik hatalar (örn: unregistered torrent) başarı sayılır.
                # 5xx sunucu hatası veya bağlantı kopması başarısızlıktır.
                if response.status in [200, 400, 403, 404]: 
                    # İçeriğin bencoded olup olmadığını kontrol etmek ekstra güvenlik sağlar ama
                    # Status code genellikle yeterlidir.
                    latency = (time.time() - start_time) * 1000
                    return latency
        except Exception:
            return None
        return None

    async def worker(self, url, semaphore, session):
        async with semaphore:
            latency = None
            if url.startswith("udp://"):
                latency = await self.check_udp(url)
            elif url.startswith(("http://", "https://")):
                latency = await self.check_http(url, session)
            
            if latency is not None:
                logger.debug(f"SUCCESS: {url} ({latency:.1f}ms)")
                self.results.append((url, latency))
            else:
                logger.debug(f"FAIL: {url}")

# ===================== MAIN AKIŞ =====================

async def fetch_trackers(session):
    trackers = set()
    logger.info("Tracker listeleri indiriliyor...")
    
    for src in URLS:
        try:
            async with session.get(src, timeout=15) as resp:
                if resp.status == 200:
                    text = await resp.text()
                    for line in text.splitlines():
                        line = line.strip()
                        if line and not line.startswith("#") and "://" in line:
                            trackers.add(line)
        except Exception as e:
            logger.error(f"Kaynak indirilemedi {src}: {e}")
            
    logger.info(f"Toplam {len(trackers)} benzersiz tracker bulundu.")
    return list(trackers)

async def main():
    tester = TrackerTester()
    semaphore = asyncio.Semaphore(CONCURRENCY)
    
    async with aiohttp.ClientSession() as session:
        # 1. Listeyi İndir
        trackers = await fetch_trackers(session)
        if not trackers:
            logger.error("Hiç tracker bulunamadı!")
            return

        # 2. Testleri Başlat
        logger.info(f"Test başlıyor... ({len(trackers)} tracker, {CONCURRENCY} thread)")
        tasks = [tester.worker(url, semaphore, session) for url in trackers]
        
        # İlerleme çubuğu gibi çıktı almak istersen tqdm kullanabilirsin ama workflow için print yeterli.
        await asyncio.gather(*tasks)

    # 3. Sonuçları İşle
    valid_trackers = tester.results
    logger.info(f"Çalışan Tracker Sayısı: {len(valid_trackers)}")

    # Gecikme süresine (latency) göre sırala (en düşük en iyi)
    valid_trackers.sort(key=lambda x: x[1])

    # En iyileri seç
    best_trackers = [t[0] for t in valid_trackers[:MAX_TRACKERS]]

    # 4. Dosyaya Yaz
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        # Aralarına boş satır koyarak (qBittorrent formatına uygun) yazalım
        f.write("\n\n".join(best_trackers))
    
    logger.info(f"En iyi {len(best_trackers)} tracker '{OUTPUT_FILE}' dosyasına kaydedildi.")
    
    # Önizleme
    print("\n--- TOP 10 TRACKERS ---")
    for t in valid_trackers[:10]:
        print(f"{t[1]:.1f}ms - {t[0]}")

if __name__ == "__main__":
    # Windows uyumluluğu (Local testler için)
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
        
    asyncio.run(main())
