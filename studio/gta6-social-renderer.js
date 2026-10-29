/* GTA6Studio — renderer voor GTA6 Centraal (herbouwd 29 oktober 2026)
 *
 * Gebruik: plak dit hele bestand in de console van een pagina op https://gta6centraal.com
 * (ingelogd in WordPress), en voer daarna een renderblok uit, bv.:
 *
 *   await GTA6Studio.reelCarrousel({ naam: "druski-ali-g", dias: [ ... ] });
 *
 * Dia-types:
 *   { type:"cover", label, titel, accent, sub, beeld }
 *   { type:"punt",  nr, titel, tekst, beeld }
 *   { type:"vraag", titel, accent, sub, knop, beeld }   (knop = witte pil, standaard "HET HELE VERHAAL: LINK IN BIO")
 * beeld = media-ID uit de WordPress-mediabibliotheek (getal) of een volledige afbeeldings-URL.
 * accent = woord(en) uit de titel die roze kleuren. Bij "vraag" standaard het laatste woord.
 *
 * Resultaat: per dia een 9:16-PNG (1080x1920, voor de reel/TikTok) en een 4:5-PNG (1080x1350, voor Facebook),
 * geüpload naar de mediabibliotheek. Opties: { upload:true, download:false, formaten:["9x16","4x5"] }.
 */
(function () {
  const KLEUR = {
    roze: "#FF5DA1",
    oranje: "#FE7644",
    wit: "#F5F2F8",
    lavendel: "#C9CCE6",
    navy: "#161E35",
    pilTekst: "#1B2040",
  };
  const FORMATEN = {
    "9x16": { w: 1080, h: 1920, balkY: 170, logoY: 262, onderkant: 1488, coverOnderkant: 1490 },
    "4x5": { w: 1080, h: 1350, balkY: 64, logoY: 150, onderkant: 1250, coverOnderkant: 1250 },
  };
  const X = 70; // linkermarge
  const KAART_B = 838; // breedte van de glazen kaart
  const KAART_PAD = 57;

  // ---------- lettertypes ----------
  async function laadLettertypes() {
    const nodig = ['400 100px "Bebas Neue"', '400 40px "Inter"', '700 40px "Inter"'];
    const ok = () => nodig.every((f) => document.fonts.check(f));
    if (ok()) return;
    if (!document.querySelector("link[data-gta6studio]")) {
      const l = document.createElement("link");
      l.rel = "stylesheet";
      l.dataset.gta6studio = "1";
      l.href = "https://fonts.googleapis.com/css2?family=Bebas+Neue&family=Inter:wght@400;700&display=block";
      document.head.appendChild(l);
    }
    await Promise.all(nodig.map((f) => document.fonts.load(f).catch(() => {})));
    await document.fonts.ready;
    if (!ok()) console.warn("GTA6Studio: Bebas Neue of Inter niet geladen; open een artikelpagina van gta6centraal.com.");
  }

  // ---------- WordPress ----------
  let _nonce = null;
  async function nonce() {
    if (_nonce) return _nonce;
    if (window.wpApiSettings && wpApiSettings.nonce) return (_nonce = wpApiSettings.nonce);
    const r = await fetch("/wp-admin/admin-ajax.php?action=rest-nonce", { credentials: "same-origin" });
    const t = (await r.text()).trim();
    if (!r.ok || !t || t === "0" || t.length > 20) throw new Error("Niet ingelogd in WordPress: log eerst in en probeer opnieuw.");
    return (_nonce = t);
  }
  async function beeldUrl(beeld) {
    if (typeof beeld === "string" && !/^\d+$/.test(beeld.trim())) return beeld;
    const r = await fetch(`/wp-json/wp/v2/media/${beeld}?_fields=source_url`, { credentials: "same-origin" });
    if (!r.ok) throw new Error(`Media-ID ${beeld} niet gevonden (${r.status}).`);
    return (await r.json()).source_url;
  }
  function laadBeeld(url) {
    return new Promise((ok, fout) => {
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => ok(img);
      img.onerror = () => fout(new Error("Beeld laadt niet: " + url));
      img.src = url;
    });
  }
  async function upload(blob, bestandsnaam) {
    const r = await fetch("/wp-json/wp/v2/media", {
      method: "POST",
      credentials: "same-origin",
      headers: {
        "X-WP-Nonce": await nonce(),
        "Content-Disposition": `attachment; filename="${bestandsnaam}"`,
        "Content-Type": "image/png",
      },
      body: blob,
    });
    const j = await r.json();
    if (!r.ok) throw new Error(`Upload mislukt voor ${bestandsnaam}: ${j.message || r.status}`);
    return { id: j.id, url: j.source_url };
  }
  function download(blob, naam) {
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = naam;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => { URL.revokeObjectURL(a.href); a.remove(); }, 2000);
  }

  // ---------- tekenhulp ----------
  function rondeRechthoek(ctx, x, y, w, h, r) {
    ctx.beginPath();
    ctx.moveTo(x + r, y);
    ctx.arcTo(x + w, y, x + w, y + h, r);
    ctx.arcTo(x + w, y + h, x, y + h, r);
    ctx.arcTo(x, y + h, x, y, r);
    ctx.arcTo(x, y, x + w, y, r);
    ctx.closePath();
  }
  function tekenCover(ctx, img, w, h, filter) {
    const s = Math.max(w / img.width, h / img.height);
    const iw = img.width * s, ih = img.height * s;
    ctx.save();
    if (filter) ctx.filter = filter;
    ctx.drawImage(img, (w - iw) / 2, (h - ih) / 2, iw, ih);
    ctx.restore();
  }
  // woorden met per woord een vlag 'accent'
  // "GTA 6" (en "GTA VI") nooit over twee regels breken
  const bind = (t) => t.replace(/\b(GTA)[ ]+(6|VI)\b/gi, "$1\u00A0$2");
  const splits = (t) => bind(t).trim().split(/[ \t\n]+/);
  function woordenMetAccent(titel, accent) {
    const woorden = splits(titel);
    const vlag = woorden.map(() => false);
    if (accent) {
      const a = splits(accent).map((s) => s.toLowerCase());
      for (let i = 0; i + a.length <= woorden.length; i++) {
        const stuk = woorden.slice(i, i + a.length).map((s) => s.toLowerCase().replace(/[?!.,:;]+$/, ""));
        if (stuk.every((s, k) => s === a[k].replace(/[?!.,:;]+$/, ""))) {
          for (let k = 0; k < a.length; k++) vlag[i + k] = true;
          break;
        }
      }
    }
    return woorden.map((t, i) => ({ t, accent: vlag[i] }));
  }
  function breekWoorden(ctx, woorden, maxB) {
    const regels = [];
    let regel = [];
    for (const w of woorden) {
      const proef = regel.concat([w]).map((x) => x.t).join(" ");
      if (regel.length && ctx.measureText(proef).width > maxB) {
        regels.push(regel);
        regel = [w];
      } else regel.push(w);
    }
    if (regel.length) regels.push(regel);
    return regels;
  }
  function breekTekst(ctx, tekst, maxB) {
    return breekWoorden(ctx, tekst.trim().split(/\s+/).map((t) => ({ t })), maxB).map((r) => r.map((x) => x.t).join(" "));
  }
  function tekenRegel(ctx, regel, x, y) {
    let cx = x;
    const spatie = ctx.measureText(" ").width;
    for (const w of regel) {
      ctx.fillStyle = w.accent ? KLEUR.roze : KLEUR.wit;
      ctx.fillText(w.t, cx, y);
      cx += ctx.measureText(w.t).width + spatie;
    }
  }
  // titel passend maken: krimp tot hij in maxRegels past
  function pasTitel(ctx, woorden, maxB, groottes, maxRegels) {
    for (const g of groottes) {
      ctx.font = `400 ${g}px "Bebas Neue"`;
      const regels = breekWoorden(ctx, woorden, maxB);
      const breedOk = regels.every((r) => r.length > 1 || ctx.measureText(r[0].t).width <= maxB);
      if (regels.length <= maxRegels && breedOk) return { g, regels };
    }
    const g = groottes[groottes.length - 1];
    ctx.font = `400 ${g}px "Bebas Neue"`;
    return { g, regels: breekWoorden(ctx, woorden, maxB) };
  }

  function pil(ctx, tekst, x, yBoven, achtergrond, kleur) {
    ctx.font = '700 32px "Inter"';
    const t = tekst.toUpperCase();
    const b = ctx.measureText(t).width + 58;
    const h = 70;
    rondeRechthoek(ctx, x, yBoven, b, h, h / 2);
    ctx.fillStyle = achtergrond;
    ctx.fill();
    ctx.fillStyle = kleur;
    ctx.textBaseline = "middle";
    ctx.fillText(t, x + 29, yBoven + h / 2 + 1);
    ctx.textBaseline = "alphabetic";
    return h;
  }

  function achtergrond(ctx, img, F) {
    const { w, h } = F;
    ctx.fillStyle = KLEUR.navy;
    ctx.fillRect(0, 0, w, h);
    tekenCover(ctx, img, w, h, "brightness(0.82) saturate(1.05)");
    // donkere navy verloop van onder
    let g = ctx.createLinearGradient(0, h * 0.42, 0, h);
    g.addColorStop(0, "rgba(22,30,53,0)");
    g.addColorStop(0.45, "rgba(22,30,53,0.72)");
    g.addColorStop(0.75, "rgba(22,30,53,0.94)");
    g.addColorStop(1, "rgba(22,30,53,1)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, h);
    // lichte schaduw bovenaan voor de balkjes en het logo
    g = ctx.createLinearGradient(0, 0, 0, F.logoY + 120);
    g.addColorStop(0, "rgba(10,12,28,0.35)");
    g.addColorStop(1, "rgba(10,12,28,0)");
    ctx.fillStyle = g;
    ctx.fillRect(0, 0, w, F.logoY + 120);
  }

  function balkjesEnLogo(ctx, F, index, totaal) {
    const links = 60, rechts = F.w - 60, gat = 10;
    const bb = (rechts - links - gat * (totaal - 1)) / totaal;
    for (let i = 0; i < totaal; i++) {
      rondeRechthoek(ctx, links + i * (bb + gat), F.balkY, bb, 6, 3);
      ctx.fillStyle = i <= index ? KLEUR.wit : "rgba(245,242,248,0.38)";
      ctx.fill();
    }
    ctx.font = '400 54px "Bebas Neue"';
    ctx.fillStyle = KLEUR.wit;
    ctx.fillText("GTA6", X, F.logoY);
    const b = ctx.measureText("GTA6 ").width;
    ctx.fillStyle = KLEUR.oranje;
    ctx.fillText("CENTRAAL", X + b, F.logoY);
  }

  // glazen kaart: geblurde achtergrond + donkere laag + rand
  function kaart(ctx, img, F, y, h) {
    ctx.save();
    rondeRechthoek(ctx, X, y, KAART_B, h, 30);
    ctx.clip();
    tekenCover(ctx, img, F.w, F.h, "blur(26px) brightness(0.5)");
    ctx.fillStyle = "rgba(14,16,32,0.62)";
    ctx.fillRect(X, y, KAART_B, h);
    ctx.restore();
    rondeRechthoek(ctx, X + 0.5, y + 0.5, KAART_B - 1, h - 1, 30);
    ctx.strokeStyle = "rgba(255,255,255,0.13)";
    ctx.lineWidth = 2;
    ctx.stroke();
  }

  function subTekst(ctx, tekst, maxB) {
    ctx.font = '400 42px "Inter"';
    return breekTekst(ctx, tekst, maxB);
  }

  // ---------- dia's ----------
  function diaCover(ctx, d, img, F) {
    const maxB = F.w - X - 110;
    const woorden = woordenMetAccent(d.titel.toUpperCase(), d.accent && d.accent.toUpperCase());
    const { g, regels } = pasTitel(ctx, woorden, maxB, [150, 138, 126, 114], 3);
    const lh = g * 1.0;
    const subRegels = d.sub ? subTekst(ctx, d.sub, maxB - 60) : [];
    const subLh = 60;
    // onderaan verankerd
    let y = F.coverOnderkant - subRegels.length * subLh - (subRegels.length ? 26 : 0);
    const titelOnder = y;
    const titelBoven = titelOnder - regels.length * lh;
    // label-pil
    if (d.label) pil(ctx, d.label, X, titelBoven - 70 - 52 + 6, KLEUR.roze, KLEUR.wit);
    ctx.font = `400 ${g}px "Bebas Neue"`;
    regels.forEach((r, i) => tekenRegel(ctx, r, X, titelBoven + (i + 1) * lh - g * 0.12));
    ctx.font = '400 42px "Inter"';
    ctx.fillStyle = KLEUR.lavendel;
    subRegels.forEach((s, i) => ctx.fillText(s, X, titelOnder + 26 + (i + 1) * subLh - 16));
  }

  function diaPunt(ctx, d, img, F) {
    const binnenB = KAART_B - 2 * KAART_PAD;
    const woorden = woordenMetAccent(d.titel.toUpperCase(), d.accent && d.accent.toUpperCase());
    const { g, regels } = pasTitel(ctx, woorden, binnenB, [92, 84, 76], 3);
    const tekstRegels = d.tekst ? subTekst(ctx, d.tekst, binnenB - 20) : [];
    const nrH = 112, tlh = g * 0.98, slh = 60;
    const h = 58 + nrH + regels.length * tlh + 4 + tekstRegels.length * slh + 56;
    const y = F.onderkant - h;
    kaart(ctx, img, F, y, h);
    const tx = X + KAART_PAD;
    let cy = y + 58;
    ctx.font = '400 112px "Bebas Neue"';
    ctx.fillStyle = KLEUR.roze;
    ctx.fillText(String(d.nr).padStart(2, "0"), tx, cy + 92);
    cy += nrH;
    ctx.font = `400 ${g}px "Bebas Neue"`;
    regels.forEach((r, i) => tekenRegel(ctx, r, tx, cy + (i + 1) * tlh - g * 0.1));
    cy += regels.length * tlh + 4;
    ctx.font = '400 42px "Inter"';
    ctx.fillStyle = KLEUR.lavendel;
    tekstRegels.forEach((s, i) => ctx.fillText(s, tx, cy + (i + 1) * slh - 16));
  }

  function diaVraag(ctx, d, img, F) {
    const binnenB = KAART_B - 2 * KAART_PAD;
    const titel = d.titel.toUpperCase();
    const accent = d.accent ? d.accent.toUpperCase() : splits(titel).pop();
    const woorden = woordenMetAccent(titel, accent);
    const { g, regels } = pasTitel(ctx, woorden, binnenB, [118, 108, 98, 90], 4);
    const subRegels = d.sub ? subTekst(ctx, d.sub, binnenB - 20) : [];
    const tlh = g * 0.98, slh = 60;
    const h = 64 + regels.length * tlh + 6 + subRegels.length * slh + 56;
    const y = F.onderkant - h;
    kaart(ctx, img, F, y, h);
    pil(ctx, d.knop || "Het hele verhaal: link in bio", X, y - 70 - 48, KLEUR.wit, KLEUR.pilTekst);
    const tx = X + KAART_PAD;
    let cy = y + 64;
    ctx.font = `400 ${g}px "Bebas Neue"`;
    regels.forEach((r, i) => tekenRegel(ctx, r, tx, cy + (i + 1) * tlh - g * 0.1));
    cy += regels.length * tlh + 6;
    ctx.font = '400 42px "Inter"';
    ctx.fillStyle = KLEUR.lavendel;
    subRegels.forEach((s, i) => ctx.fillText(s, tx, cy + (i + 1) * slh - 16));
  }

  const TEKEN = { cover: diaCover, punt: diaPunt, vraag: diaVraag };

  async function renderDia(d, index, totaal, formaat) {
    const F = FORMATEN[formaat];
    const c = document.createElement("canvas");
    c.width = F.w;
    c.height = F.h;
    const ctx = c.getContext("2d");
    const img = await laadBeeld(await beeldUrl(d.beeld));
    achtergrond(ctx, img, F);
    balkjesEnLogo(ctx, F, index, totaal);
    const f = TEKEN[d.type];
    if (!f) throw new Error(`Onbekend dia-type "${d.type}" (gebruik cover, punt of vraag).`);
    f(ctx, d, img, F);
    return new Promise((ok) => c.toBlob(ok, "image/png"));
  }

  async function reelCarrousel({ naam, dias }, opties = {}) {
    const o = Object.assign({ upload: true, download: false, formaten: ["9x16", "4x5"] }, opties);
    if (!naam || !Array.isArray(dias) || !dias.length) throw new Error("Geef een naam en een lijst dias.");
    await laadLettertypes();
    const resultaat = { naam };
    for (const formaat of o.formaten) {
      resultaat[formaat] = [];
      for (let i = 0; i < dias.length; i++) {
        const blob = await renderDia(dias[i], i, dias.length, formaat);
        const bestand = `${naam}-${formaat}-${i + 1}.png`;
        const item = { dia: i + 1, bestand, blob };
        if (o.upload) Object.assign(item, await upload(blob, bestand));
        if (o.download) download(blob, bestand);
        resultaat[formaat].push(item);
        console.log(`GTA6Studio: ${bestand}${item.url ? " → " + item.url : ""}`);
      }
    }
    // klaar voor Make-scenario 7727355 (Facebook met de 4:5-dia's)
    if (resultaat["4x5"] && resultaat["4x5"][0] && resultaat["4x5"][0].url) {
      resultaat.fb_photos = resultaat["4x5"].map((x) => ({ type: "url", url: x.url }));
    }
    if (resultaat["9x16"] && resultaat["9x16"][0] && resultaat["9x16"][0].url) {
      resultaat.reel_urls = resultaat["9x16"].map((x) => x.url);
    }
    return resultaat;
  }

  window.GTA6Studio = Object.assign(window.GTA6Studio || {}, {
    versie: "2026-10-29",
    reelCarrousel,
    renderDia,
    laadLettertypes,
  });
  console.log("GTA6Studio geladen (versie 2026-10-29): GTA6Studio.reelCarrousel({naam, dias})");
})();
