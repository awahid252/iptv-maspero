import requests
from bs4 import BeautifulSoup
import re
from datetime import datetime

MASPERO_URL = "https://www.maspero.eg/stream/6"
DM_API = "https://www.dailymotion.com/player/metadata/video/{}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}

def fetch_page(url):
    """Fetch a webpage with proper headers."""
    try:
        response = requests.get(url, headers=HEADERS, timeout=15)
        response.raise_for_status()
        return response.text
    except Exception as e:
        print(f"❌ Error fetching {url}: {e}")
        return None


def extract_m3u8_from_html(html):
    """Extract .m3u8 URLs using multiple regex patterns."""
    patterns = [
        r'https://[^\s"\'<>]+\.m3u8[^\s"\'<>]*',
        r'"src"\s*:\s*"(https://[^"]+\.m3u8[^"]*)"',
        r'src=["\']([^"\']+\.m3u8[^"\']*)["\']',
    ]

    for pattern in patterns:
        matches = re.findall(pattern, html)
        if matches:
            print(f"🔍 Found stream using pattern: {pattern[:40]}")
            return matches[0]

    return None


def extract_dailymotion_id(html):
    """Extract Dailymotion video ID (starts with x...)."""
    match = re.search(r'x[a-z0-9]{6,}', html)
    return match.group(0) if match else None


def fetch_dailymotion_stream(video_id):
    """Fetch the real .m3u8 stream from Dailymotion metadata."""
    try:
        metadata_url = DM_API.format(video_id)
        print(f"🔄 Fetching Dailymotion metadata: {metadata_url}")
        data = requests.get(metadata_url, headers=HEADERS, timeout=15).json()

        # Dailymotion stores streams under "qualities"
        qualities = data.get("qualities", {})
        if "auto" in qualities:
            stream = qualities["auto"][0]["url"]
            print("🎥 Dailymotion stream extracted successfully")
            return stream

        print("⚠️ No auto-quality stream found in metadata")
        return None

    except Exception as e:
        print(f"❌ Error fetching Dailymotion metadata: {e}")
        return None


def extract_stream_url():
    """Main extraction logic."""
    print("🔄 Fetching Maspero Zaman page...")
    html = fetch_page(MASPERO_URL)
    if not html:
        return None

    print("🔍 Searching for direct .m3u8 stream...")
    stream_url = extract_m3u8_from_html(html)

    if stream_url:
        print(f"✅ Direct stream found: {stream_url}")
        return stream_url

    print("⚠️ No direct stream found — trying Dailymotion fallback...")
    video_id = extract_dailymotion_id(html)

    if video_id:
        print(f"📹 Dailymotion video ID found: {video_id}")
        return fetch_dailymotion_stream(video_id)

    print("❌ No stream found at all")
    return None


def create_m3u(stream_url):
    """Write the M3U playlist file."""
    if not stream_url:
        print("⚠️ No stream URL found — using fallback Maspero page")
        stream_url = MASPERO_URL

    m3u_content = f"""#EXTM3U
#EXTINF:-1 tvg-name="Maspero Zaman" tvg-id="maspero.zaman" group-title="Egypt" tvg-logo="https://s2.dmcdn.net/y/3ElO1gAN-BkcNTD7",Maspero Zaman
{stream_url}
"""

    try:
        with open("maspero.m3u", "w", encoding="utf-8") as f:
            f.write(m3u_content)

        print("✅ M3U file updated successfully")
        print(f"📅 Updated at: {datetime.now()}")
        print(f"🔗 Stream URL: {stream_url}")
        return True

    except Exception as e:
        print(f"❌ Error writing M3U file: {e}")
        return False


if __name__ == "__main__":
    print("=" * 60)
    print("🔄 Starting Maspero Zaman stream extraction...")
    print("=" * 60)

    url = extract_stream_url()
    create_m3u(url)

    print("=" * 60)
    print("✅ Process completed!")
    print("=" * 60)
