import os
import re
from datetime import datetime

def extract_stream_url():
    target_url = "https://www.maspero.eg/stream/6"
    m3u8_urls = []

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ Playwright library not found.")
        return None

    print("🔄 Inspecting network traffic for m3u8 playlists...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64)"
        )
        page = context.new_page()

        def inspect_network_traffic(response):
            url = response.url

            if ".m3u8" in url:
                print(f"📡 Found playlist: {url}")
                m3u8_urls.append(url)

        page.on("response", inspect_network_traffic)

        try:
            page.goto(target_url, timeout=45000, wait_until="networkidle")
            page.wait_for_timeout(5000)
        except Exception as e:
            print(f"⚠️ Timeout or load issue: {e}")

        browser.close()

    if not m3u8_urls:
        print("❌ No m3u8 URLs found.")
        return None

    # ---- FILTERING LOGIC ----
    # Prefer master playlists over audio/video-only ones
    def is_master(url):
        url_lower = url.lower()
        return (
            "audio" not in url_lower and
            "video" not in url_lower and
            "ad" not in url_lower and
            "chunk" not in url_lower
        )

    master_candidates = [u for u in m3u8_urls if is_master(u)]

    if master_candidates:
        best = master_candidates[-1]  # last one is usually the real master
        print(f"🎯 Selected MASTER playlist: {best}")
        return best

    # fallback: return longest URL (usually master)
    best = sorted(m3u8_urls, key=len, reverse=True)[0]
    print(f"🎯 Fallback selected playlist: {best}")
    return best


def create_m3u(stream_url):
    if not stream_url:
        print("❌ No stream URL found. Using fallback.")
        stream_url = "https://dailymotion.com"

    cleaned_url = stream_url.replace('\\', '')

    m3u_content = (
        "#EXTM3U\n"
        "#EXTINF:-1 tvg-name='Maspero Zaman' tvg-id='maspero.zaman' "
        "group-title='Egypt' tvg-logo='https://dmcdn.net Zaman'\n"
        f"{cleaned_url}\n"
    )

    try:
        with open('maspero.m3u', 'w', newline='\n', encoding='utf-8') as f:
            f.write(m3u_content)
        print("✅ maspero.m3u updated.")
        return True
    except Exception as e:
        print(f"❌ Error writing file: {e}")
        return False


if __name__ == "__main__":
    url = extract_stream_url()
    create_m3u(url)
