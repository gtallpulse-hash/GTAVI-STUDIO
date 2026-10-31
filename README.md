# GTAVI-STUDIO

Maakt elke ochtend automatisch de YouTube Shorts en Facebook-dia's voor GTA6 Centraal.

**Zo werkt het**
1. De scheduled task "GTA6 Centraal dagelijks" schrijft 2 artikels, publiceert ze en zet via Make (actie `renderopdracht`) een renderopdracht op gta6centraal.com: een klein beeldje `renderopdracht-<datum>` met de opdracht (JSON, base64) in de beschrijving.
2. De GitHub-workflow **Render Shorts** (`.github/workflows/render.yml`) kijkt 's ochtends elke 10 minuten of er een nieuwe opdracht is (`studio/haal_opdracht.py`), bewaart ze in `jobs/<datum>.json` en maakt de media. Een opdracht die rechtstreeks in `jobs/` gepusht wordt, werkt ook. Hij haalt de beelden op bij gta6centraal.com, maakt de dia's in de huisstijl (9:16 en 4:5) met `studio/gta6-social-renderer.js` en maakt van de 5 dia's een Short van ±15 seconden met rechtenvrije muziek (Kevin MacLeod, CC BY 4.0, zie `studio/muziek.json`). Lukt de muziek niet, dan wordt de video stil.
3. Alles komt op de branch **media** onder `<datum>/` met een `manifest.json` (de laatste 10 dagen blijven bewaard).
4. De scheduled task post daarna via Make (scenario 7727355) de Short op YouTube en de 4:5-dia's op Facebook.

Instagram en TikTok post je zelf, met de 9:16-dia's of de video en een trending liedje.

Handmatig opnieuw renderen: Actions → Render Shorts → Run workflow → datum invullen (opdracht in jobs/) of bij "van_site" (opdracht op de site).
