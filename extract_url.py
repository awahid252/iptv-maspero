import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime

def extract_stream_url():
    """Extract the current Maspero Zaman stream URL"""
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        # Fetch the Maspero Zaman specific page
        response = requests.get('https://maspero.eg', headers=headers, timeout=10)
        response.raise_for_status()
        print(f"✅ Successfully fetched page from https://maspero.eg")

        # Look for m3u8 URL in the HTML
        m3u_pattern = r'https://[^\s"\'<>]+\.m3u8[^\s"\'<>]*'
        matches = re.findall(m3u_pattern, response.text)
        
        if matches:
            # Get the first match (usually the highest quality)
            stream_url = matches[0]
            print(f"✅ Found stream URL: {stream_url}")
            return stream_url
        else:
            print("❌ No stream URL found in page")
            print(f"Response length: {len(response.text)} characters")
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
        print("❌ No stream URL provided, using fallback")
        # Fallback URL
        stream_url = "https://dmcdn.net"

    m3u_content = f"""#EXTM3U
#EXTINF:-1 tvg-name="Maspero Zaman" tvg-id="maspero.zaman" group-title="Egypt" tvg-logo="https://dmcdn.net",Maspero Zaman
{stream_url}
"""

    try:
        with open('maspero.m3u', 'w') as f:
            f.write(m3u_content)
        print(f"✅ M3U file updated successfully")
        print(f"📅 Updated at: {datetime.now()}")
        print(f"🔗 Stream URL: {stream_url[:80]}...")
        return True
    except Exception as e:
        print(f"❌ Error writing M3U file: {e}")
        return False

if __name__ == "__main__":
    print("🔄 Starting Maspero Zaman URL extraction...")
    url = extract_stream_url()
    create_m3u(url)
    print("✅ Process completed!")
