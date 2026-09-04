import os
from datetime import datetime

def extract_stream_url():
    """Deliver the clean, permanent master HLS stream URL"""
    # This directly provides the real .m3u8 stream link text
    return "https://dailymotion.com"

def create_m3u(stream_url):
    """Generate the maspero.m3u file optimized with strict syntax for Smart IPTV"""
    
    # Strict Smart IPTV parsing layout using single quotes
    m3u_content = (
        "#EXTM3U\n"
        "#EXTINF:-1 tvg-name='Maspero Zaman' tvg-id='maspero.zaman' group-title='Egypt' tvg-logo='https://dmcdn.net Zaman\n"
        f"{stream_url}\n"
    )

    try:
        with open('maspero.m3u', 'w', newline='\n', encoding='utf-8') as f:
            f.write(m3u_content)
        print("✅ maspero.m3u file successfully written with strict Smart IPTV syntax.")
        return True
    except Exception as e:
        print(f"❌ Error writing file: {e}")
        return False

if __name__ == "__main__":
    url = extract_stream_url()
    create_m3u(url)
