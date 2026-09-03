import os
import re
from datetime import datetime

# We use standard library code to avoid script errors if a library acts up
def extract_stream_url():
    """Simulate opening the browser and capturing DevTools Network logs"""
    target_url = "https://www.maspero.eg/stream/6"
    
    try:
        # We import playwright inside the function so it doesn't block loading
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ Playwright library is missing from the environment.")
        return None

    captured_url = None

    print(f"🔄 Opening browser DevTools simulation for: {target_url}")
    with sync_playwright() as p:
        # Launch a headless background browser instance
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        # Step 3 & 4: Monitor the Network log events for Fetch/XHR m3u8 targets
        def handle_response(response):
            nonlocal captured_url
            url = response.url
            # Filter for the specific live stream chunk playlists you saw in DevTools
            if ".m3u8" in url and "sec2" in url:
                if not captured_url:  # Keep the first match found
                    print(f"🎯 DevTools Network Match Found: {url[:80]}...")
                    captured_url = url

        # Attach our network traffic inspector listener
        page.on("response", handle_response)

        try:
            # Step 1: Navigate to the web page and wait up to 30 seconds for player traffic to load
            page.goto(target_url, timeout=30000, wait_until="networkidle")
            # Give the hidden video player 5 extra seconds to fire its background streams
            page.wait_for_timeout(5000)
        except Exception as e:
            print(f"⚠️ Page load took too long, checking if any URLs were captured anyway: {e}")

        browser.close()

    return captured_url

def create_m3u(stream_url):
    """Update maspero.m3u with the captured network stream url layout"""
    if not stream_url:
        print("❌ DevTools network sniff failed. Reverting to static live layout.")
        stream_url = "https://dailymotion.com"

    m3u_content = (
        f"#EXTM3U\n"
        f"#EXTINF:-1 tvg-name=\"Maspero Zaman\" tvg-id=\"maspero.zaman\" group-title=\"Egypt\" tvg-logo=\"https://dmcdn.net\",Maspero Zaman\n"
        f"{stream_url}\n"
    )

    try:
        with open('maspero.m3u', 'w', encoding='utf-8') as f:
            f.write(m3u_content)
        print("✅ maspero.m3u updated successfully with the active DevTools URL.")
        print(f"📅 Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return True
    except Exception as e:
        print(f"❌ Error writing M3U file layout properties: {e}")
        return False

if __name__ == "__main__":
    url = extract_stream_url()
    create_m3u(url)
