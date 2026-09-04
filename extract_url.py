import os
import re
from datetime import datetime

def extract_stream_url():
    """
    Step 1: Open the website
    Step 2 & 3: Simulate accessing DevTools & Network tab
    Step 4, 5 & 6: Inspect Fetch/XHR network logs for request URLs ending in m3u8
    Step 7: Copy the full URL string
    """
    target_url = "https://www.maspero.eg/stream/6"
    captured_url = None

    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("❌ Playwright library not found in the running environment.")
        return None

    print(f"🔄 Opening browser and starting DevTools Network traffic inspection...")
    
    with sync_playwright() as p:
        # Launch a headless background browser instance
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
        page = context.new_page()

        # Event listener matching Step 4, 5 & 6 (Sniffing Fetch/XHR network links)
        def inspect_network_traffic(response):
            nonlocal captured_url
            url = response.url
            
            # Look for the streaming playlist endpoints ending with m3u8
            if ".m3u8" in url and "sec2" in url:
                if not captured_url:  # Capture the first live stream manifest found
                    print(f"🎯 DevTools Network Match Found: {url[:80]}...")
                    captured_url = url

        # Attach the network sniffing tool to the page
        page.on("response", inspect_network_traffic)

        try:
            # Step 1: Open the page and wait for background elements to process
            page.goto(target_url, timeout=45000, wait_until="networkidle")
            # Step 7: Give the player engine 5 extra seconds to execute its dynamic network handshakes
            page.wait_for_timeout(5000)
        except Exception as e:
            print(f"⚠️ Page load timed out, checking captured logs regardless: {e}")

        browser.close()

    return captured_url

def create_m3u(stream_url):
    """
    Step 8: Update maspero.m3u with strict formatting for Smart IPTV
    """
    if not stream_url:
        print("❌ Failed to sniff dynamic token URL from DevTools. Dropping down to baseline live stream pointer link...")
        stream_url = "https://dailymotion.com"

    # Clean any encoded text backslashes out of the URL string so it reads perfectly
    cleaned_url = stream_url.replace('\\', '')

    # Smart IPTV compatible layout using single quotes, proper spacing, and fixed logos
    m3u_content = (
        "#EXTM3U\n"
        "#EXTINF:-1 tvg-name='Maspero Zaman' tvg-id='maspero.zaman' group-title='Egypt' tvg-logo='https://dmcdn.net Zaman\n"
        f"{cleaned_url}\n"
    )

    try:
        with open('maspero.m3u', 'w', newline='\n', encoding='utf-8') as f:
            f.write(m3u_content)
        print("✅ maspero.m3u file successfully updated and synchronized for Smart IPTV.")
        return True
    except Exception as e:
        print(f"❌ Error writing file to disk: {e}")
        return False

if __name__ == "__main__":
    url = extract_stream_url()
    create_m3u(url)
