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
    # fallback: if master contains EXT-X-MEDIA TYPE=AUDIO and no combined variant, return None
    return None

def validate_variant(variant_url):
    try:
        txt = download_text(variant_url)
    except Exception:
        return False
    # simple check: variant should contain segment lines (#EXTINF) and not be empty
    if "#EXTINF" in txt and len(txt) > 200:
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
        print("No combined audio+video variant found in master. Smart IPTV likely cannot use separate audio groups.")
        return
    print("Chosen variant:", variant)
    if not validate_variant(variant):
        print("Variant validation failed (no segments).")
        return
    write_m3u(variant)
    print("maspero.m3u written with validated variant.")

if __name__ == "__main__":
    main()
