import re
import urllib.request
from playwright.sync_api import sync_playwright


TARGET_PAGE = "https://www.maspero.eg/stream/6"
OUTPUT_FILE = "maspero.m3u"


def extract_master_playlist() -> str | None:
    """
    Open Maspero stream page, sniff ONLY master.m3u8 URLs.
    """

    master_url = None
    print("🔍 Sniffing network traffic for master playlist...")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context()
        page = context.new_page()

        def sniff(response):
            nonlocal master_url
            url = response.url

            # Strict master playlist detection
            if url.endswith("master.m3u8"):
                print(f"🎯 MASTER PLAYLIST FOUND: {url}")
                master_url = url

            # Fallback: any m3u8 with 'master' in name
            elif ".m3u8" in url and "master" in url and master_url is None:
                print(f"🎯 MASTER-LIKE PLAYLIST FOUND: {url}")
                master_url = url

        page.on("response", sniff)

        try:
            page.goto(TARGET_PAGE, timeout=45000, wait_until="networkidle")
            page.wait_for_timeout(5000)
        except Exception as e:
            print(f"⚠️ Page load issue: {e}")

        browser.close()

    if not master_url:
        print("❌ No master playlist URL captured.")
    return master_url


def playlist_has_audio_and_video(master_url: str) -> bool:
    """
    Download master.m3u8 and confirm it has both audio and video streams.
    """

    print("🔎 Validating master playlist for audio + video...")
    try:
        with urllib.request.urlopen(master_url, timeout=15) as resp:
            content = resp.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"⚠️ Error downloading master playlist: {e}")
        return False

    # Look for EXT-X-STREAM-INF lines with CODECS
    streams = re.findall(r"#EXT-X-STREAM-INF:.*CODECS=\"([^\"]+)\"", content)

    if not streams:
        print("❌ No EXT-X-STREAM-INF entries found.")
        return False

    has_video = any("avc1" in s or "h264" in s for s in streams)
    has_audio = any("mp4a" in s or "aac" in s for s in streams)

    print(f"   Streams found: {len(streams)} | video={has_video} audio={has_audio}")

    return has_video and has_audio


def create_m3u(stream_url: str) -> bool:
    """
    Write Smart IPTV-compatible M3U pointing to the validated master playlist.
    """

    cleaned = stream_url.replace("\\", "")

    m3u = (
        "#EXTM3U\n"
        "#EXTINF:-1 tvg-name='Maspero Zaman' tvg-id='maspero.zaman' "
        "group-title='Egypt' tvg-logo='https://s2.dmcdn.net/y/3ElO1gAN-BkcNTD7'\n"
        f"{cleaned}\n"
    )

    try:
        with open(OUTPUT_FILE, "w", encoding="utf-8", newline="\n") as f:
            f.write(m3u)
        print(f"✅ {OUTPUT_FILE} updated with validated MASTER playlist.")
        return True
    except Exception as e:
        print(f"❌ Error writing file: {e}")
        return False


def main():
    master_url = extract_master_playlist()
    if not master_url:
        return

    if not playlist_has_audio_and_video(master_url):
        print("❌ Master playlist does not expose both audio and video. Aborting.")
        return

    create_m3u(master_url)


if __name__ == "__main__":
    main()
