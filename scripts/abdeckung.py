#!/usr/bin/env python3
"""Erzeugt ABDECKUNG.md aus einem Verzeichnis mit Bundles.

    python3 scripts/abdeckung.py ~/testdata/_work > ABDECKUNG.md

Die Matrix ist zur **Veröffentlichung** bestimmt: Sie zeigt, welche
Modell-/Firmware-Kombinationen schon einmal ausgelesen wurden und welche
Datenarten dabei tatsächlich Datensätze geliefert haben. Daraus kann ein
Außenstehender ablesen, ob ein Abzug seiner Box dem Projekt weiterhilft.

Bewusst NICHT ausgegeben werden Seriennummern, Aktenzeichen, Hostnamen, IPs
und absolute Datensatzzahlen — letztere lassen Rückschlüsse auf den
Haushalt zu (Zahl der Geräte, Anrufe). Es steht nur da, *ob* eine Datenart
Daten lieferte, nie wie viele. Eine Gegenprobe darauf steht in
tests/format/test_abdeckung.py.
"""
from __future__ import annotations

import hashlib
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from fritzformat.names import JSON_TYPES, SUPPORT_VARIANTS  # noqa: E402

#: HWRevision → Handelsname. Aus den Supportdaten ist nur die Revision
#: sicher ablesbar; das Modell steht dort nicht durchgängig als Klartext.
HWREV_MODELL = {
    "185": "FRITZ!Box 7490",
    "226": "FRITZ!Box 7590",
    "256": "FRITZ!Box 7530 AX",
    "285": "FRITZ!Box 7690",
}


def _erste_zeilen(pfad: Path, anzahl: int = 400) -> list[str]:
    with pfad.open(encoding="utf-8", errors="replace") as f:
        return [zeile for _, zeile in zip(range(anzahl), f)]


def firmware_kurz(roh: str) -> str:
    """``285.08.25,slot0=…,slot1=…`` → ``08.25``.

    ``firmware_info`` führt hinter einem Komma die Inhalte beider Flash-Slots
    des Dual-Boot-Systems auf. Die sind hier nicht nur überflüssig breit,
    sondern schädlich: Zwei Boxen mit demselben FRITZ!OS-Stand hätten je nach
    Slot-Belegung verschiedene Werte und würden in der Matrix als
    unterschiedliche Zeilen erscheinen. Vor dem Komma steht
    ``<HWRevision>.<FRITZ!OS>``; die Revision hat eine eigene Spalte.
    """
    kern = roh.split(",", 1)[0].strip()
    teile = kern.split(".")
    return ".".join(teile[1:]) if len(teile) >= 3 else kern


def _brauchbar(wert: str) -> bool:
    """Taugt der Wert zum Unterscheiden von Geräten?

    Leer oder durchgängig genullt heißt: das Feld wurde mit einem Vorgabewert
    beschrieben, nicht mit einer Gerätekennung. Im Korpus trifft das auf die
    ``SerialNumber`` eines 7490 zu.
    """
    wert = wert.strip()
    return bool(wert) and set(wert) > {"0"}


def _geraetekennung(zeilen: list[str]) -> str:
    """Stabile, nicht rückrechenbare Kennung eines Geräts.

    Dient allein dazu, mehrere Abzüge **derselben** Box als ein Gerät zu zählen.
    Ohne das läse sich „3 Abzüge" wie „3 Geräte", und die Hardware-Abdeckung
    erschiene besser als sie ist.

    Herangezogen werden zwei Felder in fester **Rangfolge**, nicht in
    Kombination: zuerst ``tr069_serial``, ersatzweise ``SerialNumber``.

    Die Rangfolge ist wesentlich. Beide Felder zusammen zu hashen wäre falsch —
    dann gälten zwei Abzüge derselben Box als verschiedene Geräte, sobald eines
    der Felder in einem Abzug fehlt. Und ``tr069_serial`` steht zuerst, weil es
    sich im Korpus als das robustere erwiesen hat: Es wird aus der MAC gebildet
    (``00040E-<maca ohne Doppelpunkte>``) und überlebt damit ein Zurücksetzen,
    bei dem ``SerialNumber`` auf Nullen fällt.

    Ausgegeben wird nur ein gekürzter SHA256; weder er noch die Rohwerte
    erscheinen in der Matrix. Der Wert verlässt diese Funktion als reines
    Zählmerkmal.
    """
    for feld in ("tr069_serial", "SerialNumber"):
        wert = _feld(zeilen, feld)
        if _brauchbar(wert):
            roh = f"{feld}={wert.strip()}|{_feld(zeilen, 'HWRevision')}"
            return hashlib.sha256(roh.encode("utf-8")).hexdigest()[:16]
    # Kein brauchbares Feld — der Aufrufer zählt solche Abzüge einzeln,
    # statt sie fälschlich zu verschmelzen.
    return ""


def _feld(zeilen: list[str], name: str) -> str:
    """Tab-getrenntes Feld aus dem Kopf der Supportdaten ziehen."""
    muster = re.compile(rf"^{re.escape(name)}\t(.+)$")
    for zeile in zeilen:
        treffer = muster.match(zeile.rstrip("\n"))
        if treffer:
            return treffer.group(1).strip()
    return ""


def lies_bundle(verzeichnis: Path) -> dict | None:
    """Liest die veröffentlichbaren Merkmale eines Bundles."""
    standard = sorted(verzeichnis.glob("supportdata_standard_*.txt"))
    if not standard:
        return None
    kopf = _erste_zeilen(standard[0])

    hwrev = _feld(kopf, "HWRevision")
    befund = {
        "hwrev": hwrev,
        # Nur zum Unterscheiden von Geräten — der Hash selbst wird nie
        # ausgegeben, die Klartext-Serial erst recht nicht. Ohne diese
        # Unterscheidung läse sich "3 Abzüge" wie "3 Geräte", obwohl es
        # dieselbe Box sein kann.
        "geraet": _geraetekennung(kopf),
        # Für den Hinweis in der Ausgabe — die Serial selbst wird nie
        # ausgegeben, nur die Tatsache, dass sie genullt ist.
        "serial_genullt": not _brauchbar(_feld(kopf, "SerialNumber")),
        "modell": HWREV_MODELL.get(hwrev, f"unbekannt (HWRevision {hwrev})"),
        "firmware": firmware_kurz(_feld(kopf, "firmware_info")),
        "datenarten": {},
        "support": sorted(
            v for v in SUPPORT_VARIANTS if list(verzeichnis.glob(f"supportdata_{v}_*.txt"))
        ),
    }

    for art in JSON_TYPES:
        treffer = sorted(verzeichnis.glob(f"*_{art}.json"))
        if not treffer:
            befund["datenarten"][art] = "fehlt"
            continue
        try:
            daten = json.loads(treffer[0].read_text(encoding="utf-8", errors="replace"))
        except (json.JSONDecodeError, OSError):
            befund["datenarten"][art] = "fehlt"
            continue
        satz = daten.get("records")
        # Nur ob, nicht wie viele — die Zahl bliebe sonst ein Rückschluss
        # auf den Haushalt.
        befund["datenarten"][art] = "ja" if isinstance(satz, list) and satz else "leer"
    return befund


def gruppiere(befunde: list[dict]) -> dict[tuple[str, str], list[dict]]:
    """Nach Modell+Firmware bündeln — mehrere Abzüge derselben Box sind eine Zeile."""
    gruppen: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for b in befunde:
        gruppen[(b["modell"], b["firmware"])].append(b)
    return gruppen


def geraetezahl(eintraege: list[dict]) -> int:
    """Wie viele **verschiedene** Geräte hinter diesen Abzügen stecken.

    Abzüge ohne brauchbare Seriennummer (Kennung ``""``) zählen einzeln — sie
    lassen sich nicht zusammenführen, und lieber ein Gerät zu viel ausweisen
    als zwei fälschlich verschmelzen.
    """
    bekannt = {e["geraet"] for e in eintraege if e["geraet"]}
    unbekannt = sum(1 for e in eintraege if not e["geraet"])
    return len(bekannt) + unbekannt


SYMBOL = {"ja": "✓", "leer": "○", "fehlt": "—"}


def zusammenfassen(eintraege: list[dict], art: str) -> str:
    """Bestes Ergebnis über alle Abzüge einer Modell-/Firmware-Kombination."""
    werte = {e["datenarten"].get(art, "fehlt") for e in eintraege}
    for rang in ("ja", "leer", "fehlt"):
        if rang in werte:
            return SYMBOL[rang]
    return SYMBOL["fehlt"]


def erzeuge(befunde: list[dict]) -> str:
    gruppen = gruppiere(befunde)
    zeilen: list[str] = []
    a = zeilen.append

    a("# Abdeckung: getestete Boxen und Datenarten")
    a("")
    a("Welche FRITZ!Box-Modelle mit welchem FRITZ!OS-Stand bereits ausgelesen wurden —")
    a("und welche Datenarten dabei tatsächlich Daten geliefert haben.")
    a("")
    a("**Diese Datei wird erzeugt, nicht von Hand gepflegt:**")
    a("")
    a("```bash")
    a("python3 scripts/abdeckung.py <verzeichnis-mit-bundles> > ABDECKUNG.md")
    a("```")
    a("")
    a("| Zeichen | Bedeutung |")
    a("|---|---|")
    a("| ✓ | Datenart lieferte Datensätze |")
    a("| ○ | abgefragt, kam aber leer zurück |")
    a("| — | in diesem Abzug nicht enthalten |")
    a("")
    a("Ein ○ ist nicht zwingend ein Fehler — eine Box ohne Anrufbeantworter liefert bei")
    a("`tam` zu Recht nichts. Es heißt nur: an dieser Kombination ist der Codepfad noch")
    a("nie mit echten Daten gelaufen.")
    a("")

    kopf = ("| Modell | HWRev | FRITZ!OS | Geräte | Abzüge | "
            + " | ".join(JSON_TYPES) + " |")
    a(kopf)
    a("|---" * (5 + len(JSON_TYPES)) + "|")
    for (modell, firmware), eintraege in sorted(gruppen.items()):
        felder = [zusammenfassen(eintraege, art) for art in JSON_TYPES]
        a(f"| {modell} | {eintraege[0]['hwrev']} | {firmware} | "
          f"{geraetezahl(eintraege)} | {len(eintraege)} | "
          + " | ".join(felder) + " |")
    a("")

    # Je Modell über alle Firmware-Zeilen hinweg zählen. Ohne das bliebe
    # unsichtbar, dass dieselbe Box vor und nach einem Firmware-Update in zwei
    # Zeilen steht — der Leser zählte Zeilen und käme auf zu viele Geräte.
    je_modell: dict[str, list[dict]] = defaultdict(list)
    for b in befunde:
        je_modell[b["modell"]].append(b)

    mehrfach = [
        (modell, geraetezahl(eintraege), len(eintraege))
        for modell, eintraege in sorted(je_modell.items())
        if len(eintraege) > geraetezahl(eintraege)
    ]
    if mehrfach:
        a("**Mehrere Abzüge derselben Box.** Die Spalte „Geräte\" zählt verschiedene")
        a("Exemplare, „Abzüge\" die Sicherungen davon. Wo beide auseinandergehen,")
        a("stammen mehrere Abzüge vom selben Gerät (erkannt an der Seriennummer, die")
        a("hier bewusst nicht steht) — etwa dieselbe Box vor und nach einem")
        a("Firmware-Update. Solche Abzüge erweitern die **Hardware**-Abdeckung nicht:")
        a("")
        for modell, geraete, abzuege in mehrfach:
            a(f"- {modell}: {abzuege} Abzüge, aber nur {geraete} Gerät"
              + ("e" if geraete != 1 else ""))
        a("")
        a("Ein Abzug eines **zweiten Exemplars** dieser Modelle ist deshalb weiterhin")
        a("wertvoll — auch wenn Modell und FRITZ!OS-Stand schon in der Tabelle stehen.")
        a("")

    genullt = sorted({b["modell"] for b in befunde if b.get("serial_genullt")})
    if genullt:
        a("### Genullte Seriennummer")
        a("")
        a("Bei " + ", ".join(genullt) + " im Korpus steht in `SerialNumber` eine Folge")
        a("aus lauter Nullen. Das ist **kein Auslesefehler**: Das Feld ist beschrieben,")
        a("nur eben mit einem Vorgabewert statt einer Gerätekennung.")
        a("")
        a("Das übrige Urlader-Environment ist dabei unversehrt — MAC-Adressen,")
        a("Hardware-Revision und Bootloader-Version stehen normal darin. Das Muster")
        a("passt zu einer **Wiederherstellung aus einem generischen AVM-Image**: Ein")
        a("solches Image bringt die gerätespezifische Seriennummer nicht mit (sie steht")
        a("auf dem Gehäuseaufkleber), und das Feld wird beim Neuaufbau des Environments")
        a("mit Nullen belegt. Andere Ursachen sind nicht auszuschließen — ein Nachweis")
        a("des Vorgangs selbst steckt nicht in den Daten.")
        a("")
        a("Praktische Folge: Bei einer solchen Box taugt `SerialNumber` **nicht** zur")
        a("Identifikation. Diese Matrix unterscheidet Geräte deshalb vorrangig über")
        a("`tr069_serial`, das aus der MAC-Adresse gebildet wird und den Vorgang")
        a("übersteht. Wer Abzüge forensisch zuordnet, sollte sich aus demselben Grund")
        a("nicht allein auf `SerialNumber` verlassen.")
        a("")

    a("## Supportdaten-Varianten")
    a("")
    a("| Modell | FRITZ!OS | " + " | ".join(SUPPORT_VARIANTS) + " |")
    a("|---" * (2 + len(SUPPORT_VARIANTS)) + "|")
    for (modell, firmware), eintraege in sorted(gruppen.items()):
        vorhanden = {v for e in eintraege for v in e["support"]}
        felder = ["✓" if v in vorhanden else "—" for v in SUPPORT_VARIANTS]
        a(f"| {modell} | {firmware} | " + " | ".join(felder) + " |")
    a("")

    # Lücken: Datenarten, die NIRGENDS Daten lieferten, sind die wertvollsten
    # Hinweise für Beitragende — dort ist der Codepfad faktisch ungetestet.
    nie = [art for art in JSON_TYPES
           if all(e["datenarten"].get(art) != "ja" for e in befunde)]
    teils = [art for art in JSON_TYPES
             if art not in nie and any(e["datenarten"].get(art) != "ja" for e in befunde)]

    a("## Wo Abzüge dem Projekt am meisten helfen")
    a("")
    if nie:
        a("**Bisher in keinem einzigen Abzug mit Daten gesehen** — hier ist der Codepfad")
        a("faktisch ungetestet:")
        a("")
        for art in nie:
            a(f"- `{art}`")
        a("")
    if teils:
        a("**Nur auf einem Teil der Modelle mit Daten gesehen** — Abzüge der übrigen")
        a("Modelle schließen die Lücke:")
        a("")
        for art in teils:
            mit = sorted({e["modell"] for e in befunde if e["datenarten"].get(art) == "ja"})
            a(f"- `{art}` — bisher nur: {', '.join(mit)}")
        a("")

    fehlende = sorted(set(HWREV_MODELL.values()) - {b["modell"] for b in befunde})
    a("Ebenso wertvoll: **jedes Modell, das oben noch gar nicht steht**, und jeder")
    a("deutlich abweichende FRITZ!OS-Stand eines schon gelisteten Modells.")
    if fehlende:
        a("")
        a("Bekannt, aber noch nicht abgedeckt: " + ", ".join(fehlende) + ".")
    a("")
    a("")
    a("## Bevor Sie einen Abzug bereitstellen")
    a("")
    a("Ein Abzug enthält **personenbezogene Daten** — Anrufe, Telefonbuch, Gerätenamen,")
    a("MAC-Adressen. Nicht nur Ihre eigenen: auch die aller Personen, die mit dieser Box")
    a("telefoniert haben oder in ihrem WLAN waren. Diese Menschen können nicht selbst")
    a("einwilligen. Bitte prüfen Sie vor dem Bereitstellen, wessen Daten Sie weitergeben.")
    a("")
    a("### Auswertung erfolgt KI-gestützt")
    a("")
    a("Zwei Dinge, die auseinanderzuhalten sind:")
    a("")
    a("- **Die Werkzeuge selbst enthalten keine KI.** `fritzexport` und `fritzreport`")
    a("  sind gewöhnliche Programme ohne Modell, ohne Dienstaufruf. `fritzexport`")
    a("  spricht ausschließlich mit der Box im eigenen Netz, `fritzreport` liest nur")
    a("  das Bündel auf der Platte. Wer sie herunterlädt und auf eigenen Geräten")
    a("  einsetzt, gibt keine Daten heraus.")
    a("- **Die Weiterentwicklung dieses Projekts läuft KI-gestützt.** Wird ein Abzug")
    a("  bereitgestellt, um eine Lücke zu schließen, werden seine Inhalte dabei von")
    a("  einem KI-Assistenten verarbeitet — und damit an dessen Anbieter übermittelt.")
    a("")
    a("**Wer einen Abzug bereitstellt, muss damit einverstanden sein.** Sind Sie es")
    a("nicht, stellen Sie bitte keinen bereit — es gibt einen Weg ohne Daten, siehe")
    a("unten.")
    a("")
    a("### Der einfachere Weg: nur die Abdeckungsinformation")
    a("")
    a("Für diese Matrix genügt in aller Regel schon, **was ohne personenbezogene Daten**")
    a("auskommt:")
    a("")
    a("- Modell, HWRevision und FRITZ!OS-Stand (aus der Box-Oberfläche ablesbar)")
    a("- welche Datenarten Daten enthielten — also die Zeile, die in dieser Tabelle")
    a("  entstünde")
    a("")
    a("Damit lässt sich eine Lücke oft schon schließen, ohne dass ein einziger Datensatz")
    a("das Haus verlässt. Ein vollständiger Abzug ist nur nötig, wenn ein Fehler")
    a("nachvollzogen werden muss.")
    a("")
    a("Ein Abzug gehört in **keinem** Fall in ein öffentliches Issue. Der Weg für eine")
    a("Kontaktaufnahme steht in [SECURITY.md](SECURITY.md).")
    return "\n".join(zeilen) + "\n"


def main(argv: list[str]) -> int:
    if len(argv) != 2:
        print(__doc__.strip().splitlines()[2].strip(), file=sys.stderr)
        return 2
    wurzel = Path(argv[1]).expanduser()
    if not wurzel.is_dir():
        print(f"Kein Verzeichnis: {wurzel}", file=sys.stderr)
        return 2

    befunde = [b for b in (lies_bundle(p) for p in sorted(wurzel.iterdir()) if p.is_dir()) if b]
    if not befunde:
        print(f"Keine auswertbaren Bundles in {wurzel}", file=sys.stderr)
        return 1
    print(erzeuge(befunde), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
