import os
from datetime import datetime

def extract_stream_url():
    """Simulate opening the browser and capturing DevTools Network logs"""
    target_url = "https://maspero.eg"
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None

    captured_url = None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()

        def handle_response(response):
            nonlocal captured_url
            url = response.url
            if ".m3u8" in url and "sec2" in url:
                if not captured_url:
                    captured_url = url

        page.on("response", handle_response)

        try:
            page.goto(target_url, timeout=30000, wait_until="networkidle")
            page.wait_for_timeout(5000)
        except Exception:
            pass

        browser.close()

    return captured_url

def create_m3u(stream_url):
    """Update maspero.m3u with an explicit clean syntax format for Smart IPTV"""
    if not stream_url:
        # Fallback to the working master direct video link format if browser fails
        stream_url = "https://dailymotion.com"

    # Clean any encoded backslashes out of the URL string so it reads perfectly
    cleaned_url = stream_url.replace('\\', '')

    # Strict Smart IPTV single-quote syntax formatting
    m3u_content = (
        "#EXTM3U\n"
        "#EXTINF:-1 tvg-name='Maspero Zaman' tvg-id='maspero.zaman' group-title='Egypt' tvg-logo='https://dmcdn.net Zaman\n"
        f"{cleaned_url}\n"
    )

    try:
        with open('maspero.m3u', 'w', newline='\n', encoding='utf-8') as f:
            f.write(m3u_content)
        print("✅ maspero.m3u formatted cleanly for Smart IPTV.")
        return True
    except Exception as e:
        print(f"❌ Error writing file: {e}")
        return False

if __name__ == "__main__":
    url = extract_stream_url()
    create_m3u(url)
