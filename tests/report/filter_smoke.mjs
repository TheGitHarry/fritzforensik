// jsdom-Smoke-Test der interaktiven Filter-Logik im generierten Report.
// Aufruf: node filter_smoke.mjs <report.html>
import { JSDOM } from "jsdom";
import { readFileSync } from "fs";

const path = process.argv[2];
if (!path) { console.error("usage: node filter_smoke.mjs <report.html>"); process.exit(2); }

const dom = new JSDOM(readFileSync(path, "utf8"),
  { runScripts: "dangerously", pretendToBeVisual: true });
const { window } = dom;
const doc = window.document;

let failed = 0;
const assert = (cond, msg) => { if (!cond) { console.error("  FAIL:", msg); failed++; }
                                else console.log("  ok:", msg); };
const inputEv = () => new window.Event("input", { bubbles: true });

const rows = [...doc.querySelectorAll("tr.datarow")];
const vis = () => rows.filter(r => !r.classList.contains("hidden"));

assert(rows.length > 0, `datarows vorhanden (${rows.length})`);
assert(vis().length === rows.length, "initial: nichts ausgeblendet");

// --- MAC-Filter
const mac = rows.map(r => r.dataset.mac).find(Boolean);
const fmac = doc.getElementById("f-mac");
fmac.value = mac.slice(0, 8);
fmac.dispatchEvent(inputEv());
assert(vis().length > 0 && vis().length < rows.length, "MAC-Filter blendet aus");
assert(vis().every(r => (r.dataset.mac || "").includes(mac.slice(0, 8))),
  "MAC-Filter: nur passende sichtbar");
// Section-Zähler zeigt gefilterten Stand
const anyFilt = [...doc.querySelectorAll(".seccount")].some(c => /von/.test(c.textContent));
assert(anyFilt, "Sektions-Zähler zeigt 'X von Y'");

// --- Reset
doc.getElementById("b-reset").click();
assert(vis().length === rows.length, "Reset: wieder alle sichtbar");

// --- Grade-Filter: nur D2 aktiv lassen
const togs = [...doc.querySelectorAll(".gtog")];
assert(togs.length === 3, `genau 3 Grade-Umschalter (${togs.length})`);
togs.filter(t => t.dataset.grade !== "D2").forEach(t => t.click());  // D1, D3 aus
const gradedVisible = vis().filter(r => (r.dataset.grades || "").length);
assert(gradedVisible.every(r => r.dataset.grades.split(",").includes("D2")),
  "Grade-Filter 'nur D2': sichtbare graduierte Zeilen tragen D2");
// Zeilen ganz ohne Grade bleiben sichtbar (reine Rohdaten)
const ungraded = rows.filter(r => !(r.dataset.grades || "").length);
assert(ungraded.every(r => !r.classList.contains("hidden")),
  "Zeilen ohne Grade bleiben vom Grade-Filter unberührt");

doc.getElementById("b-reset").click();
assert(vis().length === rows.length, "Reset nach Grade-Filter");

console.log(failed ? `\n${failed} Prüfung(en) fehlgeschlagen` : "\nalle Prüfungen grün");
process.exit(failed ? 1 : 0);
