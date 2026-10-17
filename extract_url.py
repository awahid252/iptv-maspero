#!/usr/bin/env python3
"""
extract_url.py

- Finds HLS master/media playlists on the target page (maspero).
- Prefers video media playlists when writing maspero.m3u.
- Optional: --restream to automatically run ffmpeg to merge video+audio into an HLS output.
"""
import re
import os
import sys
import argparse
import shlex
import subprocess
from urllib.parse import urljoin
import urllib.request
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

TARGET_PAGE = "https://www.maspero.eg/stream/6"
DEFAULT_OUTPUT_FILE = "maspero.m3u"
DEFAULT_OUTPUT_DIR = "hls_out"

HEADLESS = True
WAIT_AFTER_LOAD_MS = 4000

def download_text(url, timeout=15):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception as e:
        print(f"[download_text] failed to GET {url}: {e}")
        return None

def sniff_master_aggressive(target_page):
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
                if ".m3u8" in url.lower():
                    print(f"[network] .m3u8 seen in response URL: {url}")
                    candidates.add(url)
            page.on("response", on_response)

            try:
                print(f"[sniff] navigating to {target_page} ...")
                page.goto(target_page, timeout=45000, wait_until="networkidle")
                page.wait_for_timeout(WAIT_AFTER_LOAD_MS)
            except PWTimeout as e:
                print(f"[sniff] Playwright timeout while loading page: {e}")
            except Exception as e:
                print(f"[sniff] Playwright navigation error: {e}")

            try:
                content = page.content()
                found = set(re.findall(r'https?://[^\'"\s>]+\.m3u8(?:\?[^\'"\s>]*)?', content, flags=re.IGNORECASE))
                for u in found:
                    candidates.add(u)
                rel_found = set(re.findall(r'["\']([^"\']+\.m3u8(?:\?[^"\']*)?)["\']', content, flags=re.IGNORECASE))
                for r in rel_found:
                    full = urljoin(page.url, r)
                    candidates.add(full)
            except Exception as e:
                print(f"[sniff] page.content() error: {e}")

            try:
                js_snippets = [
                    "(() => { try { return window.player && window.player.src || (window.player && (window.player.currentSrc || (window.player.config && window.player.config['file']))) } catch(e) { return null } })()",
                    "(() => { try { const v = document.querySelector('video'); return v && (v.src || v.getAttribute('src')); } catch(e) { return null } })()",
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
        return list(candidates)
    return list(candidates)

def scan_page_html_for_m3u8(url):
    print(f"[scan] fetching page HTML via urllib: {url}")
    text = download_text(url)
    found = set()
    if not text:
        print("[scan] no HTML fetched")
        return []
    for u in re.findall(r'https?://[^\'"\s>]+\.m3u8(?:\?[^\'"\s>]*)?', text, flags=re.IGNORECASE):
        found.add(u)
    for r in re.findall(r'["\']([^"\']+\.m3u8(?:\?[^"\']*)?)["\']', text, flags=re.IGNORECASE):
        full = urljoin(url, r)
        found.add(full)
    print(f"[scan] found {len(found)} candidate m3u8 URLs in page HTML")
    return list(found)

def _parse_attributes(attr_str):
    attrs = {}
    for m in re.finditer(r'([A-Z0-9-]+)=((?:\"[^\"]*\")|[^,\n]+)', attr_str, flags=re.IGNORECASE):
        k = m.group(1).upper()
        v = m.group(2)
        if v.startswith('"') and v.endswith('"'):
            v = v[1:-1]
        attrs[k] = v
    return attrs

def extract_variants(master_url):
    text = download_text(master_url)
    if not text:
        return {}, []
    audio_groups = {}
    for m in re.finditer(r'#EXT-X-MEDIA:([^\n]+)', text, flags=re.IGNORECASE):
        attrs = _parse_attributes(m.group(1))
        if attrs.get('TYPE','').upper() == 'AUDIO':
            group = attrs.get('GROUP-ID')
            uri = attrs.get('URI')
            if group and uri:
                full = urljoin(master_url, uri)
                audio_groups.setdefault(group, []).append(full)
    pattern = re.compile(r'(#EXT-X-STREAM-INF:([^\n]*)\n)([^\n]+)', re.IGNORECASE)
    stream_variants = []
    for header, header_attrs, uri in pattern.findall(text):
        attrs = _parse_attributes(header_attrs)
        codecs = attrs.get('CODECS','')
        codes = codecs.lower()
        has_video = any(x in codes for x in ("avc1","h264","hev1","h265"))
        has_audio = any(x in codes for x in ("mp4a","aac","ac-3","ec-3"))
        audio_group = attrs.get('AUDIO')
        bandwidth = None
        if attrs.get('BANDWIDTH') and attrs['BANDWIDTH'].isdigit():
            bandwidth = int(attrs['BANDWIDTH'])
        resolution = attrs.get('RESOLUTION')
        uri_str = uri.strip()
        full = urljoin(master_url, uri_str)
        stream_variants.append({
            'uri': uri_str,
            'full_uri': full,
            'attributes': attrs,
            'codecs': codecs,
            'has_video': has_video,
            'has_audio': has_audio,
            'audio_group': audio_group,
            'bandwidth': bandwidth,
            'resolution': resolution,
        })
    print('\nDiscovered audio groups:')
    if audio_groups:
        for gid, uris in audio_groups.items():
            print(f"  GROUP-ID={gid} ->")
            for u in uris:
                print(f"    {u}")
    else:
        print('  (none)')
    print('\nDiscovered stream variants:')
    for i, sv in enumerate(stream_variants, start=1):
        b = sv['bandwidth'] or '?'
        r = sv['resolution'] or '-'
        av = 'A+V' if sv['has_audio'] and sv['has_video'] else ('V' if sv['has_video'] else ('A' if sv['has_audio'] else '-'))
        ag = sv['audio_group'] or '-'
        print(f"  {i}. bandwidth={b} resolution={r} type={av} audio_group={ag}\n     {sv['full_uri']}")
    return audio_groups, stream_variants

def resolve_master_to_media(url):
    text = download_text(url)
    if not text:
        return url
    if "#EXT-X-STREAM-INF" not in text:
        return url
    pattern = re.compile(r'#EXT-X-STREAM-INF:([^\n]*)\n([^\n]+)', re.IGNORECASE)
    variants = []
    for header_attrs, uri in pattern.findall(text):
        attrs = _parse_attributes(header_attrs)
        codecs = attrs.get('CODECS','').lower()
        has_video = any(x in codecs for x in ("avc1","h264","hev1","h265"))
        bw = None
        if attrs.get('BANDWIDTH') and attrs['BANDWIDTH'].isdigit():
            bw = int(attrs['BANDWIDTH'])
        full = urljoin(url, uri.strip())
        variants.append({'full': full, 'has_video': has_video, 'bw': bw})
    with_video = [v for v in variants if v['has_video']]
    candidates = with_video or variants
    chosen = max(candidates, key=lambda v: v['bw'] or 0)
    return chosen['full']

def choose_variant(master_url):
    audio_groups, variants = extract_variants(master_url)
    if not variants:
        return None
    combined = [v for v in variants if v['has_video'] and v['has_audio']]
    if combined:
        chosen = max(combined, key=lambda v: v['bandwidth'] or 0)
        video_media = resolve_master_to_media(chosen['full_uri'])
        print('\nChosen combined variant ->', video_media)
        return {'video': video_media, 'audio': None, 'type': 'combined'}
    video_only = [v for v in variants if v['has_video']]
    if video_only:
        video_only.sort(key=lambda v: v['bandwidth'] or 0, reverse=True)
        chosen_v = video_only[0]
        group = chosen_v['audio_group']
        audio_uri = None
        if group and group in audio_groups:
            audio_uri = audio_groups[group][0]
        video_media = resolve_master_to_media(chosen_v['full_uri'])
        print('\nChosen video variant ->', video_media)
        if audio_uri:
            print('Associated audio ->', audio_uri)
            return {'video': video_media, 'audio': audio_uri, 'type': 'separate'}
        else:
            print('No audio group associated with chosen video variant.')
            return {'video': video_media, 'audio': None, 'type': 'video_only'}
    chosen = max(variants, key=lambda v: v['bandwidth'] or 0)
    video_media = resolve_master_to_media(chosen['full_uri'])
    print('\nFallback chosen ->', video_media)
    return {'video': video_media, 'audio': None, 'type': 'fallback'}

def validate_media_playlist_has_segments(url):
    txt = download_text(url)
    if not txt:
        return False
    if '#EXTINF' in txt:
        return True
    return False

def write_m3u(url, outpath=DEFAULT_OUTPUT_FILE):
    m3u = "#EXTM3U\n" + url + "\n"
    with open(outpath, "w", encoding="utf-8", newline="\n") as f:
        f.write(m3u)
    print(f"Wrote {outpath} -> {url}")

def build_headers_string(headers_list):
    if not headers_list:
        return None
    # headers_list contains "Name: value" strings; ffmpeg expects "\r\n" between headers and a final "\r\n"
    cleaned = []
    for h in headers_list:
        if isinstance(h, tuple):
            h = f"{h[0]}: {h[1]}"
        cleaned.append(h.strip())
    s = "\r\n".join(cleaned) + "\r\n"
    return s

def start_ffmpeg(cmd_args, foreground=False, pid_file=None):
    print("\n[ffmpeg] running command:")
    # show readable command
    print(" ".join(shlex.quote(a) for a in cmd_args))
    if foreground:
        # run in foreground, stream output
        try:
            subprocess.run(cmd_args, check=False)
        except KeyboardInterrupt:
            print("[ffmpeg] interrupted by user")
        return None
    else:
        # spawn background process
        if os.name == "nt":
            # Windows: CREATE_NEW_PROCESS_GROUP to allow later taskkill /PID or send CTRL_BREAK
            CREATE_NEW_PROCESS_GROUP = 0x00000200
            proc = subprocess.Popen(cmd_args, creationflags=CREATE_NEW_PROCESS_GROUP)
        else:
            # UNIX: start in new process group
            proc = subprocess.Popen(cmd_args, preexec_fn=os.setsid)
        pid = proc.pid
        print(f"[ffmpeg] spawned background process with PID {pid}")
        if pid_file:
            try:
                with open(pid_file, "w", encoding="utf-8") as f:
                    f.write(str(pid))
                print(f"[ffmpeg] PID written to {pid_file}")
            except Exception as e:
                print(f"[ffmpeg] failed to write pid file: {e}")
        return pid

def run_restarter(pair, ffmpeg_path, output_dir, headers_list, foreground, pid_file):
    os.makedirs(output_dir, exist_ok=True)
    headers_str = build_headers_string(headers_list)
    # Build ffmpeg args
    cmd = [ffmpeg_path]
    # if combined (single input with audio+video), we can feed single input and package to HLS
    if pair['type'] == 'combined':
        if headers_str:
            cmd += ['-headers', headers_str]
        cmd += ['-i', pair['video']]
        # copy both streams
        cmd += ['-map', '0', '-c', 'copy']
    elif pair['type'] == 'separate':
        # supply headers before each -i if provided
        if headers_str:
            cmd += ['-headers', headers_str]
        cmd += ['-i', pair['video']]
        if headers_str:
            cmd += ['-headers', headers_str]
        cmd += ['-i', pair['audio']]
        cmd += ['-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'copy']
    elif pair['type'] == 'video_only' or pair['type'] == 'video_only' or pair['type'] == 'fallback':
        # if video only, we still try to produce HLS (no audio)
        if headers_str:
            cmd += ['-headers', headers_str]
        cmd += ['-i', pair['video']]
        cmd += ['-map', '0', '-c', 'copy']
    else:
        # unknown
        if headers_str:
            cmd += ['-headers', headers_str]
        cmd += ['-i', pair['video']]
        cmd += ['-map', '0', '-c', 'copy']

    # HLS output to output_dir/maspero_combined.m3u8
    out_m3u = os.path.join(output_dir, "maspero_combined.m3u8")
    cmd += ['-f', 'hls', '-hls_time', '4', '-hls_list_size', '6', '-hls_flags', 'delete_segments+omit_endlist', out_m3u]

    pid = start_ffmpeg(cmd, foreground=foreground, pid_file=pid_file)
    return pid

def main():
    parser = argparse.ArgumentParser(description="Extract Maspero HLS URLs and optionally restream with ffmpeg")
    parser.add_argument("--target", default=TARGET_PAGE, help="Target page to sniff (default maspero)")
    parser.add_argument("--output-file", default=DEFAULT_OUTPUT_FILE, help="Write chosen video (media) URL to this m3u file")
    parser.add_argument("--restream", action="store_true", help="Run ffmpeg to combine video+audio into HLS output")
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR, help="Directory for HLS output/segments")
    parser.add_argument("--ffmpeg", dest="ffmpeg_path", default="ffmpeg", help="Path to ffmpeg binary")
    parser.add_argument("--header", action="append", help='HTTP header to pass to ffmpeg inputs, e.g. --header "Referer: https://www.maspero.eg" (repeatable)')
    parser.add_argument("--foreground", action="store_true", help="Run ffmpeg in foreground (do not background)")
    parser.add_argument("--pid-file", default=None, help="Write ffmpeg PID here (defaults to <output-dir>/ffmpeg.pid when --restream)")
    args = parser.parse_args()

    print("extract_url.py - aggressive sniffer + optional restream")
    candidates = sniff_master_aggressive(args.target)
    if not candidates:
        html_candidates = scan_page_html_for_m3u8(args.target)
        candidates = html_candidates

    if not candidates:
        print("No .m3u8 candidates found. See earlier guidance in script output.")
        return

    print("\n>>> Candidate m3u8 URLs discovered:")
    for i, u in enumerate(candidates, 1):
        print(f"  {i}. {u}")

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
            print("  downloaded content does not look like an HLS playlist (no EXTINF or EXT-X-STREAM-INF).")
            valid.append(('unknown', u))

    if not valid:
        print("No valid-looking playlists among candidates.")
        return

    for t, u in valid:
        print(f"  - {t}: {u}")

    # prefer a media playlist (video) to write to maspero.m3u
    chosen_video = None
    chosen_type = None
    # first pick any media that looks like video (attempt to detect h264 marker or 'h264' in url)
    for t, u in valid:
        if t == 'media' and ('h264' in u or 'live-h' in u or 'video' in u or 'hls' in u):
            chosen_video = u
            chosen_type = t
            break
    if not chosen_video:
        # next pick any media
        for t, u in valid:
            if t == 'media':
                chosen_video = u
                chosen_type = t
                break
    if not chosen_video:
        # if no media found, pick first master (we will try to resolve)
        for t, u in valid:
            if t == 'master':
                chosen_video = u
                chosen_type = t
                break
    if not chosen_video:
        # fallback to first candidate
        chosen_video = valid[0][1]
        chosen_type = valid[0][0]

    print(f"\nChosen URL to write to {args.output_file} (prefer video media): {chosen_video}")
    write_m3u(chosen_video, outpath=args.output_file)

    # If restream requested, we need to determine audio pairing (if any)
    if args.restream:
        print("\nPreparing to restream with ffmpeg...")
        # If chosen is a master, try choose_variant logic on it to get pairing
        pair = None
        # Try to use choose_variant() logic to get best pairing
        # We'll attempt to find separate video+audio pair by running choose_variant with chosen master if it's a master.
        # Reuse extract logic: if chosen is a master, choose_variant will prefer combined or pick best video+audio pairing.
        # For convenience, if chosen was media, try to find a sibling audio by scanning its parent master if available.
        # We'll find the master candidate by checking other valid entries (a master in valid list) or the original master candidate list.
        master_candidate = None
        for t, u in valid:
            if t == 'master':
                master_candidate = u
                break
        # If we have a master candidate, use choose_variant on it; otherwise try on the first master-like candidate from initial list.
        from urllib.parse import urlparse
        pair = None
        if master_candidate:
            pair = choose_variant(master_candidate)
        else:
            # fallback: try to resolve the chosen_video if it looks like a master
            txt = download_text(chosen_video)
            if txt and '#EXT-X-STREAM-INF' in txt:
                pair = choose_variant(chosen_video)
            else:
                # if we have both a media video and an audio entry in valid list, pair them heuristically
                media_url = None
                audio_url = None
                for t, u in valid:
                    if t == 'media' and ('aac' in u or 'audio' in u or 'live-aac' in u):
                        audio_url = u
                    if t == 'media' and ('h264' in u or 'video' in u or 'live-h' in u):
                        media_url = u
                if media_url:
                    pair = {'video': media_url, 'audio': audio_url, 'type': 'separate' if audio_url else 'video_only'}

        if not pair:
            print("Could not determine a suitable video+audio pairing automatically.")
            print("Please run the script without --restream, copy the video and audio URLs printed, and I will provide the ffmpeg command.")
            return

        # ensure we prefer the resolved video media (resolve nested masters)
        pair_video_resolved = resolve_master_to_media(pair['video'])
        pair['video'] = pair_video_resolved

        # if there is an audio entry but it's a master, we typically keep that URL (audio playlists are media-level)
        if pair.get('audio'):
            # nothing to resolve usually, but we could attempt resolve_master_to_media if needed
            pass

        if not validate_media_playlist_has_segments(pair['video']):
            print("Chosen video playlist does not contain segments (#EXTINF missing). Aborting restream.")
            return

        output_dir = args.output_dir
        pid_file = args.pid_file or os.path.join(output_dir, "ffmpeg.pid")
        pid = run_restarter(pair, args.ffmpeg_path, output_dir, args.header or [], args.foreground, pid_file)
        if pid:
            print(f"[main] ffmpeg running in background with PID {pid}. HLS output directory: {output_dir}")
            print(f"[main] Serve the directory with e.g. 'python -m http.server' and point your IPTV to http://<host>:8000/maspero_combined.m3u8")
        else:
            print("[main] ffmpeg ran in foreground or exited. Check output above for ffmpeg logs.")

if __name__ == "__main__":
    main()
