import re
from playwright.sync_api import sync_playwright

def extract_streams():
    target_url = "https://www.maspero.eg/stream/6"
    m3u8_urls = []

    print("🔄 Inspecting network traffic for m3u8 playlists...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        def sniff(response):
            url = response.url
            if ".m3u8" in url:
                print(f"📡 Found playlist: {url}")
                m3u8_urls.append(url)

        page.on("response", sniff)

        try:
            page.goto(target_url, timeout=45000, wait_until="networkidle")
            page.wait_for_timeout(5000)
        except Exception as e:
            print(f"⚠️ Page load issue: {e}")

        browser.close()

    return m3u8_urls


def select_best_streams(urls):
    video_streams = []
    audio_streams = []

    # Categorize streams
    for u in urls:
        if "h264" in u.lower():
            video_streams.append(u)
        if "aac" in u.lower():
            audio_streams.append(u)

    if not video_streams or not audio_streams:
        print("❌ Could not find both audio and video streams.")
        return None, None

    # Extract resolution or bitrate numbers
    def extract_number(url):
        nums = re.findall(r"(\d+)", url)
        return max([int(n) for n in nums]) if nums else 0

    # Highest resolution video
    best_video = sorted(video_streams, key=extract_number, reverse=True)[0]

    # Highest bitrate audio
    best_audio = sorted(audio_streams, key=extract_number, reverse=True)[0]

    print(f"🎥 Best video stream: {best_video}")
    print(f"🔊 Best audio stream: {best_audio}")

    return best_video, best_audio


def create_master_playlist(video_url, audio_url):
    master = f"""#EXTM3U

#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="AAC",DEFAULT=YES,AUTOSELECT=YES,URI="{audio_url}"

#EXT-X-STREAM-INF:BANDWIDTH=1500000,CODECS="avc1.4d401f,mp4a.40.2",AUDIO="audio"
{video_url}
"""

    try:
        with open("maspero.m3u", "w", encoding="utf-8") as f:
            f.write(master)
        print("✅ maspero.m3u created with combined audio + video.")
    except Exception as e:
        print(f"❌ Error writing playlist: {e}")


if __name__ == "__main__":
    urls = extract_streams()
    video, audio = select_best_streams(urls)

    if video and audio:
        create_master_playlist(video, audio)
