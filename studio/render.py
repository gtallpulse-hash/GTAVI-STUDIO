"""GTAVI-STUDIO: maakt van een renderopdracht (jobs/<datum>.json) de dia's en Shorts-video's.

Draait in GitHub Actions. Stappen per reel:
  1. beelden ophalen bij gta6centraal.com (media-ID -> source_url via de openbare WordPress-API)
  2. dia's renderen met studio/gta6-social-renderer.js in headless Chromium (9:16 en 4:5)
  3. video maken met ffmpeg: 5 dia's, lichte zoom, overvloeiers, rechtenvrije muziek (of stil)
  4. alles in out/<datum>/ plus manifest.json (de workflow zet dat op de branch 'media')

Gebruik: python studio/render.py jobs/2026-10-30.json out
"""
import base64
import http.server
import json
import os
import random
import shutil
import socketserver
import subprocess
import sys
import threading
import time
import urllib.request
from pathlib import Path

SITE = "https://gta6centraal.com"
REPO_RAW = "https://raw.githubusercontent.com/gtallpulse-hash/GTAVI-STUDIO/media"
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36 GTAVI-STUDIO"
DIA_SEC = 3.4      # duur per dia
OVERGANG = 0.4     # overvloeier
FPS = 30
HIER = Path(__file__).resolve().parent


def haal(url, pad=None, pogingen=3):
    laatste = None
    for i in range(pogingen):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
            with urllib.request.urlopen(req, timeout=60) as r:
                data = r.read()
            if pad:
                Path(pad).write_bytes(data)
            return data
        except Exception as e:  # noqa: BLE001
            laatste = e
            time.sleep(2 + 3 * i)
    raise RuntimeError(f"Ophalen mislukt: {url}: {laatste}")


def beeld_naar_bestand(beeld, map_):
    """media-ID of URL -> lokaal bestand (naam relatief t.o.v. de webmap)."""
    if isinstance(beeld, int) or str(beeld).strip().isdigit():
        info = json.loads(haal(f"{SITE}/wp-json/wp/v2/media/{int(beeld)}?_fields=source_url,mime_type"))
        url = info["source_url"]
    else:
        url = str(beeld)
    ext = os.path.splitext(url.split("?")[0])[1].lower() or ".jpg"
    naam = f"beeld-{abs(hash(url)) % 10**10}{ext}"
    doel = map_ / naam
    if not doel.exists():
        haal(url, doel)
    return naam


def start_server(map_):
    handler = lambda *a, **k: http.server.SimpleHTTPRequestHandler(*a, directory=str(map_), **k)  # noqa: E731
    socketserver.TCPServer.allow_reuse_address = True
    srv = socketserver.TCPServer(("127.0.0.1", 0), handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


def render_dias(reels, web, uit):
    from playwright.sync_api import sync_playwright

    srv, poort = start_server(web)
    try:
        with sync_playwright() as p:
            b = p.chromium.launch()
            pg = b.new_page()
            fouten = []
            pg.on("pageerror", lambda e: fouten.append(str(e)))
            pg.goto(f"http://127.0.0.1:{poort}/index.html")
            pg.evaluate("GTA6Studio.laadLettertypes()")
            for reel in reels:
                n = len(reel["dias"])
                for fmt in ("9x16", "4x5"):
                    for i, d in enumerate(reel["dias"]):
                        data_url = pg.evaluate(
                            """async ([d, i, n, fmt]) => {
                                const blob = await GTA6Studio.renderDia(d, i, n, fmt);
                                return await new Promise(ok => { const fr = new FileReader(); fr.onload = () => ok(fr.result); fr.readAsDataURL(blob); });
                            }""",
                            [d, i, n, fmt],
                        )
                        pad = uit / f"{reel['naam']}-{fmt}-{i + 1}.png"
                        pad.write_bytes(base64.b64decode(data_url.split(",", 1)[1]))
            if fouten:
                print("Paginafouten:", fouten)
            b.close()
    finally:
        srv.shutdown()


def kies_muziek(gebruikt, werkmap):
    lijst = json.loads((HIER / "muziek.json").read_text(encoding="utf-8"))
    random.shuffle(lijst)
    for t in lijst:
        if t["url"] in gebruikt:
            continue
        pad = werkmap / f"muziek-{abs(hash(t['url'])) % 10**8}.mp3"
        try:
            if not pad.exists():
                haal(t["url"], pad, pogingen=2)
            duur = float(subprocess.check_output(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(pad)]).decode().strip())
            if duur < 20:
                continue
            gebruikt.add(t["url"])
            return pad, t, duur
        except Exception as e:  # noqa: BLE001
            print("Muziek overgeslagen:", t.get("titel"), e)
    return None, None, 0


def maak_video(reel, uit, muziek):
    n = len(reel["dias"])
    totaal = n * DIA_SEC - (n - 1) * OVERGANG
    frames = int(round(DIA_SEC * FPS))
    cmd = ["ffmpeg", "-y", "-loglevel", "error"]
    for i in range(n):
        cmd += ["-loop", "1", "-framerate", str(FPS), "-t", str(DIA_SEC), "-i", str(uit / f"{reel['naam']}-9x16-{i + 1}.png")]
    pad_muziek, info, duur = muziek
    if pad_muziek:
        start = max(0.0, min(duur - totaal - 1, duur * 0.15))
        cmd += ["-ss", f"{start:.2f}", "-i", str(pad_muziek)]
    else:
        cmd += ["-f", "lavfi", "-t", f"{totaal:.2f}", "-i", "anullsrc=r=44100:cl=stereo"]
    filt = []
    for i in range(n):
        # lichte zoom (Ken Burns), eerst opschalen tegen trillen
        filt.append(
            f"[{i}:v]scale=2160:3840,zoompan=z='1+0.035*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frames}:s=1080x1920:fps={FPS},setsar=1,format=yuv420p[v{i}]"
        )
    vorige = "v0"
    for i in range(1, n):
        off = i * (DIA_SEC - OVERGANG)
        filt.append(f"[{vorige}][v{i}]xfade=transition=fade:duration={OVERGANG}:offset={off:.2f}[x{i}]")
        vorige = f"x{i}"
    a = n
    if pad_muziek:
        filt.append(f"[{a}:a]atrim=0:{totaal:.2f},afade=t=in:d=0.6,afade=t=out:st={totaal - 1.6:.2f}:d=1.6,volume=0.85[a]")
    else:
        filt.append(f"[{a}:a]atrim=0:{totaal:.2f}[a]")
    video = uit / f"{reel['naam']}-short.mp4"
    cmd += [
        "-filter_complex", ";".join(filt), "-map", f"[{vorige}]", "-map", "[a]",
        "-c:v", "libx264", "-profile:v", "high", "-preset", "medium", "-crf", "20", "-maxrate", "6M", "-bufsize", "12M",
        "-pix_fmt", "yuv420p", "-r", str(FPS), "-c:a", "aac", "-b:a", "128k", "-ar", "44100",
        "-t", f"{totaal:.2f}", "-movflags", "+faststart", str(video),
    ]
    subprocess.run(cmd, check=True)
    return video, round(totaal, 1)


def main():
    job_pad, uit_basis = Path(sys.argv[1]), Path(sys.argv[2])
    job = json.loads(job_pad.read_text(encoding="utf-8"))
    datum = job["datum"]
    uit = uit_basis / datum
    uit.mkdir(parents=True, exist_ok=True)
    web = Path("_web")
    if web.exists():
        shutil.rmtree(web)
    web.mkdir()
    shutil.copy(HIER / "gta6-social-renderer.js", web)
    fonts = Path("node_modules/@fontsource")
    for src in ["bebas-neue/files/bebas-neue-latin-400-normal.woff2", "inter/files/inter-latin-400-normal.woff2",
                "inter/files/inter-latin-700-normal.woff2", "inter/files/inter-latin-ext-400-normal.woff2",
                "inter/files/inter-latin-ext-700-normal.woff2", "bebas-neue/files/bebas-neue-latin-ext-400-normal.woff2"]:
        if (fonts / src).exists():
            shutil.copy(fonts / src, web)
    (web / "index.html").write_text("""<!doctype html><html><head><meta charset="utf-8"><style>
@font-face{font-family:"Bebas Neue";src:url(bebas-neue-latin-400-normal.woff2)}
@font-face{font-family:"Bebas Neue";src:url(bebas-neue-latin-ext-400-normal.woff2);unicode-range:U+0100-024F,U+1E00-1EFF}
@font-face{font-family:"Inter";font-weight:400;src:url(inter-latin-400-normal.woff2)}
@font-face{font-family:"Inter";font-weight:700;src:url(inter-latin-700-normal.woff2)}
@font-face{font-family:"Inter";font-weight:400;src:url(inter-latin-ext-400-normal.woff2);unicode-range:U+0100-024F,U+1E00-1EFF}
@font-face{font-family:"Inter";font-weight:700;src:url(inter-latin-ext-700-normal.woff2);unicode-range:U+0100-024F,U+1E00-1EFF}
</style><link data-gta6studio href="data:text/css,"></head><body><script src="gta6-social-renderer.js"></script></body></html>""",
                                    encoding="utf-8")

    reels = job["reels"]
    for reel in reels:
        for d in reel["dias"]:
            d["beeld"] = beeld_naar_bestand(d["beeld"], web)
    render_dias(reels, web, uit)

    gebruikt = set()
    manifest = {"datum": datum, "gemaakt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "reels": []}
    for reel in reels:
        muziek = kies_muziek(gebruikt, Path("_web")) if job.get("muziek", True) else (None, None, 0)
        video, duur = maak_video(reel, uit, muziek)
        info = muziek[1]
        n = len(reel["dias"])
        url = lambda f: f"{REPO_RAW}/{datum}/{f}"  # noqa: E731
        item = {k: v for k, v in reel.items() if k != "dias"}
        item.update({
            "video": url(video.name),
            "duur_sec": duur,
            "fotos_4x5": [url(f"{reel['naam']}-4x5-{i + 1}.png") for i in range(n)],
            "fotos_9x16": [url(f"{reel['naam']}-9x16-{i + 1}.png") for i in range(n)],
            "muziek": ({"titel": info["titel"], "artiest": info["artiest"], "credit": info["credit"]} if info else None),
        })
        manifest["reels"].append(item)
        print(f"Klaar: {reel['naam']} ({duur}s, muziek: {info['titel'] if info else 'stil'})")
    (uit / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print("Manifest:", f"{REPO_RAW}/{datum}/manifest.json")


if __name__ == "__main__":
    main()
