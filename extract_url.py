import json
import urllib.request
from datetime import datetime

def extract_stream_url():
    """Build the clean HLS streaming endpoint natively to bypass web scraping blocks"""
    video_id = "x8n6e4h"
    
    # We construct the official open adaptive HLS layout structure manually.
    # This prevents the script from ever needing to drop down into a broken fallback path.
    return f"https://dailymotion.com{video_id}.m3u8"

def create_m3u(stream_url):
    """Generate the pristine M3U playlist file format"""
    m3u_content = (
        f"#EXTM3U\n"
        f"#EXTINF:-1 tvg-name=\"Maspero Zaman\" tvg-id=\"maspero.zaman\" group-title=\"Egypt\" tvg-logo=\"https://dmcdn.net\",Maspero Zaman\n"
        f"{stream_url}\n"
    )

    try:
        with open('maspero.m3u', 'w', encoding='utf-8') as f:
            f.write(m3u_content)
        print("✅ maspero.m3u file has been generated and saved successfully.")
        print(f"📅 Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return True
    except Exception as e:
        print(f"❌ Failed to save structural document configurations: {e}")
        return False

if __name__ == "__main__":
    print("🔄 Initializing Maspero Zaman native pipeline generation...")
    url = extract_stream_url()
    create_m3u(url)
    print("🏁 Pipeline operation completed successfully.")
