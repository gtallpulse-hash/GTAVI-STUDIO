"""Haalt de renderopdracht van <datum> op van gta6centraal.com.

De scheduled task zet ze via Make als klein beeldje 'renderopdracht-<datum>' in de mediabibliotheek,
met de JSON in base64 in de beschrijving. Gebruik: python studio/haal_opdracht.py 2026-11-01 jobs/2026-11-01.json
Exitcode 0 = gevonden en geschreven, 2 = (nog) niet gevonden.
"""
import base64, html, json, re, sys, urllib.request

d, doel = sys.argv[1], sys.argv[2]
naam = f"renderopdracht-{d}"
url = (f"https://gta6centraal.com/wp-json/wp/v2/media?search={naam}&orderby=id&order=desc"
       f"&per_page=10&_fields=id,title,description&t={d}")
req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 GTAVI-STUDIO", "Cache-Control": "no-cache"})
try:
    items = json.load(urllib.request.urlopen(req, timeout=60))
except Exception as e:  # noqa: BLE001
    print("Site niet bereikbaar:", e); sys.exit(2)
for m in items:
    titel = html.unescape(m.get("title", {}).get("rendered", ""))
    if not titel.startswith(naam):
        continue
    ruw = html.unescape(re.sub(r"<[^>]+>", "", m.get("description", {}).get("rendered", "")))
    ruw = re.sub(r"\s+", "", ruw.replace("×", "x"))
    try:
        tekst = base64.b64decode(ruw + "=" * (-len(ruw) % 4)).decode("utf-8")
        job = json.loads(tekst)
    except Exception as e:  # noqa: BLE001
        print(f"Media {m['id']} is geen geldige opdracht: {e}"); continue
    if job.get("datum") != d:
        print(f"Media {m['id']} heeft datum {job.get('datum')}, verwacht {d}"); continue
    with open(doel, "w", encoding="utf-8") as f:
        json.dump(job, f, ensure_ascii=False, indent=1)
    print(f"Opdracht gevonden in media {m['id']}: {len(job.get('reels', []))} reels -> {doel}")
    sys.exit(0)
print(f"Nog geen {naam} op de site."); sys.exit(2)
