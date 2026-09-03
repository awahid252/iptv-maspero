import json
import re
from datetime import datetime
import urllib.request

def extract_stream_url():
    """Extract the adaptive live stream URL from Dailymotion's metadata backend"""
    video_id = "x8n6e4h"
    metadata_url = f"https://dailymotion.com{video_id}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }
    
    try:
        print(f"🔄 Requesting metadata directly from Dailymotion for ID: {video_id}")
        req = urllib.request.Request(metadata_url, headers=headers)
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        # Dailymotion packs its live streams inside the qualities dictionary
        qualities = data.get("qualities", {})
        
        # 'auto' contains the master adaptive HLS stream layout (.m3u8)
        auto_stream = qualities.get("auto", [{}])[0].get("url", "")
        
        if auto_stream:
            print("✅ Successfully found adaptive master stream manifest URL.")
            return auto_stream
        else:
            print("❌ Found metadata structure, but 'auto' stream URL was missing.")
            return None
            
    except Exception as e:
        print(f"❌ Error communicating with Dailymotion API: {e}")
        return None

def create_m3u(stream_url):
    """Create a pristine M3U playlist file using the retrieved stream link"""
    if not stream_url:
        print("❌ Stream URL is missing. Falling back to static adaptive layout structure...")
        # A resilient direct fallback link that points to the adaptive master layer
        stream_url = "https://dailymotion.com"

    # Properly cleaning and formatting text spacing for strict IPTV client parsing
    m3u_content = (
        f"#EXTM3U\n"
        f"#EXTINF:-1 tvg-name=\"Maspero Zaman\" tvg-id=\"maspero.zaman\" group-title=\"Egypt\" tvg-logo=\"https://s2.dmcdn.net/y/3ElO1gAN-BkcNTD7\",Maspero Zaman\n"
        f"{stream_url}\n"
    )

    try:
        with open('maspero.m3u', 'w', encoding='utf-8') as f:
            f.write(m3u_content)
        print("✅ maspero.m3u file has been generated and rewritten successfully.")
        print(f"📅 Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return True
    except Exception as e:
        print(f"❌ Failed to write file to disk: {e}")
        return False

if __name__ == "__main__":
    print("🔄 Initializing Maspero Zaman stream pipeline...")
    current_url = extract_stream_url()
    create_m3u(current_url)
    print("🏁 Pipeline operation completed.")
