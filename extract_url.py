import re
import os
import argparse
import shlex
import subprocess
import threading
import socket
import time
import urllib.request
from urllib.parse import urljoin
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout

TARGET_PAGE = "https://www.maspero.eg/stream/6"
DEFAULT_OUTPUT_FILE = "maspero.m3u"
DEFAULT_OUTDIR = "hls_out"
HTTP_PORT = 8000
HEADLESS = True
WAIT_AFTER_LOAD_MS = 4000


def download_text(url, timeout=15):
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception:
        return None


def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def sniff_master_aggressive(target_page, headless=True):
    candidates = set()
    print("[sniff] starting Playwright...")
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=headless)
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
            except Exception as e:
                print(f"[sniff] navigation error: {e}")

            try:
                content = page.content()

                absolute = set(re.findall(
                    r'https?://[^\'"\s>]+\.m3u8(?:\?[^\'"\s>]*)?',
                    content,
                    flags=re.IGNORECASE
                ))

                relative = set(re.findall(
                    r"['\"]([^'\"]+\.m3u8(?:\?[^'\"]*)?)['\"]",
                    content,
                    flags=re.IGNORECASE
                ))

                for r in relative:
                    absolute.add(urljoin(page.url, r))

                candidates.update(absolute)

            except Exception as e:
                print(f"[sniff] page.content() error: {e}")

            browser.close()
    except Exception as e:
        print(f"[sniff] could not start Playwright: {e}")
        print("[sniff] Make sure 'playwright' is installed and you ran 'python -m playwright install'.")
        return list(candidates)

    return list(candidates)


def scan_page_html_for_m3u8(url):
    text = download_text(url)
    found = set()
    if not text:
        return []

    for u in re.findall(r'https?://[^\'"\s>]+\.m3u8(?:\?[^\'"\s>]*)?', text, flags=re.IGNORECASE):
        found.add(u)

    for r in re.findall(r"['\"]([^'\"]+\.m3u8(?:\?[^'\"]*)?)['\"]", text, flags=re.IGNORECASE):
        found.add(urljoin(url, r))

    return list(found)


def _parse_attributes(attr_str):
    attrs = {}
    for m in re.finditer(r'([A-Z0-9-]+)=((?:\"[^\"]*\")|[^,\n]+)', attr_str, flags=re.IGNORECASE):
        key = m.group(1).upper()
        val = m.group(2)
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        attrs[key] = val
    return attrs


def extract_variants(master_url):
    text = download_text(master_url)
    if not text:
        return {}, []

    audio_groups = {}
    for m in re.finditer(r'#EXT-X-MEDIA:([^\n]+)', text, flags=re.IGNORECASE):
        attrs = _parse_attributes(m.group(1))
        if attrs.get('TYPE', '').upper() == 'AUDIO':
            group = attrs.get('GROUP-ID')
            uri = attrs.get('URI')
            if group and uri:
                full = urljoin(master_url, uri)
                audio_groups.setdefault(group, []).append(full)

    pattern = re.compile(r'(#EXT-X-STREAM-INF:([^\n]*)\n)([^\n]+)', re.IGNORECASE)
    stream_variants = []
    for header, header_attrs, uri in pattern.findall(text):
        attrs = _parse_attributes(header_attrs)
        codecs = attrs.get('CODECS', '')
        codes = codecs.lower()
        has_video = any(x in codes for x in ("avc1", "h264", "hev1", "h265"))
        has_audio = any(x in codes for x in ("mp4a", "aac", "ac-3", "ec-3"))
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

    print("\nDiscovered audio groups:")
    if audio_groups:
        for gid, uris in audio_groups.items():
            print(f"  GROUP-ID={gid} ->")
            for u in uris:
                print(f"    {u}")
    else:
        print("  (none)")

    print("\nDiscovered stream variants:")
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
        codes = attrs.get('CODECS', '').lower()
        has_video = any(x in codes for x in ("avc1", "h264", "hev1", "h265"))
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
        print("\nChosen combined variant ->", video_media)
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
        print("\nChosen video variant ->", video_media)
        if audio_uri:
            print("Associated audio ->", audio_uri)
            return {'video': video_media, 'audio': audio_uri, 'type': 'separate'}
        print("No audio group associated with chosen video variant.")
        return {'video': video_media, 'audio': None, 'type': 'video_only'}

    chosen = max(variants, key=lambda v: v['bandwidth'] or 0)
    video_media = resolve_master_to_media(chosen['full_uri'])
    print("\nFallback chosen ->", video_media)
    return {'video': video_media, 'audio': None, 'type': 'fallback'}


def validate_media_playlist_has_segments(url):
    txt = download_text(url)
    if not txt:
        return False
    return "#EXTINF" in txt


def write_m3u(url, outpath=DEFAULT_OUTPUT_FILE):
    m3u = "#EXTM3U\n" + url + "\n"
    with open(outpath, "w", encoding="utf-8", newline="\n") as f:
        f.write(m3u)
    print(f"Wrote {outpath} -> {url}")


def build_headers_string(headers_list):
    if not headers_list:
        return None

    cleaned = []
    for h in headers_list:
        if isinstance(h, tuple):
            h = f"{h[0]}: {h[1]}"
        cleaned.append(h.strip())

    return ("\r\n".join(cleaned) + "\r\n")


def start_ffmpeg(cmd_args, foreground=False, pid_file=None):
    print("\n[ffmpeg] running command:")
    print(" ".join(shlex.quote(a) for a in cmd_args))

    if foreground:
        try:
            subprocess.run(cmd_args, check=False)
        except KeyboardInterrupt:
            print("[ffmpeg] interrupted by user")
        return None

    if os.name == "nt":
        CREATE_NEW_PROCESS_GROUP = 0x00000200
        proc = subprocess.Popen(cmd_args, creationflags=CREATE_NEW_PROCESS_GROUP)
    else:
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

    cmd = [ffmpeg_path]

    if pair['type'] == 'combined':
        if headers_str:
            cmd += ['-headers', headers_str]
        cmd += ['-i', pair['video']]
        cmd += ['-map', '0', '-c', 'copy']

    elif pair['type'] == 'separate':
        if headers_str:
            cmd += ['-headers', headers_str]
        cmd += ['-i', pair['video']]
        if headers_str:
            cmd += ['-headers', headers_str]
        cmd += ['-i', pair['audio']]
        cmd += ['-map', '0:v:0', '-map', '1:a:0', '-c:v', 'copy', '-c:a', 'aac', '-b:a', '128k', '-ac', '2']

    else:
        if headers_str:
            cmd += ['-headers', headers_str]
        cmd += ['-i', pair['video']]
        cmd += ['-map', '0', '-c', 'copy']

    out_m3u = os.path.join(output_dir, "maspero_combined.m3u8")
    cmd += ['-f', 'hls', '-hls_time', '4', '-hls_list_size', '6', '-hls_flags', 'delete_segments+omit_endlist', out_m3u]

    return start_ffmpeg(cmd, foreground=foreground, pid_file=pid_file)


def main():
    parser = argparse.ArgumentParser(description="Extract Maspero HLS URLs and optionally restream with ffmpeg")
    parser.add_argument("--target", default=TARGET_PAGE)
    parser.add_argument("--output-file", default=DEFAULT_OUTPUT_FILE)
    parser.add_argument("--restream", action="store_true")
    parser.add_argument("--output-dir", default=DEFAULT_OUTDIR)
    parser.add_argument("--ffmpeg", dest="ffmpeg_path", default="ffmpeg")
    parser.add_argument("--header", action="append", help='HTTP header to pass to ffmpeg inputs, e.g. --header "Referer: https://www.maspero.eg"')
    parser.add_argument("--foreground", action="store_true")
    parser.add_argument("--pid-file", default=None)
    args = parser.parse_args()

    print("extract_url.py - aggressive sniffer + optional restream")

    candidates = sniff_master_aggressive(args.target, headless=HEADLESS)
    if not candidates:
        candidates = scan_page_html_for_m3u8(args.target)

    if not candidates:
        print("No .m3u8 candidates found.")
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
            valid.append(("media", u))
        elif "#EXT-X-STREAM-INF" in txt:
            print("  looks like a master playlist (#EXT-X-STREAM-INF present).")
            valid.append(("master", u))
        else:
            print("  downloaded content does not look like an HLS playlist (no EXTINF or EXT-X-STREAM-INF).")
            valid.append(("unknown", u))

    if not valid:
        print("No valid-looking playlists among candidates.")
        return

    for kind, url in valid:
        print(f"  - {kind}: {url}")

    # prefer a media playlist that looks like video
    chosen_video = None
    for kind, url in valid:
        if kind == "media" and ("h264" in url or "live-h" in url or "video" in url):
            chosen_video = url
            break

    if not chosen_video:
        for kind, url in valid:
            if kind == "media":
                chosen_video = url
                break

    if not chosen_video:
        for kind, url in valid:
            if kind == "master":
                chosen_video = url
                break

    if not chosen_video:
        chosen_video = valid[0][1]

    print(f"\nChosen URL to write to {args.output_file} (prefer video media): {chosen_video}")
    write_m3u(chosen_video, outpath=args.output_file)

    if not args.restream:
        print("\nDone. Run with --restream to combine video + audio.")
        return

    master_candidate = None
    for kind, url in valid:
        if kind == "master":
            master_candidate = url
            break

    pair = None
    if master_candidate:
        pair = choose_variant(master_candidate)
    else:
        media_url = None
        audio_url = None
        for kind, url in valid:
            if kind == "media" and ("aac" in url or "audio" in url or "live-aac" in url):
                audio_url = url
            if kind == "media" and ("h264" in url or "video" in url or "live-h" in url):
                media_url = url

        if media_url:
            pair = {'video': media_url, 'audio': audio_url, 'type': 'separate' if audio_url else 'video_only'}

    if not pair:
        print("Could not determine a suitable video+audio pairing automatically.")
        return

    pair['video'] = resolve_master_to_media(pair['video'])

    if not validate_media_playlist_has_segments(pair['video']):
        print("Chosen video playlist does not contain segments (#EXTINF missing). Aborting restream.")
        return

    output_dir = args.output_dir
    pid_file = args.pid_file or os.path.join(output_dir, "ffmpeg.pid")
    pid = run_restarter(pair, args.ffmpeg_path, output_dir, args.header or [], args.foreground, pid_file)

    if pid:
        print(f"\n[main] ffmpeg running in background with PID {pid}.")
        print(f"[main] Output directory: {output_dir}")
        print(f"[main] HLS URL: http://{get_local_ip()}:8000/{output_dir}/maspero_combined.m3u8")
    else:
        print("\n[main] ffmpeg ran in foreground or exited. Check terminal logs.")


if __name__ == "__main__":
    main()
