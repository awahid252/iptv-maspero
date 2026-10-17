import re
import urllib.request
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright

TARGET_PAGE = "https://www.maspero.eg/stream/6"
OUTPUT_FILE = "maspero.m3u"

def sniff_master():
    master = None
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context()
        page = ctx.new_page()

        def on_response(resp):
            nonlocal master
            url = resp.url
            if master:
                return
            if url.endswith("master.m3u8") or (".m3u8" in url and "master" in url):
                master = url

        page.on("response", on_response)
        try:
            page.goto(TARGET_PAGE, timeout=45000, wait_until="networkidle")
            page.wait_for_timeout(4000)
        except Exception:
            pass
        browser.close()
    return master


def download_text(url, timeout=15):
    with urllib.request.urlopen(url, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="ignore")


def choose_variant(master_url):
    text = download_text(master_url)
    # find all EXT-X-STREAM-INF blocks and following URI
    pattern = re.compile(r'(#EXT-X-STREAM-INF:[^\n]*\n)([^\n]+)', re.IGNORECASE)
    candidates = []
    for header, uri in pattern.findall(text):
        codecs_match = re.search(r'CODECS="([^"]+)"', header)
        codecs = codecs_match.group(1) if codecs_match else ""
        # normalize
        codecs_lower = codecs.lower()
        has_video = ("avc1" in codecs_lower) or ("h264" in codecs_lower) or ("hev1" in codecs_lower) or ("h265" in codecs_lower)
        has_audio = ("mp4a" in codecs_lower) or ("aac" in codecs_lower) or ("ac-3" in codecs_lower) or ("ec-3" in codecs_lower)
        candidates.append((has_video, has_audio, uri.strip(), codecs))
    # prefer variants with both audio+video
    for hv, ha, uri, codecs in candidates:
        if hv and ha:
            return urljoin(master_url, uri)
    # If no combined variant found, but the master contains separate audio groups (EXT-X-MEDIA TYPE=AUDIO),
    # return the master itself so players that support alternate audio will fetch both video variants and audio playlists.
    if re.search(r"#EXT-X-MEDIA:.*TYPE=\s*?AUDIO", text, re.IGNORECASE):
        return master_url
    # fallback: no suitable variant discovered
    return None


def validate_variant(variant_url):
    try:
        txt = download_text(variant_url)
    except Exception:
        return False
    # a variant playlist typically contains segment lines (#EXTINF)
    if "#EXTINF" in txt and len(txt) > 200:
        return True
    # some master playlists with separate audio use EXT-X-MEDIA + EXT-X-STREAM-INF; accept these as valid master playlists
    if "#EXT-X-STREAM-INF" in txt and "#EXT-X-MEDIA" in txt:
        return True
    return False


def write_m3u(url):
    m3u = (
        "#EXTM3U\n"
        "#EXTINF:-1 tvg-name='Maspero Zaman' tvg-id='maspero.zaman' "
        "group-title='Egypt' tvg-logo='https://s2.dmcdn.net/y/3ElO1gAN-BkcNTD7'\n"
        f"{url}\n"
    )
    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write(m3u)


def main():
    master = sniff_master()
    if not master:
        print("No master playlist found.")
        return
    print("Master found:", master)
    variant = choose_variant(master)
    if not variant:
        print("No combined audio+video variant found in master and no alternate-audio groups detected.")
        return
    print("Chosen variant or master to use:", variant)
    if not validate_variant(variant):
        print("Variant/master validation failed (no segments or streams).")
        return
    write_m3u(variant)
    print("maspero.m3u written with validated variant/master.")


if __name__ == "__main__":
    main()
