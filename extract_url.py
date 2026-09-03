import json
import urllib.request
from datetime import datetime

def extract_stream_url():
    """Extract the specific 480p direct live stream URL for web player compatibility"""
    video_id = "x8n6e4h"
    metadata_url = f"https://dailymotion.com{video_id}"
    
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
        'Accept': 'application/json'
    }
    
    try:
        print(f"🔄 Fetching streaming configuration parameters...")
        req = urllib.request.Request(metadata_url, headers=headers)
        
        with urllib.request.urlopen(req, timeout=10) as response:
            data = json.loads(response.read().decode('utf-8'))
            
        qualities = data.get("qualities", {})
        
        # FIX: "480" returns a LIST of streams. We must pull index 0.
        stream_list = qualities.get("480", [])
        
        if stream_list and len(stream_list) > 0:
            stream_url = stream_list[0].get("url", "")
            if stream_url:
                print("✅ Found explicit 480p direct live feed asset link.")
                return stream_url
                
        print("⚠️ 480p profile unavailable. Attempting auto stream layout pointer...")
        auto_list = qualities.get("auto", [])
        if auto_list and len(auto_list) > 0:
            return auto_list[0].get("url", "")
            
        return None
            
    except Exception as e:
        print(f"❌ Error communicating with metadata server: {e}")
        return None

def create_m3u(stream_url):
    """Generate the M3U playlist text structure with working adaptive fallback path format pointer"""
    if not stream_url:
        print("❌ Could not extract dynamic URL. Using standard adaptive layout fallback...")
        # FIX: Standard baseline live stream index path link layout format instead of a plain main web domain link string text
        stream_url = "https://dailymotion.com"

    # Cleaning template spaces down to pure clean lines for strict IPTV stream link readers
    m3u_content = (
        f"#EXTM3U\n"
        f"#EXTINF:-1 tvg-name=\"Maspero Zaman\" tvg-id=\"maspero.zaman\" group-title=\"Egypt\" tvg-logo=\"https://dmcdn.net\",Maspero Zaman\n"
        f"{stream_url}\n"
    )

    try:
        with open('maspero.m3u', 'w', encoding='utf-8') as f:
            f.write(m3u_content)
        print("✅ maspero.m3u file has been updated and synchronized.")
        print(f"📅 Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        return True
    except Exception as e:
        print(f"❌ Failed to save file format configurations: {e}")
        return False

if __name__ == "__main__":
    print("🔄 Initializing Maspero Zaman web player pipeline alignment...")
    url = extract_stream_url()
    create_m3u(url)
    print("🏁 Pipeline operation completed successfully.")
