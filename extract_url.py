import os
import re
from playwright.sync_api import sync_playwright

# ---------------------------------------------------------------------------
# Where maspero_master.m3u8 will be publicly reachable.
# Inside GitHub Actions, GITHUB_REPOSITORY ("user/repo") is set automatically,
# so the URL is built for you. Override with the MASTER_PUBLIC_URL env var if
# you host the files elsewhere (e.g. GitHub Pages).
# ---------------------------------------------------------------------------
BRANCH = os.environ.get("GITHUB_REF_NAME", "main")
REPO = os.environ.get("GITHUB_REPOSITORY", "YOUR_USER/YOUR_REPO")
MASTER_PUBLIC_URL = os.environ.get(
    "MASTER_PUBLIC_URL",
    f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/maspero_master.m3u8",
)


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
            if ".m3u8" in url and url not in m3u8_urls:
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
    # STRICT FILTERING — only real audio/video streams
    video_streams = [u for u in urls if "live-h264-" in u.lower()]
    audio_streams = [u for u in urls if "live-aac-" in u.lower()]

    if not video_streams:
        print("❌ No video streams found.")
        return None, None
    if not audio_streams:
        print("❌ No audio streams found.")
        return None, None

    # Extract numeric quality (240, 480, 64, 128)
    def extract_number(url):
        nums = re.findall(r"(\d+)", url)
        return max([int(n) for n in nums]) if nums else 0

    best_video = sorted(video_streams, key=extract_number, reverse=True)[0]
    best_audio = sorted(audio_streams, key=extract_number, reverse=True)[0]

    print(f"🎥 Best video stream: {best_video}")
    print(f"🔊 Best audio stream: {best_audio}")

    return best_video, best_audio


def create_playlists(video_url, audio_url):
    # 1) HLS master playlist (combined audio + video) -> .m3u8
    master = (
        "#EXTM3U\n"
        "#EXT-X-VERSION:4\n"
        "#EXT-X-INDEPENDENT-SEGMENTS\n"
        '#EXT-X-MEDIA:TYPE=AUDIO,GROUP-ID="audio",NAME="AAC",LANGUAGE="ar",'
        f'DEFAULT=YES,AUTOSELECT=YES,URI="{audio_url}"\n'
        '#EXT-X-STREAM-INF:BANDWIDTH=1500000,CODECS="avc1.4d401f,mp4a.40.2",AUDIO="audio"\n'
        f"{video_url}\n"
    )

    # 2) SmartIPTV channel list -> .m3u (EXTINF entries only, no HLS tags)
    channel_list = (
        "#EXTM3U\n"
        '#EXTINF:-1 tvg-id="maspero" tvg-name="Maspero" group-title="Egypt",Maspero (Combined)\n'
        f"{MASTER_PUBLIC_URL}\n"
        '#EXTINF:-1 tvg-id="maspero-video" group-title="Egypt",Maspero (Video only)\n'
        f"{video_url}\n"
        '#EXTINF:-1 tvg-id="maspero-audio" group-title="Egypt",Maspero (Audio only)\n'
        f"{audio_url}\n"
    )

    try:
        with open("maspero_master.m3u8", "w", encoding="utf-8", newline="\n") as f:
            f.write(master)
        with open("maspero.m3u", "w", encoding="utf-8", newline="\n") as f:
            f.write(channel_list)
        print("✅ maspero_master.m3u8 (combined HLS) created.")
        print("✅ maspero.m3u (SmartIPTV channel list) created.")
    except Exception as e:
        print(f"❌ Error writing playlists: {e}")


if __name__ == "__main__":
    urls = extract_streams()
    video, audio = select_best_streams(urls)

    if video and audio:
        create_playlists(video, audio)
