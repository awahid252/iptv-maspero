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


def _parse_attributes(attr_str):
    # Parse a comma-separated list of key=value pairs where values may be quoted
    attrs = {}
    for m in re.finditer(r'([A-Z0-9-]+)=((?:"[^"]*")|[^,\n]+)', attr_str, flags=re.IGNORECASE):
        k = m.group(1).upper()
        v = m.group(2)
        if v.startswith('"') and v.endswith('"'):
            v = v[1:-1]
        attrs[k] = v
    return attrs


def extract_variants(master_url):
    """
    Parse the master playlist and return:
      - audio_groups: dict group_id -> list of audio playlist full URLs
      - stream_variants: list of dicts with keys: uri, full_uri, attributes (dict), codecs, has_video, has_audio, audio_group, bandwidth, resolution
    Also prints a human-readable list to stdout.
    """
    text = download_text(master_url)
    # Parse EXT-X-MEDIA TYPE=AUDIO lines
    audio_groups = {}
    for m in re.finditer(r'#EXT-X-MEDIA:([^\n]+)', text, flags=re.IGNORECASE):
        attrs = _parse_attributes(m.group(1))
        if attrs.get('TYPE', '').upper() == 'AUDIO':
            group = attrs.get('GROUP-ID') or attrs.get('GROUP-ID')
            uri = attrs.get('URI')
            if group and uri:
                full = urljoin(master_url, uri)
                audio_groups.setdefault(group, []).append(full)

    # Parse EXT-X-STREAM-INF blocks and following URI
    pattern = re.compile(r'(#EXT-X-STREAM-INF:([^\n]*)\n)([^\n]+)', re.IGNORECASE)
    stream_variants = []
    for header, header_attrs, uri in pattern.findall(text):
        attrs = _parse_attributes(header_attrs)
        codecs = attrs.get('CODECS', '')
        codecs_lower = codecs.lower()
        has_video = any(x in codecs_lower for x in ("avc1", "h264", "hev1", "h265"))
        has_audio = any(x in codecs_lower for x in ("mp4a", "aac", "ac-3", "ec-3"))
        audio_group = attrs.get('AUDIO')
        bandwidth = int(attrs.get('BANDWIDTH')) if attrs.get('BANDWIDTH') and attrs.get('BANDWIDTH').isdigit() else None
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

    # Print discovered audio groups and variants
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


def choose_variant(master_url):
    # If there is a combined variant we prefer it. Otherwise pair the best video-only variant with an audio playlist from its AUDIO group.
    audio_groups, variants = extract_variants(master_url)
    if not variants:
        return None

    # First look for a variant that contains both audio+video
    combined = [v for v in variants if v['has_video'] and v['has_audio']]
    if combined:
        # pick highest bandwidth combined
        chosen = max(combined, key=lambda v: v['bandwidth'] or 0)
        print('\nChosen combined variant:')
        print(chosen['full_uri'])
        return {'video': chosen['full_uri'], 'audio': None, 'type': 'combined'}

    # No combined variant; look for video variants that reference an AUDIO group
    video_only = [v for v in variants if v['has_video']]
    # sort by bandwidth desc
    video_only.sort(key=lambda v: v['bandwidth'] or 0, reverse=True)
    for v in video_only:
        group = v['audio_group']
        if group and group in audio_groups:
            audio_uri = audio_groups[group][0]
            print('\nChosen pairing:')
            print('  video:', v['full_uri'])
            print('  audio:', audio_uri)
            return {'video': v['full_uri'], 'audio': audio_uri, 'type': 'separate'}

    # fallback: if the master contains EXT-X-MEDIA TYPE=AUDIO but we couldn't match groups, return the master
    text = download_text(master_url)
    if re.search(r"#EXT-X-MEDIA:.*TYPE=\s*?AUDIO", text, re.IGNORECASE):
        print('\nMaster contains AUDIO groups but no clear pairing found; returning master URL for players that support alternate audio.')
        return {'video': master_url, 'audio': None, 'type': 'master'}

    # nothing usable found
    return None


def validate_variant_pair(pair):
    # pair is dict returned from choose_variant
    if not pair:
        return False
    try:
        txt = download_text(pair['video'])
    except Exception:
        return False
    if '#EXTINF' in txt and len(txt) > 200:
        return True
    # if it's a master with separate audio, accept if it contains streams + media
    if '#EXT-X-STREAM-INF' in txt and '#EXT-X-MEDIA' in txt:
        return True
    # if video is a variant but is short, still allow (sometimes small files)
    return True


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
    pair = choose_variant(master)
    if not pair:
        print("No suitable variant or pairing found in master.")
        return
    print('\nValidation...')
    if not validate_variant_pair(pair):
        print("Variant/master validation failed (no segments or streams).")
        return

    # For convenience write the chosen video (or master) into the maspero.m3u file.
    write_m3u(pair['video'])
    print("\nmaspero.m3u written with:")
    if pair['type'] == 'combined':
        print('  combined variant ->', pair['video'])
    elif pair['type'] == 'separate':
        print('  video ->', pair['video'])
        print('  audio ->', pair['audio'])
    else:
        print('  master ->', pair['video'])

if __name__ == "__main__":
    main()
