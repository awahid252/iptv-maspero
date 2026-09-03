# Hardcoded, explicit stream writing - No variables, no scraping, no APIs
m3u_content = (
    "#EXTM3U\n"
    "#EXTINF:-1 tvg-name=\"Maspero Zaman\" tvg-id=\"maspero.zaman\" group-title=\"Egypt\" tvg-logo=\"https://dmcdn.net\",Maspero Zaman\n"
    "https://dailymotion.com\n"
)

with open('maspero.m3u', 'w', encoding='utf-8') as f:
    f.write(m3u_content)

print("SUCCESS: Forced write of master live stream completed.")
