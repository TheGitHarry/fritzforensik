"""HTML-Rendering — self-contained Report, 12 Sektionen.

Übernommen aus dem PoC (``_material/poc/build_report.py``): CSS, JS-Filter/-Druck,
Sektions-/Tabellen-/Herkunfts-Renderer. Angepasst an fritzreport:
- **3-Grade-System** (D1/D2/D3, kein D4),
- **SHA-256-Integritäts-Badge** je Datei in der Chain of Custody,
- **neue Sektion 10 „Vollständige Timeline"** (quellenübergreifend),
- **parametrisierte Kopf-Felder** (CaseID/ItemID/SB/Date),
- **Sekunden-Zeitstempel** (ms nur in Herkunft/Sortierung).
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import html

from . import __version__
from .model import GRADE_LABEL, GRADE_SCHEMA, NO_AP, Model

# ───────────────────────── CSS (aus PoC, 3 Grade) ────────────────────────────
CSS = """
:root {
  --fg:#1a1e24; --fg-soft:#5a6068; --fg-dim:#868d95;
  --bg:#fff; --bg-alt:#f6f7f9; --bg-sunk:#eceef1;
  --bd:#dcdfe4; --bd-soft:#ebedf0;
  --accent:#00437a; --warn:#9a4400; --err:#c0000a; --ok:#175c3a;
  --gd1:#175c3a; --gd1b:#e6f3ec; --gd2:#0f4e6f; --gd2b:#e3eff6;
  --gd3:#565c63; --gd3b:#ecedf0;
}
@media (prefers-color-scheme: dark) {
  :root {
    --fg:#e6e8ea; --fg-soft:#a3aab2; --fg-dim:#7d848c;
    --bg:#15181c; --bg-alt:#1c2026; --bg-sunk:#23282f;
    --bd:#333941; --bd-soft:#272c33;
    --accent:#5aa9e6; --warn:#e0913f; --err:#e06666; --ok:#7fd6a6;
    --gd1:#7fd6a6; --gd1b:#14301f; --gd2:#7ec4e8; --gd2b:#122733;
    --gd3:#a8afb7; --gd3b:#262a30;
  }
}
*{box-sizing:border-box}
html,body{margin:0;padding:0;background:var(--bg);color:var(--fg);
  font:14px/1.55 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,Roboto,Arial,sans-serif}
body{padding-top:150px}
main{max-width:1500px;margin:0 auto;padding:20px 24px 80px}
h1{font-size:21px;margin:0 0 3px;letter-spacing:-0.01em}
h3{font-size:13px;margin:18px 0 6px;color:var(--fg-soft);font-weight:600;
  text-transform:uppercase;letter-spacing:.05em}
.sub{color:var(--fg-soft);font-size:13px;margin-bottom:16px}
.mono{font-family:ui-monospace,SFMono-Regular,Menlo,Consolas,monospace;font-size:12px}
.hash{font-size:11px;color:var(--fg-soft);word-break:break-all}
.num{text-align:right;font-variant-numeric:tabular-nums}
.unknown{color:var(--fg-dim);font-style:italic}
.ok{color:var(--ok);font-weight:600}
.err{color:var(--err);font-weight:700}

#fbar{position:fixed;top:0;left:0;right:0;z-index:50;background:var(--bg);
  border-bottom:1px solid var(--bd);box-shadow:0 1px 8px rgba(0,0,0,.06)}
#fbar .in{max-width:1500px;margin:0 auto;padding:10px 24px 8px}
#fbar .row{display:flex;flex-wrap:wrap;gap:10px 16px;align-items:flex-end}
#fbar label{display:flex;flex-direction:column;gap:3px;font-size:10px;
  color:var(--fg-dim);text-transform:uppercase;letter-spacing:.06em;font-weight:600}
#fbar input,#fbar select{font:inherit;font-size:13px;padding:5px 7px;border:1px solid var(--bd);
  border-radius:4px;background:var(--bg);color:var(--fg);min-width:150px}
#fbar input:focus,#fbar select:focus{outline:2px solid var(--accent);outline-offset:-1px;border-color:transparent}
#fbar input[type=datetime-local]{min-width:190px}
.gtogs{display:flex;gap:4px}
.gtog{cursor:pointer;user-select:none;padding:5px 9px;border-radius:4px;font-size:11px;
  font-weight:700;opacity:.32;border:1px solid transparent;transition:opacity .1s}
.gtog.on{opacity:1}
.gtog[data-grade=D1]{background:var(--gd1b);color:var(--gd1)}
.gtog[data-grade=D2]{background:var(--gd2b);color:var(--gd2)}
.gtog[data-grade=D3]{background:var(--gd3b);color:var(--gd3)}
.btn{font:inherit;font-size:12px;padding:6px 11px;border-radius:4px;cursor:pointer;
  border:1px solid var(--bd);background:var(--bg-alt);color:var(--fg)}
.btn:hover{background:var(--bg-sunk)}
.btn.primary{background:var(--accent);border-color:var(--accent);color:#fff}
.btn.primary:hover{filter:brightness(1.1)}
#fstate{font-size:12px;color:var(--fg-dim);margin-top:7px;min-height:16px}
#fstate.act{color:var(--warn);font-weight:500}

#toc{background:var(--bg-alt);border:1px solid var(--bd);border-radius:6px;padding:6px 8px;margin:0 0 18px}
#toc ol{list-style:none;margin:0;padding:0;columns:2;column-gap:24px}
#toc li{break-inside:avoid}
#toc a{display:flex;align-items:baseline;gap:8px;padding:5px 8px;border-radius:4px;
  color:var(--fg);text-decoration:none;font-size:13px}
#toc a:hover{background:var(--bg-sunk);color:var(--accent)}
.tocnum{color:var(--fg-dim);font-variant-numeric:tabular-nums;min-width:16px;font-size:12px}
.toccount{margin-left:auto;font-size:11px;color:var(--fg-dim);font-variant-numeric:tabular-nums}
.toccount.filt{color:var(--warn);font-weight:600}

details.section{border:1px solid var(--bd);border-radius:6px;margin-bottom:8px;background:var(--bg)}
details.section > summary{display:flex;align-items:center;gap:10px;padding:11px 14px;
  cursor:pointer;list-style:none;user-select:none;border-radius:6px}
details.section > summary::-webkit-details-marker{display:none}
details.section > summary::before{content:"\\25B8";color:var(--fg-dim);font-size:11px;
  transition:transform .12s;display:inline-block;width:10px}
details.section[open] > summary::before{transform:rotate(90deg)}
details.section > summary:hover{background:var(--bg-alt)}
details.section[open] > summary{border-bottom:1px solid var(--bd-soft);border-radius:6px 6px 0 0;background:var(--bg-alt)}
.secnum{color:var(--fg-dim);font-size:12px;font-variant-numeric:tabular-nums;min-width:18px}
.sectitle{font-weight:600;font-size:14.5px}
.seccount{margin-left:auto;font-size:11.5px;color:var(--fg-dim);font-variant-numeric:tabular-nums;
  background:var(--bg-sunk);padding:2px 8px;border-radius:10px}
.seccount.filt{color:var(--warn);font-weight:600}
.secbody{padding:4px 14px 14px;overflow-x:auto}

table{width:100%;border-collapse:collapse;margin:6px 0 4px}
table.kv{width:auto;min-width:480px}
table.stat{width:auto;min-width:260px}
th,td{text-align:left;padding:5px 9px;border-bottom:1px solid var(--bd-soft);vertical-align:top}
thead th{background:var(--bg-alt);border-bottom:1px solid var(--bd);font-size:10.5px;
  font-weight:700;text-transform:uppercase;letter-spacing:.05em;color:var(--fg-dim);white-space:nowrap}
table.kv th{background:var(--bg-alt);font-weight:500;color:var(--fg-soft);width:34%;
  text-transform:none;letter-spacing:0;font-size:13px}
tr.hidden{display:none}
td.msg{font-size:12.5px;min-width:340px}
td.exp,th.exp{width:26px;padding:5px 2px 5px 8px}
.expbtn{border:0;background:none;color:var(--fg-dim);cursor:pointer;font-size:10px;
  padding:2px 4px;border-radius:3px;line-height:1}
.expbtn:hover{background:var(--bg-sunk);color:var(--accent)}
.expbtn[aria-expanded=true]{transform:rotate(90deg)}
.grades{white-space:nowrap;width:1%}
.grade{display:inline-block;padding:1px 5px;border-radius:3px;font-size:10px;
  font-weight:700;margin-right:2px;letter-spacing:.02em}
.gD1{background:var(--gd1b);color:var(--gd1)}
.gD2{background:var(--gd2b);color:var(--gd2)}
.gD3{background:var(--gd3b);color:var(--gd3)}

tr.originrow > td{background:var(--bg-alt);padding:0;border-bottom:2px solid var(--bd)}
.origin{padding:10px 12px 10px 40px;display:flex;flex-direction:column;gap:5px}
.orow{display:flex;align-items:flex-start;gap:9px}
.olab{font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.05em;
  color:var(--fg-dim);min-width:112px;padding-top:2px;flex-shrink:0}
.odim{color:var(--fg-dim);font-weight:400}
.orow .mono{flex:1;word-break:break-all}
.oraw pre{flex:1;margin:0;background:var(--bg);border:1px solid var(--bd-soft);border-radius:4px;
  padding:7px 9px;max-height:220px;overflow:auto;font-size:11px;white-space:pre-wrap;word-break:break-word}
.cp{font:inherit;font-size:10.5px;padding:2px 7px;border:1px solid var(--bd);background:var(--bg);
  color:var(--fg-soft);border-radius:3px;cursor:pointer;flex-shrink:0}
.cp:hover{background:var(--bg-sunk);color:var(--fg)}
.cp.done{background:var(--gd1b);color:var(--gd1);border-color:var(--gd1)}

.notice{padding:8px 11px;border-left:3px solid var(--warn);background:var(--bg-alt);
  margin:8px 0 12px;font-size:12.5px;color:var(--fg-soft);border-radius:0 4px 4px 0}
.notice-info{border-left-color:var(--accent)}
.banner{padding:10px 13px;border:1px solid var(--bd);border-left:3px solid var(--accent);
  background:var(--bg-alt);border-radius:0 5px 5px 0;font-size:12.5px;color:var(--fg-soft);margin:0 0 16px}
.banner.err{border-left-color:var(--err);color:var(--fg)}
#pbanner{display:none}

@media print {
  :root{
    --fg:#000;--fg-soft:#222;--fg-dim:#444;--bg:#fff;--bg-alt:#f2f2f2;--bg-sunk:#e8e8e8;
    --bd:#000;--bd-soft:#b0b0b0;--accent:#000;--warn:#000;--err:#000;--ok:#000;
    --gd1:#000;--gd1b:#fff;--gd2:#000;--gd2b:#fff;--gd3:#000;--gd3b:#fff;
  }
  @page { margin: 14mm 12mm 16mm; }
  html,body{background:#fff;color:#000}
  body{padding-top:0 !important;font-size:9pt}
  main{padding:0;max-width:none}
  #fbar,#toc{display:none}
  #pbanner{display:block !important;border:1.5pt solid #000;padding:8pt;margin:0 0 10pt;
    background:#fff;color:#000;border-radius:0;font-size:9pt}
  h1{font-size:14pt;margin-bottom:2pt}
  .sub{font-size:8.5pt;margin-bottom:8pt}
  .banner{border:0.5pt solid #666;border-left:2pt solid #000;font-size:8pt;padding:6pt;margin-bottom:10pt}
  details.section{border:none;border-radius:0;margin:0 0 10pt;background:none;break-inside:auto;page-break-inside:auto}
  details.section > summary,details.section[open] > summary{background:none !important;border:none;
    border-bottom:1.2pt solid #000;border-radius:0;padding:0 0 3pt;margin:0 0 5pt;
    break-after:avoid;page-break-after:avoid;break-inside:avoid}
  details.section > summary::before{display:none}
  .sectitle{font-size:11.5pt}
  .seccount{background:none;padding:0;font-size:8.5pt}
  .secbody{padding:0;overflow:visible !important}
  table{break-inside:auto;page-break-inside:auto;margin:0 0 6pt}
  thead{display:table-header-group;break-inside:avoid;break-after:avoid}
  tbody{break-inside:auto}
  tr{break-inside:avoid;page-break-inside:avoid}
  thead th{background:#eee !important;border-bottom:1pt solid #000;font-size:7.5pt;
    -webkit-print-color-adjust:exact;print-color-adjust:exact}
  td,th{border-bottom:0.4pt solid #bbb;padding:3pt 5pt}
  table.kv th{background:#f6f6f6 !important;-webkit-print-color-adjust:exact;print-color-adjust:exact}
  td.msg{min-width:0}
  .mono{font-size:7.5pt}
  .hash{font-size:6.5pt}
  tr.originrow{display:none !important}
  td.exp,th.exp,.expbtn{display:none !important}
  .oraw pre{max-height:none;overflow:visible}
  .grade{border:0.4pt solid #000;background:none !important;color:#000 !important;font-size:7pt;padding:0 3pt}
  .notice{border:0.4pt solid #666;background:none;font-size:8pt;padding:5pt}
  a{color:#000;text-decoration:none}
}
"""

# ───────────────────────── JS (aus PoC, 3 Grade) ─────────────────────────────
JS = """
"use strict";
(() => {
  const $ = id => document.getElementById(id);
  const fMac = $("f-mac"), fName = $("f-name"), fPhone = $("f-phone"),
        fFrom = $("f-from"), fTo = $("f-to"), fAp = $("f-ap"),
        fState = $("fstate"), pFilters = $("pfilters");
  const gtogs = [...document.querySelectorAll(".gtog")];
  const rows = [...document.querySelectorAll("tr.datarow")];
  const grades = new Set(["D1", "D2", "D3"]);

  const fbar = $("fbar");
  const setPad = () => { document.body.style.paddingTop = (fbar.offsetHeight + 14) + "px"; };
  setPad();
  if (window.ResizeObserver) new ResizeObserver(setPad).observe(fbar);
  window.addEventListener("resize", setPad);

  document.addEventListener("click", e => {
    const btn = e.target.closest(".expbtn");
    if (!btn) return;
    const tr = btn.closest("tr");
    const orig = tr.nextElementSibling;
    if (!orig || !orig.classList.contains("originrow")) return;
    const open = btn.getAttribute("aria-expanded") === "true";
    btn.setAttribute("aria-expanded", String(!open));
    orig.hidden = open;
  });

  document.addEventListener("click", async e => {
    const btn = e.target.closest(".cp");
    if (!btn) return;
    const text = btn.hasAttribute("data-cp-pre")
      ? btn.parentElement.querySelector("pre").textContent
          .split("\\n").map(l => l.replace(/^\\s*\\d+\\s\\u2502\\s?/, "")).join("\\n")
      : btn.dataset.cp;
    try { await navigator.clipboard.writeText(text); }
    catch {
      const ta = document.createElement("textarea");
      ta.value = text; document.body.appendChild(ta);
      ta.select(); document.execCommand("copy"); ta.remove();
    }
    const old = btn.textContent;
    btn.textContent = "kopiert \\u2713"; btn.classList.add("done");
    setTimeout(() => { btn.textContent = old; btn.classList.remove("done"); }, 1100);
  });

  document.querySelectorAll("#toc a").forEach(a => a.addEventListener("click", e => {
    e.preventDefault();
    const sec = $(a.dataset.target);
    if (!sec) return;
    sec.open = true;
    sec.scrollIntoView({behavior: "smooth", block: "start"});
  }));

  gtogs.forEach(g => g.addEventListener("click", () => {
    const k = g.dataset.grade;
    grades.has(k) ? (grades.delete(k), g.classList.remove("on"))
                  : (grades.add(k), g.classList.add("on"));
    apply();
  }));

  [fMac, fName, fPhone, fFrom, fTo, fAp].forEach(el => el.addEventListener("input", apply));

  $("b-reset").addEventListener("click", () => {
    [fMac, fName, fPhone, fFrom, fTo, fAp].forEach(el => el.value = "");
    ["D1","D2","D3"].forEach(g => grades.add(g));
    gtogs.forEach(g => g.classList.add("on"));
    apply();
  });

  $("b-expand").addEventListener("click", () => {
    const secs = [...document.querySelectorAll("details.section")];
    const anyClosed = secs.some(s => !s.open);
    secs.forEach(s => s.open = anyClosed);
    $("b-expand").textContent = anyClosed ? "Alle zuklappen" : "Alle aufklappen";
  });

  $("b-print").addEventListener("click", () => {
    document.querySelectorAll("details.section").forEach(s => {
      const rs = s.querySelectorAll("tr.datarow");
      s.open = rs.length === 0 || [...rs].some(r => !r.classList.contains("hidden"));
    });
    setTimeout(() => window.print(), 60);
  });

  function apply() {
    const mac = fMac.value.trim().toUpperCase();
    const name = fName.value.trim().toUpperCase();
    const phone = fPhone.value.trim().replace(/[\\s\\-\\/]/g, "");
    const from = fFrom.value ? new Date(fFrom.value).getTime() : null;
    const to = fTo.value ? new Date(fTo.value).getTime() : null;
    const ap = fAp.value;
    let hidden = 0;

    for (const tr of rows) {
      const d = tr.dataset;
      let vis = true;
      if (mac && !(d.mac || "").includes(mac)) vis = false;
      if (vis && name && !(d.name || "").includes(name)) vis = false;
      if (vis && phone && !((d.phone || "").replace(/[\\s\\-\\/]/g, "")).includes(phone)) vis = false;
      if (vis && ap && d.ap !== ap) vis = false;
      if (vis && (from !== null || to !== null) && d.iso) {
        const t = new Date(d.iso).getTime();
        if (from !== null && t < from) vis = false;
        if (to !== null && t > to) vis = false;
      }
      if (vis) {
        const gs = (d.grades || "").split(",").filter(Boolean);
        // Zeilen ohne Grade (reine Rohdaten) sind vom Grade-Filter nicht betroffen.
        if (gs.length && !gs.some(g => grades.has(g))) vis = false;
      }

      tr.classList.toggle("hidden", !vis);
      const orig = tr.nextElementSibling;
      if (orig && orig.classList.contains("originrow")) {
        orig.classList.toggle("hidden", !vis);
        if (!vis) {
          orig.hidden = true;
          const b = tr.querySelector(".expbtn");
          if (b) b.setAttribute("aria-expanded", "false");
        }
      }
      if (!vis) hidden++;
    }

    document.querySelectorAll("details.section").forEach(sec => {
      const rs = sec.querySelectorAll("tr.datarow");
      const cnt = sec.querySelector(".seccount");
      const toc = document.querySelector(`.toccount[data-toc="${sec.id}"]`);
      if (!rs.length) { if (toc) toc.textContent = ""; return; }
      const vis = [...rs].filter(r => !r.classList.contains("hidden")).length;
      const filtered = vis < rs.length;
      const noun = (cnt && cnt.dataset.noun) || "Zeilen";
      const txt = filtered ? `${vis} von ${rs.length}` : `${rs.length} ${noun}`;
      if (cnt) { cnt.textContent = txt; cnt.classList.toggle("filt", filtered); }
      if (toc) { toc.textContent = filtered ? `${vis}/${rs.length}` : String(rs.length);
                 toc.classList.toggle("filt", filtered); }
    });

    const act = [];
    if (mac) act.push("MAC \\u2287 " + mac);
    if (name) act.push("Name \\u2287 " + fName.value.trim());
    if (phone) act.push("Rufnummer \\u2287 " + fPhone.value.trim());
    if (fFrom.value) act.push("ab " + fFrom.value.replace("T", " "));
    if (fTo.value) act.push("bis " + fTo.value.replace("T", " "));
    if (ap) act.push("AP = " + ap);
    if (grades.size < 3) act.push("Grade " + [...grades].sort().join("+"));
    if (!act.length) {
      fState.textContent = "Keine Filter aktiv \\u2014 alle Datenpunkte sichtbar.";
      fState.classList.remove("act");
      pFilters.textContent = "keine \\u2014 alle Zeilen";
    } else {
      fState.textContent = "Aktive Filter: " + act.join(" \\u00b7 ") + "  \\u2014  " + hidden + " Zeilen ausgeblendet.";
      fState.classList.add("act");
      pFilters.textContent = act.join(" \\u00b7 ");
    }
  }

  apply();
})();
"""


# ───────────────────────── Render-Helfer ─────────────────────────────────────

def esc(x) -> str:
    return html.escape(str(x)) if x is not None else ""


def badges(grades) -> str:
    return "".join(
        f'<span class="grade g{g}" title="{esc(GRADE_LABEL.get(g, g))}">{g}</span>'
        for g in grades
    )


def _duration(von: str, bis: str) -> str:
    """ISO-Spanne → „6 min 27 s"; leer, wenn nicht berechenbar."""
    try:
        a = _dt.datetime.strptime(von, "%Y-%m-%dT%H:%M:%SZ")
        b = _dt.datetime.strptime(bis, "%Y-%m-%dT%H:%M:%SZ")
    except (ValueError, TypeError):
        return ""
    sek = int((b - a).total_seconds())
    if sek < 0:
        return ""
    if sek < 60:
        return f"{sek} s"
    if sek < 3600:
        return f"{sek // 60} min {sek % 60} s"
    return f"{sek // 3600} h {(sek % 3600) // 60} min"


def _secured_rows(bundle, m) -> list[tuple]:
    """Metadaten-Zeilen zum Sicherungszeitraum (erster bis letzter Datenabruf).

    Aus den Log-Markern protokolliert oder aus den ``extracted_at`` der Datensätze
    abgeleitet. Der abgeleitete Fall trägt ein **D3**-Badge, damit ein gerechneter
    Zeitraum im Gutachten nicht wie ein protokollierter aussieht.
    """
    if not bundle.secured_from and not bundle.secured_to:
        # Nichts ermittelbar (leeres oder beschädigtes Bundle) — bisherige
        # Einzelangabe behalten, damit nichts schlechter dasteht als vorher.
        return [("Export erstellt am", m.meta.get("extracted_at", ""))]

    badge = "" if bundle.secured_source == "log" else " " + badges(["D3"])
    von = bundle.secured_from.replace("T", " ").replace("Z", " UTC")
    bis = (bundle.secured_to.replace("T", " ").replace("Z", " UTC")
           if bundle.secured_to else "nicht protokolliert (Lauf abgebrochen)")

    rows = [("Gesichert von", von, badge), ("Gesichert bis", bis, badge)]
    dauer = _duration(bundle.secured_from, bundle.secured_to)
    if dauer:
        rows.append(("Dauer", dauer, badge))
    return rows


def data_attrs(rec) -> str:
    return (
        f' data-mac="{esc((rec.get("mac") or "").upper())}"'
        f' data-iso="{esc(rec.get("f_iso") or "")}"'
        f' data-ap="{esc(rec.get("f_ap") or "")}"'
        f' data-name="{esc((rec.get("f_name") or "").upper())}"'
        f' data-phone="{esc(rec.get("f_phone") or "")}"'
        f' data-grades="{esc(",".join(rec.get("grades", [])))}"'
    )


def origin_row(rec, colspan) -> str:
    o = rec["origin"]
    if o.get("line"):
        body = "\n".join(
            f"{o['line'] + n:>6} │ {ln}"
            for n, ln in enumerate(o["text"].split("\n"))
        )
        fundstelle = (f'Zeile {o["line"]}–{o["line_end"]}'
                      if o.get("line_end") and o["line_end"] != o["line"] else f'Zeile {o["line"]}')
        ref = f'{o["file"]}:{o["line"]}'
    else:
        body = o.get("text", "")
        fundstelle = "—"
        ref = o["file"]
    idx_html = (f'<span class="odim"> · Datensatz {o["idx"]} von {o["total"]}</span>'
                if o.get("idx") else "")
    return (
        f'<tr class="originrow" hidden><td colspan="{colspan}">'
        f'<div class="origin">'
        f'<div class="orow"><span class="olab">Quelldatei</span>'
        f'<span class="mono">{esc(o["file"])}</span>'
        f'<button class="cp" data-cp="{esc(o["file"])}" title="Dateinamen kopieren">kopieren</button></div>'
        f'<div class="orow"><span class="olab">Fundstelle</span>'
        f'<span class="mono"><strong>{esc(fundstelle)}</strong>{idx_html}</span>'
        f'<button class="cp" data-cp="{esc(ref)}" title="Referenz Datei:Zeile kopieren">Referenz kopieren</button></div>'
        f'<div class="orow"><span class="olab">SHA256 der Datei</span>'
        f'<span class="mono hash">{esc(o.get("sha",""))}</span>'
        f'<button class="cp" data-cp="{esc(o.get("sha",""))}" title="Hash kopieren">kopieren</button></div>'
        f'<div class="orow oraw"><span class="olab">Original-Auszug</span>'
        f'<pre class="mono">{html.escape(body, quote=False)}</pre>'
        f'<button class="cp" data-cp-pre title="Auszug ohne Zeilennummern kopieren">kopieren</button></div>'
        f'</div></td></tr>'
    )


def render_rows(records, cells_fn, colspan) -> str:
    out = []
    for rec in records:
        out.append(
            f'<tr class="datarow"{data_attrs(rec)}>'
            f'<td class="exp"><button class="expbtn" aria-expanded="false" title="Herkunft anzeigen">▸</button></td>'
            + cells_fn(rec)
            + f'<td class="grades">{badges(rec["grades"])}</td></tr>'
        )
        out.append(origin_row(rec, colspan))
    return "".join(out)


def section(sid, num, title, key, count, body, note="", noun="Zeilen") -> str:
    note_html = f'<div class="notice notice-info">{note}</div>' if note else ""
    label = f"{count} {noun}" if count is not None else ""
    return (
        f'<details class="section" id="{sid}">'
        f'<summary><span class="secnum">{num}</span>'
        f'<span class="sectitle">{esc(title)}</span>'
        f'<span class="seccount" data-count="{key}" data-noun="{esc(noun)}">{label}</span></summary>'
        f'<div class="secbody">{note_html}{body}</div>'
        f'</details>'
    )


def table(tid, headers, rows_html) -> str:
    th = "".join(f"<th>{esc(h)}</th>" for h in headers)
    return (f'<table id="{tid}"><thead><tr><th class="exp"></th>{th}<th>Belegt</th></tr></thead>'
            f'<tbody>{rows_html}</tbody></table>')


# ───────────────────────── Zellen-Renderer je Sektion ────────────────────────

def c_hosts(h):
    return (f'<td class="mono">{esc(h["mac"])}</td><td class="mono">{esc(h["ip"])}</td>'
            f'<td>{esc(h["name"])}</td><td>{esc(h["iface"])}</td>'
            f'<td>{"aktiv" if h["active"] else "offline"}</td>'
            f'<td>{"Gast" if h["guest"] else "regulär"}</td>')


def c_mesh(n):
    return (f'<td>{esc(n["name"])}</td><td>{esc(n["model"])}</td><td class="mono">{esc(n["mac"])}</td>'
            f'<td>{esc(n["role"])}</td>'
            f'<td>{"<strong>ja</strong>" if n["is_ap"] else "nein"}</td>'
            f'<td>{esc(n["firmware"])}</td>')


def c_wifi(w):
    return (f'<td class="mono">{esc(w["mac"])}</td><td>{esc(w["name"])}</td>'
            f'<td class="mono">{esc(w["ipv4"])}</td><td>{esc(w["interface"])}</td>'
            f'<td class="{"" if w["ap_is_mesh"] else "unknown"}">{esc(w["ap_display"])}</td>'
            f'<td>{esc(w["status"])}</td><td class="mono">{esc(w["last_seen_iso"])}</td>')


def c_calls(c):
    return (f'<td class="mono">{esc(c["iso"])}</td><td>{esc(c["typ"])}</td>'
            f'<td class="mono">{esc(c["rufnummer"])}</td><td>{esc(c["name"])}</td>'
            f'<td>{esc(c["region"])}</td><td>{esc(c["nebenstelle"])}</td>'
            f'<td>{esc(c["eigene"])}</td><td class="num">{esc(c["dauer"])}</td>')


def c_pb(p):
    return (f'<td>{esc(p["name"])}</td><td class="mono">{esc(p["numbers"])}</td><td>{esc(p["book"])}</td>')


def c_events(e):
    return (f'<td class="mono">{esc(e["iso"])}</td><td>{esc(e["category"])}</td>'
            f'<td class="num">{esc(e["id"])}</td><td class="mono">{esc(e["mac"])}</td>'
            f'<td class="msg">{esc(e["message"])}</td>')


def c_wlan(w):
    return (f'<td class="mono">{esc(w["display"])}</td><td class="mono">{esc(w["mac"])}</td>'
            f'<td>{esc(w["event_de"])}</td><td>{esc(w["band"])}</td><td>{esc(w["ap"])}</td>')


def c_timeline(t):
    return (f'<td class="mono">{esc(t["display"])}</td><td>{esc(t["quelle"])}</td>'
            f'<td class="mono">{esc(t["mac"])}</td><td class="msg">{esc(t["detail"])}</td>')


# ───────────────────────── Timeline (quellenübergreifend) ────────────────────

def build_timeline(model: Model, proofs: list) -> list:
    """Alle zeitgestempelten Datenpunkte aus allen Quellen in einer Achse."""
    tl = []

    def add(sortkey, iso, display, quelle, mac, detail, grades, rec):
        tl.append({
            "sortkey": sortkey, "display": display, "quelle": quelle,
            "mac": (mac or "").upper(), "detail": detail, "grades": grades,
            "f_name": rec.get("f_name", ""), "f_phone": rec.get("f_phone", ""),
            "f_ap": rec.get("f_ap", ""), "f_iso": iso,
            "origin": rec["origin"],
        })

    for e in model.events:
        if e["iso"]:
            add(e["iso"], e["iso"], e["iso"].replace("T", " "),
                f'Ereignis · {e["category"]}', e["mac"], e["message"], e["grades"], e)
    for c in model.calls:
        if c["iso"]:
            det = f'{c["typ"]} · {c["rufnummer"]}' + (f' · {c["name"]}' if c["name"] else "")
            add(c["iso"], c["iso"], c["iso"].replace("T", " "),
                "Anruf", "", det, c["grades"], c)
    for w in proofs:
        det = " · ".join(x for x in (w["event_de"], w["band"], (f'AP {w["ap"]}' if w["ap"] else "")) if x)
        add(w["sortkey"], w["iso"], w["display"], "WLAN-Verbindung", w["mac"], det, w["grades"], w)
    for w in model.wifi:
        if w["last_seen_iso"]:
            add(w["last_seen_iso"], w["last_seen_iso"], w["last_seen_iso"].replace("T", " "),
                "Client zuletzt gesehen", w["mac"], w["name"], w["grades"], w)

    tl.sort(key=lambda x: x["sortkey"])
    return tl


# ───────────────────────── Gesamt-Report ─────────────────────────────────────

def _pick_device(mesh_nodes: list, host: str = "") -> dict:
    """Identität der **abgezogenen** Box robust wählen.

    Beste Quelle ist der Mesh-Knoten, dessen Name im `host`-Feld steht (die Box,
    mit der fritzexport tatsächlich sprach). Ist der Host eine IP (kein
    Namenstreffer), wird ein Knoten *mit* Modell bevorzugt — der Master-Knoten
    trägt je nach Firmware kein `device_model`."""
    if host:
        hit = next((n for n in mesh_nodes if n.get("name") and n["name"] in host), None)
        if hit:
            return hit
    for pred in (lambda n: n["role"] == "master" and n.get("model"),
                 lambda n: n["is_ap"] and n.get("model"),
                 lambda n: n.get("model"),
                 lambda n: n["role"] == "master"):
        hit = next((n for n in mesh_nodes if pred(n)), None)
        if hit:
            return hit
    return mesh_nodes[0] if mesh_nodes else {}


def build_html(bundle, model: Model, support: dict, header: dict) -> str:
    m = model
    proofs = support.get("proofs", [])
    up = support.get("uptime", {})

    device = _pick_device(m.mesh_nodes, m.meta.get("host", ""))

    all_iso = [x for x in ([e["f_iso"] for e in m.events] + [c["f_iso"] for c in m.calls]
                           + [p["f_iso"] for p in proofs]) if x]
    zeit_min, zeit_max = (min(all_iso), max(all_iso)) if all_iso else ("", "")
    wlan_iso = [p["iso"] for p in proofs if p["iso"]]
    wlan_min, wlan_max = (min(wlan_iso), max(wlan_iso)) if wlan_iso else ("", "")
    mac_set = ({h["mac"] for h in m.hosts} | {w["mac"] for w in m.wifi}
               | {e["mac"] for e in m.events if e["mac"]}
               | {n["mac"] for n in m.mesh_nodes if n["mac"]}
               | {p["mac"] for p in proofs if p["mac"]})
    active_hosts = sum(1 for h in m.hosts if h["active"])
    raw_report_id = hashlib.sha256(
        (m.meta.get("extracted_at", "") + m.meta.get("host", "")).encode()).hexdigest()

    timeline = build_timeline(m, proofs)

    meta_rows = [
        ("Case-ID", header.get("case_id", "")), ("Asservat / Item-ID", header.get("item_id", "")),
        ("Sachbearbeiter (SB)", header.get("sb", "")), ("Datum", header.get("date", "")),
        ("Gerät", device.get("model", "")), ("Firmware", device.get("firmware", "")),
        ("Geräte-MAC", device.get("mac", "")),
        ("Host-URL", m.meta.get("host", "")),
        ("Extraktionswerkzeug", f'{m.meta.get("tool","?")} {m.meta.get("version","?")}'),
        *_secured_rows(bundle, m),
        ("Report erzeugt am", header.get("generated_at", "")),
        ("Report-Generator", f"fritzreport {__version__}"),
        ("Belegtheits-Schema", f"{GRADE_SCHEMA} ({len(GRADE_LABEL)} Grade)"),
        ("Roh-Report-Hash (SHA256)", raw_report_id),
    ]
    s1 = (
        "<h3>Metadaten des Beweismittels</h3><table class='kv'>"
        # Zeilen sind (Schlüssel, Wert) oder (Schlüssel, Wert, Badge-HTML)
        + "".join(f'<tr><th>{esc(r[0])}</th><td class="mono">{esc(r[1])}'
                  f'{r[2] if len(r) > 2 else ""}</td></tr>' for r in meta_rows)
        + "</table>"
        + f'<h3>Kennzahlen <span class="grade gD3">D3</span></h3><table class="kv">'
        + f'<tr><th>Hosts insgesamt</th><td>{len(m.hosts)}</td></tr>'
        + f'<tr><th>davon aktiv zum Extraktionszeitpunkt</th><td>{active_hosts}</td></tr>'
        + f'<tr><th>Clients (wifi.json)</th><td>{len(m.wifi)}</td></tr>'
        + f'<tr><th>Mesh-Knoten gesamt</th><td>{len(m.mesh_nodes)}</td></tr>'
        + f'<tr><th>davon echte Access Points (is_meshed)</th><td>{len(m.real_aps)} — {esc(", ".join(m.real_aps))}</td></tr>'
        + f'<tr><th>Verbindungsnachweise (Supportdaten)</th><td>{len(proofs)}</td></tr>'
        + f'<tr><th>Ereignisse</th><td>{len(m.events)}</td></tr>'
        + f'<tr><th>Anrufe</th><td>{len(m.calls)}</td></tr>'
        + f'<tr><th>Telefonbuch-Einträge</th><td>{len(m.phonebook)}</td></tr>'
        + f'<tr><th>Einzigartige MAC-Adressen</th><td>{len(mac_set)}</td></tr>'
        + f'<tr><th>Zeitraum zeitgestempelter Datensätze</th><td class="mono">{esc(zeit_min)} — {esc(zeit_max)}</td></tr>'
        + "</table>"
        + f'<h3>Ereignisse nach Kategorie <span class="grade gD3">D3</span></h3>'
        + "<table class='stat'><thead><tr><th>Kategorie</th><th>Anzahl</th></tr></thead><tbody>"
        + "".join(f'<tr><td>{esc(k)}</td><td class="num">{v}</td></tr>'
                  for k, v in sorted(m.cat_counts.items(), key=lambda x: -x[1]))
        + "</tbody></table>"
        + (("<h3>Betriebszeit (aus Supportdaten)</h3><table class='kv'>"
            f"<tr><th>Uptime der Box, roh</th><td class='mono'>{esc(up.get('days',''))}</td></tr>"
            f"<tr><th>hochgefahren am, berechnet {badges(['D3'])}</th>"
            f"<td class='mono'>{esc(up.get('boot_derived',''))}</td></tr>"
            f"<tr><th>WAN-Verbindungsdauer (ip4_uptime), roh</th>"
            f"<td class='mono'>{esc(up.get('wan_s',''))} s ≈ {esc(up.get('wan_h',''))} h</td></tr>"
            f"<tr><th>Fundstelle</th><td class='mono'>{esc(up.get('file',''))}"
            f" — Zeile {up.get('up_line')} (Uptime), Zeile {up.get('wan_line')} (WAN)</td></tr>"
            "</table>") if up.get("days") else "")
    )

    def coc_badge(st):
        if st == "ok":
            return '<span class="ok">✔ verifiziert</span>'
        if st == "mismatch":
            return '<span class="err">✘ MISMATCH</span>'
        return '<span class="unknown">— keine Sidecar</span>'
    mism = sum(1 for e in bundle.coc if e.status == "mismatch")
    s2 = (
        "<p>Rohquellen dieses Reports. Jede Datei ist per SHA256-Sidecar signiert; "
        "fritzreport hat jede Datei gegen ihre Sidecar <strong>verifiziert</strong>.</p>"
        "<table><thead><tr><th>Datei</th><th>SHA256</th><th class='num'>Größe (Byte)</th>"
        "<th>Integrität</th></tr></thead><tbody>"
        + "".join(f'<tr><td class="mono">{esc(c.file)}</td>'
                  f'<td class="mono hash">{esc(c.sha256)}</td>'
                  f'<td class="num mono">{c.size if c.size is not None else ""}</td>'
                  f'<td>{coc_badge(c.status)}</td></tr>' for c in bundle.coc)
        + "</tbody></table>"
    )

    s3 = table("tbl-hosts", ["MAC", "IP", "Hostname", "Interface", "Status", "Gast"],
               render_rows(m.hosts, c_hosts, 8))
    s4 = table("tbl-mesh", ["Name", "Modell", "MAC", "Rolle", "Access Point", "Firmware"],
               render_rows(m.mesh_nodes, c_mesh, 8))
    s5 = table("tbl-wifi", ["MAC", "Name", "IPv4", "Interface", "Access Point", "Status", "Zuletzt gesehen"],
               render_rows(m.wifi, c_wifi, 9))
    s6 = table("tbl-wlan", ["Zeitpunkt", "MAC", "Ereignis", "Band", "Access Point"],
               render_rows(proofs, c_wlan, 7))
    s7 = table("tbl-calls", ["Zeitpunkt", "Typ", "Rufnummer", "Name", "Region", "Nebenstelle", "Eigene Rufnr.", "Dauer"],
               render_rows(m.calls, c_calls, 10))
    s8 = table("tbl-pb", ["Name", "Rufnummern", "Telefonbuch"], render_rows(m.phonebook, c_pb, 5))
    s9 = table("tbl-events", ["Zeitpunkt", "Kategorie", "ID", "MAC", "Meldung"],
               render_rows(m.events, c_events, 7))
    s10 = table("tbl-timeline", ["Zeitpunkt", "Quelle", "MAC", "Beschreibung"],
                render_rows(timeline, c_timeline, 6))

    dhcp_body = '<div class="notice notice-info">Keine DHCP-Konfiguration in diesem Export enthalten.</div>'
    if m.dhcp:
        d = m.dhcp
        dhcp_body = ("<table class='kv'>"
                     f'<tr><th>DHCP-Server aktiv</th><td>{"ja" if d["enable"] else "nein"}</td></tr>'
                     f'<tr><th>Pool von</th><td class="mono">{esc(d["min"])}</td></tr>'
                     f'<tr><th>Pool bis</th><td class="mono">{esc(d["max"])}</td></tr>'
                     f'<tr><th>Subnetzmaske</th><td class="mono">{esc(d["mask"])}</td></tr>'
                     f'<tr><th>Domain</th><td class="mono">{esc(d["domain"])}</td></tr>'
                     f'<tr><th>Router</th><td class="mono">{esc(d["router"])}</td></tr>'
                     f'<tr><th>DNS</th><td class="mono">{esc(d["dns"])}</td></tr>'
                     "</table>")

    legend = (f"<p><strong>Belegtheits-Schema {GRADE_SCHEMA}</strong> "
              f"({len(GRADE_LABEL)} Grade, kombinierbar). Ältere Unterlagen können ein "
              "4-Grade-Schema nennen, in dem <span class='mono'>D3</span> „durch eigene "
              "forensische Versuche belegt&#8220; bedeutete — das entspricht hier "
              "<span class='mono'>D2</span>. Badges dieses Reports sind ausschließlich nach "
              "der folgenden Tabelle zu lesen.</p>"
              "<table class='kv'>"
              + "".join(f'<tr><th>{badges([g])}</th><td>{esc(l)}</td></tr>' for g, l in GRADE_LABEL.items())
              + "</table>"
              "<p>Zeile ohne Badge = reine Rohdaten-Wiedergabe (impliziter Normalfall). "
              "Verbindungsnachweise: methode.md-Parser → <strong>D1+D2</strong>, "
              "802.11-Log-Parser → <strong>D1+D3</strong>. Kombinationen möglich.</p>"
              "<p><strong>Zeitstempel:</strong> Anzeige auf Sekunde gekürzt; Millisekunden der "
              "802.11-Logs bleiben im Original-Auszug der Herkunftszeile und als Sortierschlüssel erhalten.</p>")

    ap_note = (f"Von {len(m.mesh_nodes)} Knoten sind <strong>{len(m.real_aps)} echte Access Points</strong> "
               f"(<span class='mono'>is_meshed = true</span>): {esc(', '.join(m.real_aps))}. "
               f"Nur diese stehen im AP-Filter zur Auswahl.") if m.real_aps else ""
    wlan_note = (f"WLAN-An-/Abmeldungen aus den Supportdaten ({len(proofs)} Nachweise, "
                 f"{len({p['mac'] for p in proofs})} Geräte). Diese Logs stehen "
                 f"<strong>nur in den Supportdaten</strong>. Abgedeckt: "
                 f"<span class='mono'>{esc(wlan_min)}</span> bis <span class='mono'>{esc(wlan_max)}</span>. "
                 f"methode.md-Treffer = D1+D2, 802.11-Log-Treffer = D1+D3.") if proofs else \
                "Keine Verbindungsnachweise aus den Supportdaten extrahierbar."
    tl_note = ("Alle zeitgestempelten Datenpunkte aus <strong>allen</strong> Quellen (Ereignisse, "
               "WLAN-Verbindungsnachweise aus Supportdaten, Anrufe, Client-<span class='mono'>last_seen</span>) "
               "in einer chronologischen Achse. Die ms-genauen An-/Abmeldungen stehen nur in den Supportdaten.")

    sections_html = (
        section("s1", "1", "Übersicht & Metadaten", "meta", None, s1)
        + section("s2", "2", "Chain of Custody", "coc", len(bundle.coc), s2, noun="Dateien",
                  note=(f'<strong class="err">{mism} Datei(en) mit Hash-MISMATCH!</strong>' if mism else ""))
        + section("s3", "3", "Hosts / registrierte Geräte", "hosts", len(m.hosts), s3, noun="Geräte")
        + section("s4", "4", "Mesh-Topologie", "mesh", len(m.mesh_nodes), s4, noun="Knoten", note=ap_note)
        + section("s5", "5", "Clients (wifi.json)", "wifi", len(m.wifi), s5, noun="Clients",
                  note=("" if m.wifi else "Keine WLAN-Clients in <span class='mono'>wifi.json</span> "
                        "dieses Exports — die Box lieferte zum Sammelzeitpunkt keine Client-Liste "
                        "(Verbindungsnachweise stehen in Sektion 6)."))
        + section("s6", "6", "Verbindungsnachweise (WLAN, aus Supportdaten)", "wlan", len(proofs), s6,
                  noun="Nachweise", note=wlan_note)
        + section("s7", "7", "Anrufhistorie", "calls", len(m.calls), s7, noun="Anrufe")
        + section("s8", "8", "Telefonbuch", "pb", len(m.phonebook), s8, noun="Einträge")
        + section("s9", "9", "Ereignisse", "events", len(m.events), s9, noun="Ereignisse")
        + section("s10", "10", "Vollständige Timeline (quellenübergreifend)", "timeline", len(timeline), s10,
                  noun="Datenpunkte", note=tl_note)
        + section("s11", "11", "DHCP-Konfiguration", "dhcp", None, dhcp_body)
        + section("s12", "12", "Belegtheits-Legende", "legend", None, legend)
    )

    toc_items = [
        ("s1", "1", "Übersicht & Metadaten"), ("s2", "2", "Chain of Custody"),
        ("s3", "3", "Hosts / registrierte Geräte"), ("s4", "4", "Mesh-Topologie"),
        ("s5", "5", "Clients (wifi.json)"), ("s6", "6", "Verbindungsnachweise (Supportdaten)"),
        ("s7", "7", "Anrufhistorie"), ("s8", "8", "Telefonbuch"), ("s9", "9", "Ereignisse"),
        ("s10", "10", "Vollständige Timeline"), ("s11", "11", "DHCP-Konfiguration"),
        ("s12", "12", "Belegtheits-Legende"),
    ]
    toc_html = "".join(
        f'<li><a href="#{sid}" data-target="{sid}"><span class="tocnum">{num}</span>{esc(t)}'
        f'<span class="toccount" data-toc="{sid}"></span></a></li>'
        for sid, num, t in toc_items)

    ap_options = "".join(f'<option value="{esc(a)}">{esc(a)}</option>' for a in m.real_aps)
    integrity_banner = (
        f'<div class="banner err"><strong>ACHTUNG:</strong> {mism} Bundle-Datei(en) mit '
        f'SHA256-MISMATCH — Integrität nicht gewährleistet (siehe Chain of Custody).</div>'
        if mism else "")

    return f"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Forensik-Report — {esc(header.get('item_id') or header.get('case_id') or 'FRITZ!Box')}</title>
<style>{CSS}</style>
</head>
<body>

<div id="fbar"><div class="in">
  <div class="row">
    <label>MAC-Adresse<input id="f-mac" type="text" placeholder="z.B. B4:FC" autocomplete="off"></label>
    <label>Gerätename<input id="f-name" type="text" placeholder="z.B. Android" autocomplete="off"></label>
    <label>Telefonnummer<input id="f-phone" type="text" placeholder="z.B. 0048" autocomplete="off"></label>
    <label>Zeitraum ab<input id="f-from" type="datetime-local"></label>
    <label>Zeitraum bis<input id="f-to" type="datetime-local"></label>
    <label>Access Point<select id="f-ap"><option value="">— alle —</option>{ap_options}</select></label>
    <label>Belegtheits-Grad
      <div class="gtogs">
        <span class="gtog on" data-grade="D1" title="Plausibel innerhalb Rohdaten">D1</span>
        <span class="gtog on" data-grade="D2" title="Durch eigene forensische Tests verifiziert">D2</span>
        <span class="gtog on" data-grade="D3" title="Abgeleitet / Interpretation">D3</span>
      </div></label>
    <button class="btn" id="b-reset">Zurücksetzen</button>
    <button class="btn" id="b-expand">Alle aufklappen</button>
    <button class="btn primary" id="b-print">Gefilterte Sicht drucken</button>
  </div>
  <div id="fstate">Keine Filter aktiv — alle Datenpunkte sichtbar.</div>
</div></div>

<main>
<div id="pbanner">
  <strong>GEFILTERTE SICHT — NICHT DER ORIGINAL-REPORT.</strong><br>
  Aktive Filter: <span id="pfilters">—</span><br>
  Roh-Report-Hash (SHA256): <span class="mono">{esc(raw_report_id)}</span><br>
  Case {esc(header.get('case_id',''))} · Item {esc(header.get('item_id',''))} · SB {esc(header.get('sb',''))} · {esc(header.get('generated_at',''))}
</div>

<h1>Forensik-Report — {esc(device.get('model','') or 'FRITZ!Box')}</h1>
<div class="sub">Case {esc(header.get('case_id',''))} · Item {esc(header.get('item_id',''))} · SB {esc(header.get('sb',''))} · erzeugt {esc(header.get('generated_at',''))}</div>

{integrity_banner}
<div class="banner">
  <strong>Interaktive Sicht.</strong> Die Filter oben ändern ausschließlich die Anzeige —
  der Report selbst bleibt unverändert und über seinen SHA256-Hash identifizierbar.
  Ein per Browser erzeugter Ausdruck ist eine <em>gefilterte Sicht</em>, kein Beweismittel-Original.
</div>

<nav id="toc"><ol>{toc_html}</ol></nav>

{sections_html}
</main>

<script>{JS}</script>
</body>
</html>
"""
