#!/usr/bin/env python3
# extract_url.py - aggressive playlist sniffer + extractor with debug output

import re
import sys
import time
import urllib.request
from urllib.parse import urljoin
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

TARGET_PAGE = "https://www.maspero.eg/stream/6"
OUTPUT_FILE = "maspero.m3u"
HEADLESS = True   # set to False to see the browser window for debugging
WAIT_AFTER_LOAD_MS = 4000

def download_text(url, timeout=15):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[download_text] failed to GET {url}: {e}")
        return None

def sniff_master_aggressive():
    """
    Use Playwright to collect any .m3u8 responses and then scan page content for m3u8 strings.
    Returns a list of candidate m3u8 URLs (may be empty).
    """
    candidates = set()

    print("[sniff] starting Playwright...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=HEADLESS)
            ctx = browser.new_context()
            page = ctx.new_page()

            def on_response(resp):
                try:
                    url = resp.url
                except Exception:
                    return
                # capture any .m3u8 response URL
                if ".m3u8" in url.lower():
                    print(f"[network] .m3u8 seen in response URL: {url}")
                    candidates.add(url)
            page.on("response", on_response)

            try:
                print(f"[sniff] navigating to {TARGET_PAGE} ...")
                page.goto(TARGET_PAGE, timeout=45000, wait_until="networkidle")
                # wait a bit for XHRs / players to finish loading
                page.wait_for_timeout(WAIT_AFTER_LOAD_MS)
            except PWTimeout as e:
                print(f"[sniff] Playwright timeout while loading page: {e}")
            except Exception as e:
                print(f"[sniff] Playwright navigation error: {e}")

            # also inspect the page content (HTML / inlined JS) for .m3u8 occurrences
            try:
                content = page.content()
                found = set(re.findall(r'https?://[^\'"\s>]+\.m3u8(?:\?[^\'"\s>]*)?', content, flags=re.IGNORECASE))
                if found:
                    print(f"[page-content] found {len(found)} .m3u8 URLs in page HTML/JS")
                    for u in found:
                        candidates.add(u)
                # also look for relative m3u8 references
                rel_found = set(re.findall(r'["\']([^"\']+\.m3u8(?:\?[^"\']*)?)["\']', content, flags=re.IGNORECASE))
                for r in rel_found:
                    # make absolute relative to page url
                    full = urljoin(page.url, r)
                    candidates.add(full)
            except Exception as e:
                print(f"[sniff] page.content() error: {e}")

            # last attempt: try evaluating common player variables (best-effort)
            try:
                # common keys: src, sources, playlistUrl, playlist, hlsUrl, url
                js_snippets = [
                    "(() => { try { return window.player && window.player.src || window.player && (window.player.currentSrc || window.player.config && window.player.config['file']); } catch(e) { return null } })()",
                    "(() => { try { return document.querySelector('video') && (document.querySelector('video').src || document.querySelector('video').getAttribute('src')); } catch(e) { return null } })()",
                ]
                for s in js_snippets:
                    try:
                        res = page.evaluate(s)
                        if isinstance(res, str) and ".m3u8" in res.lower():
                            full = urljoin(page.url, res)
                            print(f"[eval] found m3u8 via page.evaluate: {full}")
                            candidates.add(full)
                    except Exception:
                        pass
            except Exception:
                pass

            browser.close()
    except Exception as e:
        print(f"[sniff] could not start Playwright: {e}")
        print("[sniff] Make sure 'playwright' is installed and you ran 'python -m playwright install' to install browsers.")
        # return what we have so far (likely empty)
        return list(candidates)

    return list(candidates)

def scan_page_html_for_m3u8(url):
    """
    Directly GET the page HTML and search for m3u8 references (HTTP(S) absolute and relative).
    """
    print(f"[scan] fetching page HTML via urllib: {url}")
    text = download_text(url)
    found = set()
    if not text:
        print("[scan] no HTML fetched")
        return []
    # absolute http(s) .m3u8
    for u in re.findall(r'https?://[^\'"\s>]+\.m3u8(?:\?[^\'"\s>]*)?', text, flags=re.IGNORECASE):
        found.add(u)
    # relative .m3u8 references
    for r in re.findall(r'["\']([^"\']+\.m3u8(?:\?[^"\']*)?)["\']', text, flags=re.IGNORECASE):
        full = urljoin(url, r)
        found.add(full)
    print(f"[scan] found {len(found)} candidate m3u8 URLs in page HTML")
    return list(found)

def print_candidates(cands):
    if not cands:
        print(">>> No candidates discovered.")
        return
    print("\n>>> Candidate m3u8 URLs discovered:")
    for i, u in enumerate(cands, 1):
        print(f"  {i}. {u}")

def main():
    print("extract_url.py - aggressive sniffer")
    # 1) Try Playwright sniffing
    candidates = sniff_master_aggressive()
    print_candidates(candidates)

    # 2) If none found, try direct HTML scan
    if not candidates:
        html_candidates = scan_page_html_for_m3u8(TARGET_PAGE)
        for u in html_candidates:
            if u not in candidates:
                candidates.append(u)
        print_candidates(candidates)

    # 3) If still none found, provide guidance
    if not candidates:
        print("\nNo .m3u8 URLs were discovered automatically.")
        print("Next steps you can try manually:")
        print("  - Open the target page in a desktop browser (Chrome/Edge/Firefox).")
        print("  - Open DevTools -> Network tab, then reload the page and filter for '.m3u8' requests.")
        print("  - If you find .m3u8 requests, copy the exact URL (including query string) and paste it here.")
        print("\nCommon causes for not seeing .m3u8 from Playwright:")
        print("  - Playwright browsers not installed: run 'python -m playwright install' once after pip installing playwright.")
        print("  - The site requires special headers, cookies, or authentication.")
        print("  - The player constructs the URL purely inside WebAssembly or obfuscated JS after user interaction.")
        print("  - Site blocks headless browsers — try setting HEADLESS=False in the script to observe the browser.")
        return

    # 4) Basic validation: try downloading each candidate and check for #EXT-X-STREAM-INF or #EXTINF
    valid = []
    for u in candidates:
        print(f"\n[validate] trying {u} ...")
        txt = download_text(u)
        if not txt:
            print("  failed to download or empty response.")
            continue
        if "#EXTINF" in txt:
            print("  looks like a media playlist (#EXTINF present).")
            valid.append(('media', u))
        elif "#EXT-X-STREAM-INF" in txt:
            print("  looks like a master playlist (#EXT-X-STREAM-INF present).")
            valid.append(('master', u))
        else:
            # maybe it's indirectly referenced or requires special headers
            print("  downloaded content does not look like an HLS playlist (no EXTINF or EXT-X-STREAM-INF).")
            # still include it so we can inspect manually
            valid.append(('unknown', u))
    if not valid:
        print("\nNo valid-looking playlists among candidates.")
        return

    print("\nDiscovered valid candidates (type, url):")
    for t, u in valid:
        print(f"  - {t}: {u}")

    # optional: write the first media URL (or master) to maspero.m3u for convenience
    chosen = None
    for t, u in valid:
        if t == 'media':
            chosen = u
            break
    if not chosen:
        # pick the first master or unknown as last resort
        chosen = valid[0][1]
    print(f"\nWriting chosen URL to {OUTPUT_FILE}: {chosen}")
    with open(OUTPUT_FILE, "w", encoding="utf-8", newline="\n") as f:
        f.write("#EXTM3U\n")
        f.write(f"{chosen}\n")
    print("Done. If this plays audio-only, paste the chosen URL here so I can inspect the playlist contents.")
    print("If you still see 'No master playlist found' when running the older script, try:")
    print("  - pip install playwright")
    print("  - python -m playwright install")
    print("  - set HEADLESS=False in the script to see the browser (helps when site blocks headless).")

if __name__ == "__main__":
    main()
