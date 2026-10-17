import os
from playwright.sync_api import sync_playwright

def extract_master_playlist():
    """
    Correct extractor:
    - Captures ONLY the master playlist
    - Ignores child playlists (sec2, video-only, audio-only)
    - Works reliably in Smart IPTV
    """

    target_url = "https://www.maspero.eg/stream/6"
    master_url = None

    print("🔍 Sniffing network traffic for MASTER playlist...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        def sniff(response):
            nonlocal master_url
            url = response.url

            # MASTER PLAYLIST RULES
            if url.endswith("master.m3u8"):
                print(f"🎯 MASTER PLAYLIST FOUND: {url}")
                master_url = url

            # Secondary detection (Maspero sometimes uses variant naming)
            elif ".m3u8" in url and "master" in url:
                print(f"🎯 MASTER PLAYLIST (variant) FOUND: {url}")
                master_url = url

        page.on("response", sniff)

        try:
            page.goto(target_url, timeout=45000, wait_until="networkidle")
            page.wait_for_timeout(5000)
        except Exception as e:
            print(f"⚠️ Page load issue: {e}")

        browser.close()

    return master_url


def create_m3u(stream_url):
    """
    Writes Smart IPTV-compatible M3U
    """

    if not stream_url:
        print("❌ No master playlist found. Cannot create valid M3U.")
        return False

    cleaned = stream_url.replace("\\", "")

    m3u = (
        "#EXTM3U\n"
        "#EXTINF:-1 tvg-name='Maspero Zaman' tvg-id='maspero.zaman' "
        "group-title='Egypt' tvg-logo='https://s2.dmcdn.net/y/3ElO1gAN-BkcNTD7'\n"
        f"{cleaned}\n"
    )

    try:
        with open("maspero.m3u", "w", encoding="utf-8") as f:
            f.write(m3u)
        print("✅ maspero.m3u updated with MASTER playlist.")
        return True
    except Exception as e:
        print(f"❌ Error writing file: {e}")
        return False


if __name__ == "__main__":
    url = extract_master_playlist()
    create_m3u(url)
