import requests
from bs4 import BeautifulSoup
import re
import json
from datetime import datetime

def extract_stream_url():
    """Extract the current Maspero Zaman stream URL"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        }
        
        print("🔄 Fetching Maspero Zaman page...")
        response = requests.get('https://www.maspero.eg/stream/6', headers=headers, timeout=15)
        response.raise_for_status()
        
        print(f"✅ Successfully fetched page ({len(response.text)} bytes)")
        
        # Try multiple patterns to find the stream URL
        patterns = [
            r'https://[^\s"\'<>]+\.m3u8[^\s"\'<>]*',  # General m3u8 pattern
            r'"src"\s*:\s*"(https://[^"]+\.m3u8[^"]*)"',  # JSON format
            r'src=["\']([^"\']+\.m3u8[^"\']*)["\']',  # HTML attribute
        ]
        
        stream_url = None
        for pattern in patterns:
            matches = re.findall(pattern, response.text)
            if matches:
                stream_url = matches[0]
                print(f"✅ Found stream URL with pattern: {pattern[:50]}...")
                break
        
        if not stream_url:
            print("⚠️  No m3u8 URL found in page content")
            print("📝 Trying alternative method...")
            
            # Try to find Dailymotion video ID and construct URL
            video_id_match = re.search(r'x[a-z0-9]+', response.text)
            if video_id_match:
                video_id = video_id_match.group(0)
                print(f"📹 Found video ID: {video_id}")
                # This might require API call
        
        if stream_url:
            print(f"✅ Stream URL found: {stream_url[:100]}...")
            return stream_url
        else:
            print("❌ No stream URL found")
            return None
            
    except requests.exceptions.RequestException as e:
        print(f"❌ Network Error: {e}")
        return None
    except Exception as e:
        print(f"❌ Error: {e}")
        return None

def create_m3u(stream_url):
    """Create M3U playlist with the stream URL"""
    if not stream_url:
        print("❌ No stream URL provided")
        # Use fallback with current timestamp to help debugging
        fallback_url = "https://www.maspero.eg/stream/6"
        print(f"⚠️  Using fallback website URL: {fallback_url}")
        stream_url = fallback_url
    
    m3u_content = f"""#EXTM3U
#EXTINF:-1 tvg-name="Maspero Zaman" tvg-id="maspero.zaman" group-title="Egypt" tvg-logo="https://s2.dmcdn.net/y/3ElO1gAN-BkcNTD7",Maspero Zaman
{stream_url}
"""
    
    try:
        with open('maspero.m3u', 'w') as f:
            f.write(m3u_content)
        
        print(f"✅ M3U file updated successfully")
        print(f"📅 Updated at: {datetime.now()}")
        print(f"🔗 Stream URL: {stream_url[:100]}...")
        return True
    except Exception as e:
        print(f"❌ Error writing M3U file: {e}")
        return False

if __name__ == "__main__":
    print("=" * 60)
    print("🔄 Starting Maspero Zaman URL extraction...")
    print("=" * 60)
    url = extract_stream_url()
    create_m3u(url)
    print("=" * 60)
    print("✅ Process completed!")
    print("=" * 60)
