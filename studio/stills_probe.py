"""Test welke downloadroute vanaf GitHub werkt voor officiële GTA VI-video's (eenmalige diagnose)."""
import json, subprocess, urllib.request

VID = "VQRLujxTm3c"  # Trailer 2


def run(cmd, t=240):
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=t)
        return r.returncode, (r.stdout + r.stderr)[-400:]
    except Exception as e:  # noqa: BLE001
        return 99, str(e)


print("== yt-dlp clients ==")
for c in ["web_embedded", "tv_embedded", "android_vr", "tv_simply", "web_creator"]:
    rc, out = run(["yt-dlp", "--extractor-args", f"youtube:player_client={c}", "-f", "bv*[height<=1080]",
                   "--get-url", f"https://www.youtube.com/watch?v={VID}"])
    print(c, "OK" if rc == 0 else "FOUT", out.replace("\n", " ")[:250])

print("== Invidious / Piped ==")
for base in ["https://inv.nadeko.net", "https://invidious.nerdvpn.de", "https://yewtu.be", "https://iv.ggtyler.dev",
             "https://invidious.f5.si", "https://pipedapi.kavin.rocks", "https://api.piped.private.coffee"]:
    url = f"{base}/streams/{VID}" if "piped" in base else f"{base}/api/v1/videos/{VID}?local=true"
    try:
        j = json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"}), timeout=30))
        streams = j.get("adaptiveFormats") or j.get("videoStreams") or []
        best = [s for s in streams if "1080" in str(s.get("qualityLabel") or s.get("quality"))]
        print(base, "OK", len(streams), "streams,", len(best), "x 1080p", (best[0].get("url", "")[:90] if best else ""))
        if best:
            u = best[0]["url"]
            if u.startswith("/"):
                u = base + u
            rc, out = run(["curl", "-sL", "-r", "0-2000000", "-o", "/tmp/deel.mp4", "-w", "%{http_code} %{size_download}", u], 120)
            print("   download-test:", out)
    except Exception as e:  # noqa: BLE001
        print(base, "FOUT", str(e)[:150])

print("== Rockstar-site (speler) ==")
from playwright.sync_api import sync_playwright  # noqa: E402
with sync_playwright() as p:
    b = p.chromium.launch()
    pg = b.new_page(user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/131 Safari/537.36")
    gezien = []
    pg.on("request", lambda r: gezien.append(r.url) if any(x in r.url for x in [".m3u8", ".mp4", "youtube.com/embed", "videos"]) else None)
    try:
        pg.goto("https://www.rockstargames.com/VI", wait_until="networkidle", timeout=90000)
        for tekst in ["Trailer 2", "Watch"]:
            try:
                pg.get_by_text(tekst, exact=False).first.click(timeout=8000)
                pg.wait_for_timeout(6000)
            except Exception as e:  # noqa: BLE001
                print("klik", tekst, "lukte niet:", str(e)[:80])
        links = pg.eval_on_selector_all("a[href*='video']", "els => els.map(e => e.href)")
        print("videolinks:", sorted(set(links))[:20])
    except Exception as e:  # noqa: BLE001
        print("pagina fout:", str(e)[:200])
    print("netwerk:", sorted(set(gezien))[:25])
    b.close()
