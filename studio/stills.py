"""Haalt stilstaande beelden (stills) uit officiële GTA VI-video's van Rockstar Games.

Gebruik: python studio/stills.py <map-van-branch-stills> [extra YouTube-ID's...]

Per video:
  1. downloaden met yt-dlp (1080p, alleen beeld);
  2. zwarte filmbalken opsporen (ffmpeg cropdetect) en wegknippen;
  3. elke scènewissel zoeken en het beeld 0,8 s na de wissel nemen (geen overgangsbeeld);
  4. te donkere, onscherpe en bijna dubbele beelden weggooien;
  5. JPG's (max. 1600 px breed) + contactbladen met nummers bewaren in <map>/<kort>/.
Alles komt in <map>/catalogus.json. Video's die er al in staan, worden overgeslagen.
"""
import json, os, re, subprocess, sys, tempfile, time
from collections import Counter
from PIL import Image, ImageDraw, ImageFilter, ImageStat

HIER = os.path.dirname(os.path.abspath(__file__))
UIT = sys.argv[1]
EXTRA = sys.argv[2:]
RAW = "https://raw.githubusercontent.com/gtallpulse-hash/GTAVI-STUDIO/stills"
MAX_PER_VIDEO = 160
BREED = 1600


def run(cmd, **kw):
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def laad_catalogus():
    p = os.path.join(UIT, "catalogus.json")
    if os.path.exists(p):
        with open(p, encoding="utf-8") as f:
            return json.load(f)
    return {"uitleg": "Stills uit officiële GTA VI-video's van Rockstar Games. Bijschrift: 'Beeld: Rockstar Games (still uit <titel>)'.",
            "videos": {}, "stills": []}


RS = "https://videos.rockstargames.com/v4/{}/data/en_us-context-embed.json"


def rockstar_videos(start):
    """Loopt de officiële Rockstar-videoserver af (start-ID's + 'related') en geeft GTA VI-video's met een mp4."""
    import urllib.request
    gezien, rij, uit = set(), list(start), []
    while rij and len(gezien) < 80:
        rid = rij.pop(0)
        if rid in gezien:
            continue
        gezien.add(rid)
        try:
            req = urllib.request.Request(RS.format(rid), headers={"User-Agent": "Mozilla/5.0 GTAVI-STUDIO"})
            data = json.load(urllib.request.urlopen(req, timeout=60))["data"]
        except Exception as e:  # noqa: BLE001
            print(f"  {rid}: niet gelezen ({e})"); continue
        v = data.get("video") or {}
        spel = json.dumps(v.get("game", "")) + json.dumps([r.get("game") for r in data.get("related", {}).get("results", [])])
        for r in (data.get("related") or {}).get("results", []):
            if re.search(r"gta6|gtavi|\bvi\b|grand theft auto vi", json.dumps(r.get("game", "")), re.I) or not r.get("game"):
                rij.append(r["id"])
        files = {f.get("size") or f.get("resolution") or f.get("label"): f.get("src") or f.get("url") for f in v.get("files", [])}
        mp4 = None
        for k in ("1080p", "1080", "720p", "720"):
            for sleutel, url in files.items():
                if str(sleutel).startswith(k) and url:
                    mp4 = url; break
            if mp4: break
        if not mp4:
            for f in v.get("files", []):
                for waarde in f.values():
                    if isinstance(waarde, str) and waarde.endswith("1080p.mp4"):
                        mp4 = waarde
        print(f"  Rockstar {rid}: {v.get('title')} | mp4: {'ja' if mp4 else 'nee'} | youtube: {v.get('youtubeId')}")
        uit.append({"id": rid, "kort": rid, "titel": f"Grand Theft Auto VI: {v.get('title')}" if "Grand Theft" not in (v.get('title') or "") else v.get('title'),
                    "mp4": mp4, "youtube": v.get("youtubeId"), "pagina": f"https://www.rockstargames.com/videos/{rid}"})
    return uit


def nieuwe_rockstar_videos(bekend):
    """Zoekt recente GTA VI-video's op het Rockstar-kanaal die nog niet in de lijst staan."""
    r = run(["yt-dlp", "--flat-playlist", "--playlist-end", "40", "-J",
             "https://www.youtube.com/@RockstarGames/videos"], timeout=300)
    if r.returncode != 0:
        print("::warning::Rockstar-kanaal niet gelezen:", r.stderr[-300:]); return []
    uit = []
    for e in json.loads(r.stdout).get("entries", []):
        t = e.get("title") or ""
        if e.get("id") in bekend or not re.search(r"Grand Theft Auto VI|GTA ?VI|GTA ?6", t, re.I):
            continue
        if (e.get("duration") or 0) > 3600:
            continue
        kort = "R" + re.sub(r"[^A-Za-z0-9]", "", e["id"])[:6]
        uit.append({"id": e["id"], "kort": kort, "titel": t})
        print(f"::notice::Nieuwe Rockstar-video gevonden: {t} ({e['id']})")
    return uit


def download(vid, doel):
    for client in ("default", "tv,web_safari", "mweb", "ios"):
        cmd = ["yt-dlp", "-q", "--no-warnings", "-f", "bv*[height<=1080][ext=mp4]/bv*[height<=1080]/b[height<=1080]",
               "-o", doel, "--force-overwrites", f"https://www.youtube.com/watch?v={vid}"]
        if client != "default":
            cmd[1:1] = ["--extractor-args", f"youtube:player_client={client}"]
        r = run(cmd, timeout=1500)
        if r.returncode == 0 and os.path.exists(doel) and os.path.getsize(doel) > 1_000_000:
            return True
        print(f"  download {vid} via {client} mislukt: {r.stderr.strip()[-200:]}")
    return False


def info(pad):
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height:format=duration",
             "-of", "json", pad])
    j = json.loads(r.stdout)
    return j["streams"][0]["width"], j["streams"][0]["height"], float(j["format"]["duration"])


def crop_van(pad):
    r = run(["ffmpeg", "-hide_banner", "-i", pad, "-vf", "select='not(mod(n,24))',cropdetect=limit=24:round=2:reset=1",
             "-an", "-f", "null", "-"], timeout=1800)
    waarden = re.findall(r"crop=(\d+:\d+:\d+:\d+)", r.stderr)
    if not waarden:
        return None
    # de grootste uitsnede die vaak voorkomt (donkere beelden geven te kleine uitsnedes)
    tel = Counter(waarden)
    vaak = [w for w, n in tel.items() if n >= max(3, len(waarden) * 0.08)] or [tel.most_common(1)[0][0]]
    return max(vaak, key=lambda w: int(w.split(":")[0]) * int(w.split(":")[1]))


def scenewissels(pad, duur):
    r = run(["ffmpeg", "-hide_banner", "-i", pad, "-vf", "scale=320:-2,select='gt(scene,0.30)',showinfo",
             "-an", "-f", "null", "-"], timeout=3000)
    tijden = [0.5] + [float(t) for t in re.findall(r"pts_time:([\d.]+)", r.stderr)]
    gekozen, vorige = [], -99
    for t in sorted(tijden):
        if t - vorige >= 1.6 and t + 1.0 < duur:
            gekozen.append(t)
            vorige = t
    if len(gekozen) > MAX_PER_VIDEO:  # gelijkmatig uitdunnen
        stap = len(gekozen) / MAX_PER_VIDEO
        gekozen = [gekozen[int(i * stap)] for i in range(MAX_PER_VIDEO)]
    return gekozen


def dhash(img):
    g = img.convert("L").resize((9, 8))
    px = list(g.getdata())
    return sum(1 << i for i in range(64) if px[(i // 8) * 9 + i % 8] > px[(i // 8) * 9 + i % 8 + 1])


def goed_genoeg(img):
    stat = ImageStat.Stat(img.convert("L"))
    if stat.mean[0] < 38 or stat.stddev[0] < 22:  # te donker of te vlak (fade, zwart, wit)
        return False
    randen = ImageStat.Stat(img.convert("L").resize((640, 360)).filter(ImageFilter.FIND_EDGES))
    return randen.var[0] > 140  # onscherp/bewegingsonscherpte valt af


def contactbladen(map_, items, kort):
    bladen, per = [], 30
    for b in range(0, len(items), per):
        deel = items[b:b + per]
        kol, tw, th = 5, 320, 180
        rij = (len(deel) + kol - 1) // kol
        blad = Image.new("RGB", (kol * tw, rij * (th + 22)), (20, 20, 20))
        d = ImageDraw.Draw(blad)
        for i, it in enumerate(deel):
            im = Image.open(os.path.join(UIT, it["bestand"])).convert("RGB")
            im.thumbnail((tw, th))
            x, y = (i % kol) * tw, (i // kol) * (th + 22)
            blad.paste(im, (x + (tw - im.width) // 2, y + (th - im.height) // 2))
            d.text((x + 6, y + th + 4), f"{it['code']}", fill=(255, 220, 0))
        naam = f"{kort}/blad-{b // per + 1:02d}.jpg"
        blad.save(os.path.join(UIT, naam), quality=80)
        bladen.append(naam)
    return bladen


def verwerk(v, cat, hashes):
    kort = v["kort"]
    print(f"== {v['titel']} ({v['id']}) ==")
    tmp = tempfile.mkdtemp()
    pad = os.path.join(tmp, "v.mp4")
    bron = None
    if v.get("mp4"):
        r = run(["curl", "-sSfL", "--retry", "3", "-A", "Mozilla/5.0", "-o", pad, v["mp4"]], timeout=2400)
        if r.returncode == 0 and os.path.getsize(pad) > 1_000_000:
            bron = v["mp4"]
        else:
            print("  mp4 van Rockstar mislukt:", r.stderr[-200:])
    for kandidaat in ([] if bron else [x for x in [v.get("youtube")] + v.get("download", []) if x]):
        if download(kandidaat, pad):
            bron = kandidaat
            break
    if not bron:
        print(f"::warning::{v['titel']}: downloaden lukte niet (YouTube blokkeert of leeftijdsbeperking)")
        return False
    w, h, duur = info(pad)
    crop = crop_van(pad) or f"{w}:{h}:0:0"
    print(f"  {w}x{h}, {duur:.0f} s, uitsnede {crop}, gedownload van {bron}")
    tijden = scenewissels(pad, duur)
    print(f"  {len(tijden)} scènes")
    os.makedirs(os.path.join(UIT, kort), exist_ok=True)
    nieuw = []
    for t in tijden:
        neem = min(t + 0.8, duur - 0.2)
        mm, ss = int(neem // 60), int(neem % 60)
        code = f"{kort}-{mm:02d}m{ss:02d}"
        rel = f"{kort}/{code}.jpg"
        doel = os.path.join(UIT, rel)
        r = run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{neem:.2f}", "-i", pad,
                 "-frames:v", "1", "-vf", f"crop={crop},scale='min({BREED},iw)':-2", "-q:v", "3", doel])
        if r.returncode != 0 or not os.path.exists(doel):
            continue
        img = Image.open(doel)
        hsh = dhash(img)
        if not goed_genoeg(img) or any(bin(hsh ^ o).count("1") <= 8 for o in hashes):
            os.remove(doel)
            continue
        hashes.append(hsh)
        nieuw.append({"code": code, "video": v["id"], "kort": kort, "titel": v["titel"], "tijd": f"{mm}:{ss:02d}",
                      "bestand": rel, "url": f"{RAW}/{rel}", "breed": img.width, "hoog": img.height,
                      "pagina": v.get("pagina", ""), "dhash": f"{hsh:016x}"})
    bladen = contactbladen(UIT, nieuw, kort)
    cat["videos"][v["id"]] = {"kort": kort, "titel": v["titel"], "pagina": v.get("pagina", ""), "gedownload_van": bron, "uitsnede": crop,
                              "stills": len(nieuw), "contactbladen": [f"{RAW}/{b}" for b in bladen],
                              "verwerkt": time.strftime("%Y-%m-%d")}
    cat["stills"].extend(nieuw)
    print(f"  {len(nieuw)} bruikbare stills bewaard")
    return True


def main():
    with open(os.path.join(HIER, "stills_bronnen.json"), encoding="utf-8") as f:
        start = json.load(f)["rockstar_ids"]
    cat = laad_catalogus()
    bronnen = rockstar_videos(start + EXTRA)
    hashes = [int(s["dhash"], 16) for s in cat["stills"] if s.get("dhash")]
    gedaan = 0
    for v in bronnen:
        if v["id"] in cat["videos"]:
            continue
        if verwerk(v, cat, hashes):
            gedaan += 1
            with open(os.path.join(UIT, "catalogus.json"), "w", encoding="utf-8") as f:
                json.dump(cat, f, ensure_ascii=False, indent=1)
    print(f"::notice::{gedaan} video's verwerkt, {len(cat['stills'])} stills in de catalogus")
    with open(os.path.join(UIT, "catalogus.json"), "w", encoding="utf-8") as f:
        json.dump(cat, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
