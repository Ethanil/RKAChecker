"""
Regelbasierte Validierung für den RKA (Reisekostenabrechnung).

Datenmodell (wie der Extraktionscode liefert):
    - Checkbox-Felder (is_checkbox)  -> bool
    - Text/Choice/Radio              -> str | None  (freier Text, auch "")

Jede Regel ist eine Funktion  check_*(ctx) -> list[Issue].
Neue Regeln einfach als Funktion schreiben und in RULES eintragen.
"""

from __future__ import annotations

import os
import re
import sys
from dataclasses import dataclass, field as dc_field
from datetime import datetime, date, time
from enum import Enum
from typing import Callable, Optional

# --------------------------------------------------------------------------- #
# Selbst-Bootstrap der Abhängigkeiten
# --------------------------------------------------------------------------- #
# Ziel: "runterladen und `py main.py PDF.pdf` laufen lassen" - ohne dass der
# Nutzer vorher von Hand `pip install` ausführt. Beim ersten Start wird eine
# fehlende Abhängigkeit (pikepdf) automatisch in die AKTUELLE Python-Umgebung
# installiert und der Prozess einmal neu gestartet. Danach kostet dieser Block
# nichts mehr (Import klappt sofort). Nutzt nur die Standardbibliothek, damit
# der Import dieser Datei selbst nie an fehlenden Paketen scheitert.

_REQUIREMENTS = ["pikepdf>=9,<11"]       # Laufzeit-Abhängigkeiten
_BOOTSTRAP_FLAG = "RKA_BOOTSTRAPPED"      # verhindert Endlos-Neustart

def _ensure_dependencies() -> None:
    try:
        import pikepdf  # noqa: F401  - nur Verfügbarkeit prüfen
        return
    except ImportError:
        pass

    # Schon einmal versucht? Dann nicht erneut, sonst Endlosschleife.
    if os.environ.get(_BOOTSTRAP_FLAG):
        sys.stderr.write(
            "FEHLER: 'pikepdf' ist nicht installiert und die automatische\n"
            "Installation ist fehlgeschlagen. Bitte manuell nachinstallieren:\n"
            f"    {sys.executable} -m pip install " + " ".join(_REQUIREMENTS) + "\n")
        sys.exit(3)

    import subprocess
    sys.stderr.write(
        "Erststart: installiere benötigte Abhängigkeiten "
        f"({', '.join(_REQUIREMENTS)}) ...\n")
    try:
        subprocess.check_call(
            [sys.executable, "-m", "pip", "install", *_REQUIREMENTS])
    except Exception as exc:  # pip fehlt / offline / keine Rechte
        sys.stderr.write(
            f"FEHLER: automatische Installation fehlgeschlagen ({exc!r}).\n"
            "Bitte manuell:\n"
            f"    {sys.executable} -m pip install " + " ".join(_REQUIREMENTS) + "\n")
        sys.exit(3)

    # Prozess mit demselben Interpreter + denselben Argumenten neu starten,
    # damit das frisch installierte Paket importierbar ist.
    os.environ[_BOOTSTRAP_FLAG] = "1"
    sys.stderr.write("Abhängigkeiten installiert - starte neu ...\n\n")
    os.execv(sys.executable, [sys.executable, *sys.argv])

# Nur beim direkten Aufruf (`py main.py ...`) bootstrappen, nicht beim Import
# als Modul (z. B. durch Tests), damit Importe dort kontrolliert bleiben.
if __name__ == "__main__":
    _ensure_dependencies()

# --------------------------------------------------------------------------- #
# Mapping: Feld-ID -> menschenlesbares Label
# --------------------------------------------------------------------------- #

mapping = {
    "Textfeld0": "Stempel oder Bezeichnung der Organisationseinheit",
    "Textfeld1": "Tel.Nr.",
    "Textfeld2": "E-mail Kostenstellenverantwortlicher",
    "Textfeld3": "Name, Vorname",
    "Textfeld4": "Pers. Nr. SAP:",
    "Textfeld6": "Privatanschrift:",
    "Textfeld8": "Dienstort",
    "Kontrollkästchen0": "Dienstreise angeordnet?",
    "Kontrollkästchen1": "Dienstreise genehmigt?",
    "Textfeld9": "angeordnet/genehmigt durch:",
    "Kontrollkästchen2": "Bankverbindung hat sich nicht geändert?",
    "Kontrollkästchen3": "Bankverbindung hat sich geändert?",
    "Textfeld10": "Kreditinstitut mit Ortsangabe",
    "Textfeld11": "BIC",
    "Textfeld12": "IBAN",
    "Textfeld13": "Ich habe einen Abschlag in Höhe von erhalten.",
    "Textfeld14": "Antragsdatum:",
    "Textfeld15": "Kostenstelle:",
    "Textfeld16": "Projekt:",
    "Textfeld17": "Verbuchtungsdatum:",
    "Textfeld18": "Beginn: Von (Orts- u. Landesangabe)",
    "Textfeld19": "Beginn: Nach (Orts- u. Landesangabe)",
    "Kontrollkästchen4": "Beginn: Abreise von Wohnung?",
    "Kontrollkästchen5": "Beginn: Abreise von Dienststelle?",
    "Kontrollkästchen6": "Beginn: Abreise von Sonstiges?",
    "Textfeld26": "Beförderungsmittel",
    "Textfeld27": "Beginn: Abflug- und Ankunftsdaten des Fluges",
    "Textfeld28": "Zweck der Reise",
    "Textfeld20": "Beginn: Abfahrtsdatum",
    "Textfeld21": "Beginn: Abfahrtszeit",
    "Textfeld22": "Beginn des ersten Dienstgeschäfts Datum",
    "Textfeld23": "Beginn des ersten Dienstgeschäfts Uhrzeit",
    "Textfeld24": "Ende des letzten Dienstgeschäfts Datum",
    "Textfeld25": "Ende des letzten Dienstgeschäfts Uhrzeit",
    "Textfeld29": "Ende: Von",
    "Textfeld30": "Ende: Nach",
    "Textfeld35": "Ende: Beförderungsmittel",
    "Textfeld36": "Ende: Abflug- und Ankunftsdaten des Fluges",
    "Textfeld37": "Begründung, wenn Rückreisetag abweichend von Tag des letzten Dienstgeschäfts",
    "Textfeld31": "Ende: Abfahrtsdatum",
    "Textfeld32": "Ende: Abfahrtszeit",
    "Textfeld33": "Ende: Ankunftsdatum",
    "Textfeld34": "Ende: Ankunftszeit",
    "Kontrollkästchen7": "Tagegeld beantragt?",
    "Kontrollkästchen8": "Verpflegung gestellt nein?",
    "Kontrollkästchen9": "Verpflegung gestellt ja?",
    "Textfeld38": "Verpflegung Frühstück am",
    "Textfeld39": "Verpflegung Mittagessen  am",
    "Textfeld40": "Verpflegung Abendessen am",
    "Textfeld41": "Kein Tagegeld an diesen Tagen",
    "Kontrollkästchen10": "Übernachtungsgeld?",
    "Kontrollkästchen11": "Es sind dienstlich Übernachtungskosten enstanden?",
    "Textfeld42": "Übernachtungskosten in Euro",
    "Kontrollkästchen14": "Dienstlich gemeinsam genutzt?",
    "Kontrollkästchen12": "alleinige Nutzung des Zimmers ja?",
    "Kontrollkästchen13": "alleinige Nutzung des Zimmers nein?",
    "Textfeld43": "Dienstlich gemeinsam genutzt mit",
    "Textfeld44": "Begründung warum mehr als 80€/Nacht",
    "Kontrollkästchen15": "Es wurden Nächte privat übernommen",
    "Textfeld45": "Folgende Nächte werden privat übernommen (Urlaub....)",
    "Kontrollkästchen16": "Übernachtungspauschale?",
    "Textfeld46": "Übernachtungspauschalbetrag",
    "Kontrollkästchen17": "Ich beantrage Fahrtkosten",
    "Kontrollkästchen18": "Fahrt mit privatem Kraftfahrzeug?",
    "Kontrollkästchen19": "Fahrt angeordnet?",
    "Kontrollkästchen20": "PKW nicht triftiger Grund?",
    "Kontrollkästchen21": "PKW triftiger Grund?",
    "Textfeld47": "angeordnet  durch",
    "Textfeld48": "Begründung PKW nutzung",
    "Textfeld49": "Folgende Strecken wurden mit privatem Kraftfahrzeug zurückgelegt (Orte):",
    "Textfeld50": "Insgesamt gefahrene Kilometer mit privatem Kraftfahrzeug",
    "Textfeld51": "Anzahl aus dienstlichen Gründen mitgenommenen Personen",
    "Textfeld52": "Personen mitgenommen bei km",
    "Textfeld53": "Name des/der Mitfahrer",
    "Kontrollkästchen22": "Bahncard 25?",
    "Kontrollkästchen23": "Bahncard 50?",
    "Kontrollkästchen24": "Bahncard 100?",
    "Kontrollkästchen25": "Öffentliche Verkehrsmittel wurden von mir gezahlt?",
    "Kontrollkästchen26": "Öffentliche Verkehrsmittel wurden bereits von TUD gezahlt?",
    "Kontrollkästchen27": "Öffentliche Verkehrsmittel wurden von anderer Seite gezahlt?",
    "Textfeld54": "Enstandene kosten durch öffentliche Verkehrsmittel",
    "Kontrollkästchen28": "Flug wurde von mir gezahlt?",
    "Kontrollkästchen29": "Flug wurde bereits von TUD gezahlt?",
    "Kontrollkästchen30": "Flug wurde von anderer Seite gezahlt",
    "Textfeld55": "Enstandene kosten durch Flug",
    "Kontrollkästchen31": "Ich beantrage die Erstattung sonstiger Auslagen",
    "Textfeld56": "Art der Nebenkosten1",
    "Textfeld57": "Betrag der mit entstandenen Kosten1",
    "Textfeld58": "Begründung1",
    "Textfeld59": "Art der Nebenkosten2",
    "Textfeld61": "Betrag der mit entstandenen Kosten2",
    "Textfeld60": "Begründung2",
    "Textfeld62": "Art der Nebenkosten3",
    "Textfeld64": "Betrag der mit entstandenen Kosten3",
    "Textfeld63": "Begründung3",
    "Textfeld65": "Art der Nebenkosten4",
    "Textfeld67": "Betrag der mit entstandenen Kosten4",
    "Textfeld66": "Begründung4",
    "Textfeld68": "Art der Nebenkosten5",
    "Textfeld70": "Betrag der mit entstandenen Kosten5",
    "Textfeld69": "Begründung5",
    "Textfeld73": "Art der Nebenkosten6",
    "Textfeld71": "Betrag der mit entstandenen Kosten6",
    "Textfeld72": "Begründung6",
}

# --------------------------------------------------------------------------- #
# Ergebnis-Typen
# --------------------------------------------------------------------------- #

class Severity(str, Enum):
    ERROR = "ERROR"      # muss korrigiert werden
    WARNING = "WARNING"  # sollte geprüft werden
    INFO = "INFO"        # Hinweis

@dataclass
class Issue:
    severity: Severity
    rule: str            # Name der Regel, z. B. "reisedatum"
    message: str         # menschenlesbar
    fields: list[str] = dc_field(default_factory=list)  # betroffene Feld-IDs

    def __str__(self) -> str:
        f = f" [{', '.join(self.fields)}]" if self.fields else ""
        return f"{self.severity.value:7} {self.rule}: {self.message}{f}"

@dataclass
class Context:
    """Alles, was die Regeln brauchen, an einem Ort."""
    data: dict           # field_id -> value (bool|str|None)
    mapping: dict        # field_id -> menschenlesbares Label
    env: dict            # erwartete Sollwerte aus .env

# --------------------------------------------------------------------------- #
# Hilfsfunktionen (Zugriff + Parsing)
# --------------------------------------------------------------------------- #

def _label(ctx: Context, field_id: str) -> str:
    return ctx.mapping.get(field_id, field_id)

def get_text(ctx: Context, field_id: str) -> str:
    """Text-Feld als gestrippter String ('' wenn leer/None/nicht vorhanden).

    Behält interne Zeilenumbrüche (\\r, \\n) bewusst bei - die Vergleichs-
    Normalisierung passiert erst in der jeweiligen Regel.
    """
    v = ctx.data.get(field_id)
    if v is None:
        return ""
    return str(v).strip()

def get_bool(ctx: Context, field_id: str) -> bool:
    """Checkbox-Feld als bool (False wenn nicht vorhanden)."""
    return bool(ctx.data.get(field_id, False))

def normalize_ws(s: str) -> str:
    """Alle Whitespace-Folgen (inkl. \\r, \\n, Tabs) zu einem Leerzeichen; getrimmt.

    So matcht ein mehrzeiliger PDF-Feldwert gegen einen einzeilig in der .env
    hinterlegten Sollwert, Zeichen für Zeichen identisch bis auf den Umbruch.
    """
    return re.sub(r"\s+", " ", (s or "")).strip()

def is_multiline(s: str) -> bool:
    """True, wenn der Rohwert einen Zeilenumbruch enthält (\\r oder \\n)."""
    return bool(s) and ("\r" in s or "\n" in s)

def show_ws(s: str) -> str:
    """Macht \\r / \\n in Fehlermeldungen sichtbar statt sie roh auszugeben."""
    return s.replace("\r\n", "\\n").replace("\r", "\\r").replace("\n", "\\n")

_DATE_FORMATS = ("%d.%m.%Y", "%d.%m.%y", "%Y-%m-%d", "%d/%m/%Y", "%d.%m.")
_TIME_FORMATS = ("%H:%M", "%H.%M", "%H:%M:%S")

def parse_date(s: str) -> Optional[date]:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in _DATE_FORMATS:
        try:
            d = datetime.strptime(s, fmt).date()
            if fmt == "%d.%m.":           # ohne Jahr -> aktuelles Jahr
                d = d.replace(year=date.today().year)
            return d
        except ValueError:
            continue
    return None

def parse_time(s: str) -> Optional[time]:
    s = (s or "").strip()
    if not s:
        return None
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None

def parse_amount(s: str) -> Optional[float]:
    """'1.234,56 €' / '1234.56' / '1.234' / '80,-' -> float. None wenn leer/unparsbar.

    Deutsche Schreibweise ist die Regel auf dem Formular:
      - Komma  = Dezimaltrenner
      - Punkt  = Tausendertrenner
    Ein einzelner Punkt ist deshalb mehrdeutig:
      '1.234'  bedeutet in DE 1234 (Tausender), nicht 1.234.
    Heuristik:
      * Komma UND Punkt vorhanden  -> Punkt = Tausender, Komma = Dezimal.
      * nur Komma                  -> Komma = Dezimal.
      * nur Punkt(e):
          - als reiner Tausendertrenner formatiert (jede Gruppe nach dem
            ersten Punkt genau 3 Ziffern, z. B. '1.234', '1.234.567')
            -> Punkte entfernen (Tausender).
          - sonst (z. B. '1234.56', '0.5') -> Punkt bleibt Dezimaltrenner.
    """
    s = (s or "").strip()
    if not s:
        return None
    s = s.replace("€", "").replace("EUR", "").replace(" ", "").strip()
    neg = s.startswith("-")               # Vorzeichen vor dem Trimmen sichern
    if "," in s and "." in s:             # 1.234,56 -> 1234.56
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:                        # 1234,56 -> 1234.56
        s = s.replace(",", ".")
    elif "." in s:                        # nur Punkt(e): mehrdeutig
        # Tausender-Muster: Ziffern, dann 1+ Gruppen aus '.' + genau 3 Ziffern.
        if re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
            s = s.replace(".", "")        # 1.234(.567) -> 1234(567)
        # andernfalls Punkt als Dezimaltrenner belassen (1234.56, 0.5)
    s = s.rstrip("-.")                    # "80,-" -> "80"
    if not s or s == "-":
        return None
    try:
        val = float(s)
    except ValueError:
        return None
    return -val if neg and val > 0 else val

def exactly_one(ctx: Context, *field_ids: str) -> int:
    """Zählt, wie viele der genannten Checkboxen gesetzt sind."""
    return sum(1 for f in field_ids if get_bool(ctx, f))

# --------------------------------------------------------------------------- #
# .env laden
# --------------------------------------------------------------------------- #

def load_env(path: str = ".env") -> dict:
    """
    Minimaler .env-Parser (kein python-dotenv nötig).
    Erwartete Keys:
        RKA_STEMPEL, RKA_TEL, RKA_EMAIL, RKA_KOSTENSTELLE
        RKA_PROJEKTNUMMERN   (kommasepariert, z. B. "P1234,P5678")

    Mehrzeilige Sollwerte: schreib '\\n' literal in die .env, z. B.
        RKA_STEMPEL=Technische Universität Darmstadt\\nFB18 etit, AG Serious Games
    Das '\\n' wird hier zu einem echten Zeilenumbruch dekodiert.
    """
    env: dict = {}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                key, _, val = line.partition("=")
                val = val.strip().strip('"').strip("'")
                val = val.replace("\\n", "\n").replace("\\r", "\r")  # literale Umbrüche
                env[key.strip()] = val
    for k in ("RKA_STEMPEL", "RKA_TEL", "RKA_EMAIL",
              "RKA_KOSTENSTELLE", "RKA_PROJEKTNUMMERN"):
        if k in os.environ:               # Prozess-Environment hat Vorrang
            env[k] = os.environ[k]
    return env

def allowed_projects(env: dict) -> set[str]:
    raw = env.get("RKA_PROJEKTNUMMERN", "")
    return {p.strip() for p in raw.split(",") if p.strip()}

# =========================================================================== #
# REGELN
# =========================================================================== #

# --- Reisedaten / Zeitlogik ------------------------------------------------ #

def check_reisedatum(ctx: Context) -> list[Issue]:
    """
    Hinreise <= erstes Dienstgeschäft <= letztes Dienstgeschäft <= Rückreise.
    Prüft Datum und, wo vorhanden, zusätzlich die Uhrzeit.
    """
    issues: list[Issue] = []
    stops = [
        ("Hinreise-Abfahrt",         "Textfeld20", "Textfeld21"),
        ("Beginn 1. Dienstgeschäft", "Textfeld22", "Textfeld23"),
        ("Ende letztes Dienstgesch.", "Textfeld24", "Textfeld25"),
        ("Rückreise-Abfahrt",        "Textfeld31", "Textfeld32"),
        ("Rückreise-Ankunft",        "Textfeld33", "Textfeld34"),
    ]

    parsed: list[tuple[str, Optional[datetime], str, str]] = []
    for name, dfld, tfld in stops:
        ds, ts = get_text(ctx, dfld), get_text(ctx, tfld)
        d = parse_date(ds)
        if ds and d is None:
            issues.append(Issue(Severity.ERROR, "reisedatum",
                                 f"{name}: Datum '{ds}' nicht lesbar", [dfld]))
        t = parse_time(ts)
        if ts and t is None:
            issues.append(Issue(Severity.WARNING, "reisedatum",
                                 f"{name}: Uhrzeit '{ts}' nicht lesbar", [tfld]))
        dt = datetime.combine(d, t or time(0, 0)) if d else None
        parsed.append((name, dt, dfld, tfld))

    prev_name, prev_dt = None, None
    for name, dt, dfld, tfld in parsed:
        if dt is None:
            continue
        if prev_dt is not None and dt < prev_dt:
            issues.append(Issue(
                Severity.ERROR, "reisedatum",
                f"'{name}' ({dt:%d.%m.%Y %H:%M}) liegt VOR "
                f"'{prev_name}' ({prev_dt:%d.%m.%Y %H:%M})",
                [dfld, tfld]))
        prev_name, prev_dt = name, dt

    _, last_dt, lf, _ = parsed[-1]
    if last_dt and last_dt.date() > date.today():
        issues.append(Issue(Severity.WARNING, "reisedatum",
                            f"Rückreisedatum {last_dt:%d.%m.%Y} liegt in der Zukunft",
                            [lf]))
    return issues

def check_rueckreise_begruendung(ctx: Context) -> list[Issue]:
    """Weicht die Rückreise vom Tag des letzten Dienstgeschäfts ab -> Begründung Pflicht."""
    ende = parse_date(get_text(ctx, "Textfeld24"))
    rueck = parse_date(get_text(ctx, "Textfeld33"))
    if ende and rueck and rueck != ende and not get_text(ctx, "Textfeld37"):
        return [Issue(Severity.ERROR, "rueckreise_begruendung",
                      f"Rückreise ({rueck:%d.%m.%Y}) weicht vom letzten Dienstgeschäft "
                      f"({ende:%d.%m.%Y}) ab, aber keine Begründung angegeben",
                      ["Textfeld37"])]
    return []

def check_plausibilitaet_dauer(ctx: Context) -> list[Issue]:
    """
    Plausibilitätsprüfung der Reisedaten:

    1. Abstand Anreise -> Beginn 1. Dienstgeschäft:
       mehr als 1 Tag Unterschied -> WARNING (zu früh angereist?).

    2. Gesamtdauer der Dienstreise (Hinreise-Abfahrt bis Rückreise-Ankunft,
       ersatzweise Ende letztes Dienstgeschäft):
         >  3 Tage  -> WARNING  (bitte prüfen)
         > 10 Tage  -> deutlichere WARNING
         > 21 Tage  -> ERROR
       Es wird nur die höchste zutreffende Stufe gemeldet.
    """
    issues: list[Issue] = []

    anreise = parse_date(get_text(ctx, "Textfeld20"))        # Hinreise-Abfahrtsdatum
    dienstbeginn = parse_date(get_text(ctx, "Textfeld22"))   # Beginn 1. Dienstgeschäft
    dienstende = parse_date(get_text(ctx, "Textfeld24"))     # Ende letztes Dienstgeschäft
    rueck_ankunft = parse_date(get_text(ctx, "Textfeld33"))  # Rückreise-Ankunft

    # --- 1) Anreise vs. Dienstbeginn -------------------------------------- #
    if anreise and dienstbeginn:
        diff_tage = (dienstbeginn - anreise).days
        if diff_tage > 1:
            issues.append(Issue(
                Severity.WARNING, "plausibilitaet",
                f"Zwischen Anreise ({anreise:%d.%m.%Y}) und Beginn des "
                f"1. Dienstgeschäfts ({dienstbeginn:%d.%m.%Y}) liegen "
                f"{diff_tage} Tage (> 1 Tag) - bitte prüfen",
                ["Textfeld20", "Textfeld22"]))
        elif diff_tage < 0:
            # Reihenfolgefehler fängt check_reisedatum ab; hier nur Hinweis
            issues.append(Issue(
                Severity.WARNING, "plausibilitaet",
                f"Beginn des 1. Dienstgeschäfts ({dienstbeginn:%d.%m.%Y}) liegt "
                f"VOR der Anreise ({anreise:%d.%m.%Y})",
                ["Textfeld20", "Textfeld22"]))

    # --- 2) Gesamtdauer der Dienstreise ----------------------------------- #
    ende_fuer_dauer = rueck_ankunft or dienstende
    ende_feld = "Textfeld33" if rueck_ankunft else "Textfeld24"
    if anreise and ende_fuer_dauer:
        # inklusive beider Tage: +1 (z. B. Mo an, Mo ab = 1 Tag)
        dauer_tage = (ende_fuer_dauer - anreise).days + 1
        if dauer_tage <= 0:
            # negative/0 Dauer -> Reihenfolgefehler, von check_reisedatum abgedeckt
            return issues
        felder = ["Textfeld20", ende_feld]
        if dauer_tage > 21:
            issues.append(Issue(
                Severity.ERROR, "plausibilitaet",
                f"Dienstreise dauert {dauer_tage} Tage (> 21 Tage) - "
                f"unplausibel lang, bitte korrigieren oder gesondert begründen",
                felder))
        elif dauer_tage > 10:
            issues.append(Issue(
                Severity.WARNING, "plausibilitaet",
                f"Dienstreise dauert {dauer_tage} Tage (> 10 Tage) - "
                f"ungewöhnlich lang, bitte genau prüfen",
                felder))
        elif dauer_tage > 3:
            issues.append(Issue(
                Severity.WARNING, "plausibilitaet",
                f"Dienstreise dauert {dauer_tage} Tage (> 3 Tage) - bitte prüfen",
                felder))

    return issues

# --- Soll-Werte aus .env --------------------------------------------------- #

def _check_env_match(ctx: Context, field_id: str, env_key: str, rule: str,
                     *, normalize: Callable[[str], str] = normalize_ws) -> list[Issue]:
    """Vergleicht den Feldwert mit dem Sollwert aus .env.

    Standard-Normalisierung ist `normalize_ws`: der Vergleich ist tolerant
    gegenüber Zeilenumbrüchen/Mehrfach-Whitespace, verlangt aber ansonsten
    exakte Übereinstimmung Zeichen für Zeichen.
    """
    soll = ctx.env.get(env_key)
    if not soll:
        return [Issue(Severity.INFO, rule,
                      f"{env_key} ist in .env nicht gesetzt - kein Abgleich möglich",
                      [field_id])]
    ist = get_text(ctx, field_id)
    if not ist:
        return [Issue(Severity.ERROR, rule,
                      f"{_label(ctx, field_id)} ist leer (erwartet: '{show_ws(soll)}')",
                      [field_id])]
    if normalize(ist) != normalize(soll):
        return [Issue(Severity.ERROR, rule,
                      f"{_label(ctx, field_id)}: '{show_ws(ist)}' "
                      f"≠ erwartet '{show_ws(soll)}'",
                      [field_id])]
    return []

def check_bezeichnung(ctx: Context) -> list[Issue]:
    """
    Bezeichnung der Organisationseinheit (Textfeld0) gegen RKA_STEMPEL.

    Der PDF-Wert ist typischerweise MEHRZEILIG ('...Darmstadt\\rFB18...').
    - Der Inhalt muss (whitespace-normalisiert) exakt dem Sollwert entsprechen.
    - Zusätzlich wird WARNEND geprüft, ob der Wert tatsächlich mehrzeilig ist,
      denn das Feld ist auf dem Formular zweizeilig vorgesehen.
    """
    issues = _check_env_match(ctx, "Textfeld0", "RKA_STEMPEL",
                              "Bezeichnung der Organisationseinheit",
                              normalize=normalize_ws)
    raw = ctx.data.get("Textfeld0")
    raw = "" if raw is None else str(raw)
    soll = ctx.env.get("RKA_STEMPEL") or ""
    # Nur prüfen, wenn der Soll selbst mehrzeilig ist und der Inhalt grundsätzlich passt
    if soll and is_multiline(soll) and not issues:
        if not is_multiline(raw):
            issues.append(Issue(Severity.WARNING, "Bezeichnung der Organisationseinheit",
                                "Wert stimmt inhaltlich, ist aber EINZEILIG - "
                                "erwartet wird ein mehrzeiliger Stempel", ["Textfeld0"]))
    return issues

def check_telefon(ctx: Context) -> list[Issue]:
    return _check_env_match(ctx, "Textfeld1", "RKA_TEL", "telefon",
                            normalize=lambda s: re.sub(r"[\s/().-]", "", s))

def check_email(ctx: Context) -> list[Issue]:
    issues = _check_env_match(ctx, "Textfeld2", "RKA_EMAIL", "email",
                              normalize=lambda s: normalize_ws(s).casefold())
    ist = get_text(ctx, "Textfeld2")
    if ist and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", ist):
        issues.append(Issue(Severity.WARNING, "email",
                            f"'{ist}' sieht nicht wie eine gültige E-Mail aus",
                            ["Textfeld2"]))
    return issues

def check_kostenstelle(ctx: Context) -> list[Issue]:
    return _check_env_match(ctx, "Textfeld15", "RKA_KOSTENSTELLE", "kostenstelle")

def check_projekt(ctx: Context) -> list[Issue]:
    """Projekt (Textfeld16) muss - wenn gesetzt - in der erlaubten Liste stehen."""
    erlaubt = allowed_projects(ctx.env)
    ist = get_text(ctx, "Textfeld16")
    if not ist:
        return []  # Projekt ist optional
    if not erlaubt:
        return [Issue(Severity.INFO, "projekt",
                      "RKA_PROJEKTNUMMERN nicht gesetzt - keine Prüfung der Projektnummer",
                      ["Textfeld16"])]
    if ist not in erlaubt:
        return [Issue(Severity.ERROR, "projekt",
                      f"Projekt '{ist}' nicht in erlaubter Liste "
                      f"({', '.join(sorted(erlaubt))})",
                      ["Textfeld16"])]
    return []

# --- Pflichtfelder & Konsistenz der Checkbox-Gruppen ----------------------- #

def check_pflichtfelder(ctx: Context) -> list[Issue]:
    """Felder, die immer ausgefüllt sein müssen."""
    pflicht = ["Textfeld3", "Textfeld4", "Textfeld14", "Textfeld28"]  # Name, Pers.Nr, Antragsdatum, Zweck
    return [Issue(Severity.ERROR, "pflichtfeld",
                  f"Pflichtfeld leer: {_label(ctx, f)}", [f])
            for f in pflicht if not get_text(ctx, f)]

def check_exklusive_gruppen(ctx: Context) -> list[Issue]:
    """Entweder/Oder-Checkboxgruppen: höchstens EINE Option darf gesetzt sein."""
    gruppen: list[tuple[str, list[str]]] = [
        ("Bankverbindung geändert?",         ["Kontrollkästchen2", "Kontrollkästchen3"]),
        ("Verpflegung gestellt?",            ["Kontrollkästchen8", "Kontrollkästchen9"]),
        ("Alleinige Zimmernutzung?",         ["Kontrollkästchen12", "Kontrollkästchen13"]),
        ("PKW triftiger Grund?",             ["Kontrollkästchen20", "Kontrollkästchen21"]),
        ("ÖV bezahlt durch",                 ["Kontrollkästchen25", "Kontrollkästchen26", "Kontrollkästchen27"]),
        ("Flug bezahlt durch",               ["Kontrollkästchen28", "Kontrollkästchen29", "Kontrollkästchen30"]),
        ("Bahncard",                         ["Kontrollkästchen22", "Kontrollkästchen23", "Kontrollkästchen24"]),
    ]
    issues = []
    for name, flds in gruppen:
        n = exactly_one(ctx, *flds)
        if n > 1:
            issues.append(Issue(Severity.ERROR, "exklusive_gruppe",
                                f"{name}: {n} Optionen angekreuzt, nur eine erlaubt", flds))
    return issues

# --- Bedingte Pflichtfelder (Checkbox -> zugehöriges Textfeld) ------------- #

def check_bedingte_felder(ctx: Context) -> list[Issue]:
    """Wenn eine Checkbox gesetzt ist, muss das abhängige Textfeld gefüllt sein."""
    regeln = [
        ("Kontrollkästchen3",  "Textfeld10", "Geänderte Bankverbindung: Kreditinstitut fehlt"),
        ("Kontrollkästchen3",  "Textfeld11", "Geänderte Bankverbindung: BIC fehlt"),
        ("Kontrollkästchen3",  "Textfeld12", "Geänderte Bankverbindung: IBAN fehlt"),
        ("Kontrollkästchen11", "Textfeld42", "Übernachtungskosten angekreuzt, aber Betrag fehlt"),
        ("Kontrollkästchen15", "Textfeld45", "Private Nächte angekreuzt, aber keine Nächte benannt"),
        ("Kontrollkästchen16", "Textfeld46", "Übernachtungspauschale angekreuzt, aber Betrag fehlt"),
        ("Kontrollkästchen18", "Textfeld49", "Privat-PKW angekreuzt, aber keine Strecken angegeben"),
        ("Kontrollkästchen18", "Textfeld50", "Privat-PKW angekreuzt, aber Gesamt-km fehlen"),
        ("Kontrollkästchen21", "Textfeld48", "Triftiger Grund PKW angekreuzt, aber keine Begründung"),
    ]
    return [Issue(Severity.ERROR, "bedingtes_feld", msg, [cb, tf])
            for cb, tf, msg in regeln
            if get_bool(ctx, cb) and not get_text(ctx, tf)]

# --- IBAN / BIC Format ----------------------------------------------------- #

def _iban_valid(iban: str) -> bool:
    iban = re.sub(r"\s", "", iban).upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{10,30}", iban):
        return False
    rearr = iban[4:] + iban[:4]
    digits = "".join(str(int(c, 36)) for c in rearr)
    return int(digits) % 97 == 1

def check_iban_bic(ctx: Context) -> list[Issue]:
    issues = []
    iban = get_text(ctx, "Textfeld12")
    if iban and not _iban_valid(iban):
        issues.append(Issue(Severity.ERROR, "iban",
                            f"IBAN '{iban}' ist ungültig (Prüfziffer/Format)", ["Textfeld12"]))
    bic = get_text(ctx, "Textfeld11")
    if bic and not re.fullmatch(r"[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?",
                                bic.replace(" ", "").upper()):
        issues.append(Issue(Severity.WARNING, "bic",
                            f"BIC '{bic}' entspricht nicht dem Format", ["Textfeld11"]))
    return issues

# --- Nebenkosten-Tabelle --------------------------------------------------- #

def check_nebenkosten(ctx: Context) -> list[Issue]:
    """
    6 Zeilen Nebenkosten: Art / Betrag / Begründung.
    Je Zeile: wenn irgendetwas ausgefüllt ist, müssen Art und Betrag da sein,
    und der Betrag muss eine Zahl sein.
    """
    zeilen = [
        ("Textfeld56", "Textfeld57", "Textfeld58"),
        ("Textfeld59", "Textfeld61", "Textfeld60"),
        ("Textfeld62", "Textfeld64", "Textfeld63"),
        ("Textfeld65", "Textfeld67", "Textfeld66"),
        ("Textfeld68", "Textfeld70", "Textfeld69"),
        ("Textfeld73", "Textfeld71", "Textfeld72"),
    ]
    issues: list[Issue] = []
    beantragt = get_bool(ctx, "Kontrollkästchen31")
    any_row = False
    for i, (art, betrag, begr) in enumerate(zeilen, 1):
        a, b, g = get_text(ctx, art), get_text(ctx, betrag), get_text(ctx, begr)
        if not (a or b or g):
            continue
        any_row = True
        if not a:
            issues.append(Issue(Severity.ERROR, "nebenkosten",
                                f"Zeile {i}: Betrag/Begründung ohne Art der Nebenkosten", [art]))
        if not b:
            issues.append(Issue(Severity.ERROR, "nebenkosten",
                                f"Zeile {i}: '{a}' ohne Betrag", [betrag]))
        elif parse_amount(b) is None:
            issues.append(Issue(Severity.ERROR, "nebenkosten",
                                f"Zeile {i}: Betrag '{b}' ist keine gültige Zahl", [betrag]))
    if any_row and not beantragt:
        issues.append(Issue(Severity.WARNING, "nebenkosten",
                            "Nebenkosten eingetragen, aber 'sonstige Auslagen' nicht angekreuzt",
                            ["Kontrollkästchen31"]))
    if beantragt and not any_row:
        issues.append(Issue(Severity.WARNING, "nebenkosten",
                            "'sonstige Auslagen' angekreuzt, aber keine Zeile ausgefüllt",
                            ["Kontrollkästchen31"]))
    return issues

# --- Übernachtung: Begründung über 80 € ------------------------------------ #

def check_uebernachtung_betrag(ctx: Context) -> list[Issue]:
    if get_bool(ctx, "Kontrollkästchen11"):
        betrag = parse_amount(get_text(ctx, "Textfeld42"))
        if betrag is not None and betrag > 80 and not get_text(ctx, "Textfeld44"):
            return [Issue(Severity.ERROR, "uebernachtung",
                          f"Übernachtungskosten {betrag:.2f} € > 80 €, "
                          "aber keine Begründung angegeben", ["Textfeld44"])]
    return []

# =========================================================================== #
# NEUE REGELN (modular ergänzt)
# =========================================================================== #
#
# Jede Regel ist eigenständig: eigene check_*-Funktion, Eintrag in RULES und
# RULE_TITLES weiter unten. Keine Änderung an bestehenden Regeln oder an
# get_bool. Reihenfolge der Blöcke: Stammdaten -> Reise/Zeit -> Fahrtkosten
# -> Verpflegung -> Übernachtung -> Beträge.

# --- Datum: Antragsdatum --------------------------------------------------- #

def check_antragsdatum(ctx: Context) -> list[Issue]:
    """
    Antragsdatum (Textfeld14) muss plausibel sein:
      - nicht VOR dem Ende des letzten Dienstgeschäfts (man beantragt
        Reisekosten nicht, bevor die Reise beendet ist)   -> ERROR
      - nicht in der Zukunft                               -> WARNING
    Nicht-lesbares Datum -> WARNING (Format prüfen).
    """
    issues: list[Issue] = []
    roh = get_text(ctx, "Textfeld14")
    if not roh:
        return issues  # Fehlen fängt check_pflichtfelder ab
    antrag = parse_date(roh)
    if antrag is None:
        return [Issue(Severity.WARNING, "antragsdatum",
                      f"Antragsdatum '{roh}' ist nicht lesbar", ["Textfeld14"])]

    ende = parse_date(get_text(ctx, "Textfeld24"))        # Ende letztes Dienstgeschäft
    rueck = parse_date(get_text(ctx, "Textfeld33"))       # Rückreise-Ankunft
    reiseende = rueck or ende
    if reiseende and antrag < reiseende:
        issues.append(Issue(
            Severity.ERROR, "antragsdatum",
            f"Antragsdatum ({antrag:%d.%m.%Y}) liegt VOR dem Reiseende "
            f"({reiseende:%d.%m.%Y})", ["Textfeld14"]))
    if antrag > date.today():
        issues.append(Issue(
            Severity.WARNING, "antragsdatum",
            f"Antragsdatum ({antrag:%d.%m.%Y}) liegt in der Zukunft",
            ["Textfeld14"]))
    return issues

# --- Datum: Ausschlussfrist ------------------------------------------------ #

def check_ausschlussfrist(ctx: Context) -> list[Issue]:
    """
    Reisekosten müssen innerhalb einer Frist beantragt werden (hier: 6 Monate
    nach Reiseende, konservativ gesetzt). Liegt das Reiseende länger zurück
    -> WARNING (Ausschlussfrist womöglich überschritten, bitte prüfen).
    """
    reiseende = parse_date(get_text(ctx, "Textfeld33")) or parse_date(get_text(ctx, "Textfeld24"))
    if not reiseende:
        return []
    tage = (date.today() - reiseende).days
    if tage > 183:  # ~6 Monate
        feld = "Textfeld33" if parse_date(get_text(ctx, "Textfeld33")) else "Textfeld24"
        return [Issue(Severity.WARNING, "ausschlussfrist",
                      f"Reiseende ({reiseende:%d.%m.%Y}) liegt {tage} Tage zurück "
                      f"(> 6 Monate) - Ausschlussfrist für Reisekosten prüfen",
                      [feld])]
    return []

# --- Reiseweg: Von/Nach-Konsistenz ----------------------------------------- #

def check_reiseweg_konsistenz(ctx: Context) -> list[Issue]:
    """
    Hin- und Rückweg sollten spiegelbildlich sein:
      Beginn: Von (Textfeld18)  ~ Ende: Nach (Textfeld30)   (zurück nach Hause)
      Beginn: Nach (Textfeld19) ~ Ende: Von (Textfeld29)    (Rückweg vom Ziel)
    Weichen die Ortsangaben ab -> WARNING (Dreh-/Tippfehler?).
    Nur geprüft, wenn alle vier Felder gefüllt sind.
    """
    def norm(fid: str) -> str:
        return normalize_ws(get_text(ctx, fid)).casefold()

    b_von, b_nach = norm("Textfeld18"), norm("Textfeld19")
    e_von, e_nach = norm("Textfeld29"), norm("Textfeld30")
    if not (b_von and b_nach and e_von and e_nach):
        return []  # unvollständig -> nicht beurteilbar

    issues: list[Issue] = []
    if b_von != e_nach:
        issues.append(Issue(
            Severity.WARNING, "reiseweg",
            f"Startort '{get_text(ctx, 'Textfeld18')}' (Beginn: Von) ≠ "
            f"Rückkehrort '{get_text(ctx, 'Textfeld30')}' (Ende: Nach) - bitte prüfen",
            ["Textfeld18", "Textfeld30"]))
    if b_nach != e_von:
        issues.append(Issue(
            Severity.WARNING, "reiseweg",
            f"Zielort '{get_text(ctx, 'Textfeld19')}' (Beginn: Nach) ≠ "
            f"Rückreise-Startort '{get_text(ctx, 'Textfeld29')}' (Ende: Von) - bitte prüfen",
            ["Textfeld19", "Textfeld29"]))
    return issues

# --- Dienstreise angeordnet/genehmigt -------------------------------------- #

def check_anordnung_genehmigung(ctx: Context) -> list[Issue]:
    """
    Dienstreise muss angeordnet (Kontrollkästchen0) ODER genehmigt
    (Kontrollkästchen1) sein:
      - keine von beiden gesetzt         -> ERROR
      - mindestens eine gesetzt, aber kein 'durch wen' (Textfeld9) -> ERROR
    """
    issues: list[Issue] = []
    angeordnet = get_bool(ctx, "Kontrollkästchen0")
    genehmigt = get_bool(ctx, "Kontrollkästchen1")
    if not (angeordnet or genehmigt):
        issues.append(Issue(
            Severity.ERROR, "anordnung",
            "Dienstreise weder angeordnet noch genehmigt angekreuzt",
            ["Kontrollkästchen0", "Kontrollkästchen1"]))
    elif not get_text(ctx, "Textfeld9"):
        issues.append(Issue(
            Severity.ERROR, "anordnung",
            "Dienstreise angeordnet/genehmigt, aber 'durch wen' (Textfeld9) fehlt",
            ["Textfeld9"]))
    return issues

# --- Bankverbindung: Aussage Pflicht --------------------------------------- #

def check_bankverbindung_aussage(ctx: Context) -> list[Issue]:
    """
    Es muss GENAU eine Aussage zur Bankverbindung getroffen werden:
    'nicht geändert' (Kontrollkästchen2) oder 'geändert' (Kontrollkästchen3).
    Keine von beiden -> ERROR. (Mehr als eine fängt check_exklusive_gruppen.)
    """
    n = exactly_one(ctx, "Kontrollkästchen2", "Kontrollkästchen3")
    if n == 0:
        return [Issue(Severity.ERROR, "bankverbindung",
                      "Keine Angabe, ob sich die Bankverbindung geändert hat",
                      ["Kontrollkästchen2", "Kontrollkästchen3"])]
    return []

# --- Abreiseort: genau eine Option ----------------------------------------- #

def check_abreiseort(ctx: Context) -> list[Issue]:
    """
    Abreiseort bei Beginn: genau eine der Optionen Wohnung (4) / Dienststelle (5)
    / Sonstiges (6).
      - keine gesetzt    -> WARNING
      - mehrere gesetzt  -> ERROR
    """
    felder = ["Kontrollkästchen4", "Kontrollkästchen5", "Kontrollkästchen6"]
    n = exactly_one(ctx, *felder)
    if n == 0:
        return [Issue(Severity.WARNING, "abreiseort",
                      "Kein Abreiseort angekreuzt (Wohnung / Dienststelle / Sonstiges)",
                      felder)]
    if n > 1:
        return [Issue(Severity.ERROR, "abreiseort",
                      f"{n} Abreiseorte angekreuzt, nur einer erlaubt", felder)]
    return []

# --- Fahrtkosten: beantragt -> Nachweis ------------------------------------ #

def check_fahrtkosten_konsistenz(ctx: Context) -> list[Issue]:
    """
    'Ich beantrage Fahrtkosten' (Kontrollkästchen17) <-> Nachweise.

    Als Nachweis gilt eines von:
      - Privat-PKW (Kontrollkästchen18) oder km (Textfeld50)
      - ÖV-Kosten  (Textfeld54)
      - Flugkosten (Textfeld55)
      - Bahncard   (22/23/24)

      beantragt, aber kein Nachweis  -> WARNING (leerer Fahrtkostenantrag)
      Nachweis da, aber nicht beantragt -> WARNING (Haken vergessen)
    """
    beantragt = get_bool(ctx, "Kontrollkästchen17")
    nachweis = (
        get_bool(ctx, "Kontrollkästchen18")
        or get_text(ctx, "Textfeld50")
        or get_text(ctx, "Textfeld54")
        or get_text(ctx, "Textfeld55")
        or exactly_one(ctx, "Kontrollkästchen22", "Kontrollkästchen23", "Kontrollkästchen24") > 0
    )
    if beantragt and not nachweis:
        return [Issue(Severity.WARNING, "fahrtkosten",
                      "Fahrtkosten beantragt, aber kein Beförderungsmittel/Betrag "
                      "angegeben (PKW/ÖV/Flug/Bahncard)",
                      ["Kontrollkästchen17"])]
    if nachweis and not beantragt:
        return [Issue(Severity.WARNING, "fahrtkosten",
                      "Fahrtkosten-Angaben vorhanden, aber 'Ich beantrage Fahrtkosten' "
                      "nicht angekreuzt", ["Kontrollkästchen17"])]
    return []

# --- Fahrtkosten: Betrag -> 'bezahlt durch' -------------------------------- #

def check_zahlweg(ctx: Context) -> list[Issue]:
    """
    Wenn ein ÖV-/Flug-Betrag eingetragen ist, muss GENAU eine 'bezahlt durch'-
    Box gesetzt sein. Außerdem WARNUNG bei möglicher Doppelerstattung:
    Betrag eingetragen UND 'bereits von TUD gezahlt' angekreuzt.
    """
    issues: list[Issue] = []
    blocks = [
        ("ÖV", "Textfeld54",
         ["Kontrollkästchen25", "Kontrollkästchen26", "Kontrollkästchen27"],
         "Kontrollkästchen26"),   # bereits von TUD gezahlt
        ("Flug", "Textfeld55",
         ["Kontrollkästchen28", "Kontrollkästchen29", "Kontrollkästchen30"],
         "Kontrollkästchen29"),
    ]
    for name, betrag_fld, zahl_boxes, tud_box in blocks:
        betrag = get_text(ctx, betrag_fld)
        if not betrag:
            continue
        n = exactly_one(ctx, *zahl_boxes)
        if n == 0:
            issues.append(Issue(
                Severity.ERROR, "zahlweg",
                f"{name}-Kosten '{betrag}' eingetragen, aber nicht angekreuzt, "
                f"wer gezahlt hat", zahl_boxes))
        if parse_amount(betrag) is not None and get_bool(ctx, tud_box):
            issues.append(Issue(
                Severity.WARNING, "zahlweg",
                f"{name}-Kosten '{betrag}' eingetragen, obwohl 'bereits von TUD "
                f"gezahlt' angekreuzt ist - mögliche Doppelerstattung",
                [betrag_fld, tud_box]))
    return issues

# --- Fahrtkosten: PKW-Freitext vs. Checkbox -------------------------------- #

def check_pkw_freitext(ctx: Context) -> list[Issue]:
    """
    Nennt das Beförderungsmittel (Textfeld26 Hinweg / Textfeld35 Rückweg)
    einen Privat-PKW ('PKW', 'Pkw', 'privat...kfz', 'auto'), ist aber die
    Checkbox 'Fahrt mit privatem Kraftfahrzeug' (Kontrollkästchen18) nicht
    gesetzt -> WARNING (Haken/Zuordnung prüfen).
    """
    muster = re.compile(r"\b(p\.?kw|privat\w*\s*kfz|privat\w*\s*fahrzeug|auto)\b",
                        re.IGNORECASE)
    treffer = [fid for fid in ("Textfeld26", "Textfeld35")
               if muster.search(get_text(ctx, fid))]
    if treffer and not get_bool(ctx, "Kontrollkästchen18"):
        return [Issue(Severity.WARNING, "pkw_freitext",
                      "Beförderungsmittel nennt einen privaten PKW, aber die Checkbox "
                      "'Fahrt mit privatem Kraftfahrzeug' ist nicht gesetzt",
                      treffer + ["Kontrollkästchen18"])]
    return []

# --- Fahrtkosten: PKW angeordnet / Mitfahrer ------------------------------- #

def check_pkw_details(ctx: Context) -> list[Issue]:
    """
    Details rund um die PKW-Nutzung:
      - 'Fahrt angeordnet' (Kontrollkästchen19) -> 'angeordnet durch' (Textfeld47) Pflicht
      - Mitfahrer-Anzahl (Textfeld51) > 0       -> Namen (Textfeld53) sollten gefüllt sein
      - Gesamt-km (Textfeld50) gefüllt          -> muss eine Zahl > 0 sein
    """
    issues: list[Issue] = []

    if get_bool(ctx, "Kontrollkästchen19") and not get_text(ctx, "Textfeld47"):
        issues.append(Issue(Severity.ERROR, "pkw_details",
                            "Fahrt angeordnet, aber 'angeordnet durch' (Textfeld47) fehlt",
                            ["Textfeld47"]))

    anzahl_roh = get_text(ctx, "Textfeld51")
    if anzahl_roh:
        anzahl = parse_amount(anzahl_roh)
        if anzahl is not None and anzahl > 0 and not get_text(ctx, "Textfeld53"):
            issues.append(Issue(Severity.WARNING, "pkw_details",
                                f"{anzahl_roh} mitgenommene Person(en), aber keine Namen "
                                f"(Textfeld53) angegeben", ["Textfeld53"]))

    km_roh = get_text(ctx, "Textfeld50")
    if km_roh:
        km = parse_amount(km_roh)
        if km is None:
            issues.append(Issue(Severity.ERROR, "pkw_details",
                                f"Gesamt-km '{km_roh}' ist keine gültige Zahl", ["Textfeld50"]))
        elif km <= 0:
            issues.append(Issue(Severity.ERROR, "pkw_details",
                                f"Gesamt-km '{km_roh}' muss größer als 0 sein", ["Textfeld50"]))
    return issues

# --- Verpflegung ----------------------------------------------------------- #

def check_verpflegung(ctx: Context) -> list[Issue]:
    """
    Konsistenz der Verpflegungs-Angaben:
      - Tagegeld beantragt (Kontrollkästchen7), aber weder 'Verpflegung gestellt
        ja' (9) noch 'nein' (8) angekreuzt            -> WARNING (unvollständig)
      - 'Verpflegung gestellt ja' (9), aber keine Mahlzeit (Textfeld38/39/40)
        benannt                                        -> WARNING
      - Mahlzeit-Datum außerhalb des Reisezeitraums    -> WARNING
    """
    issues: list[Issue] = []

    tagegeld = get_bool(ctx, "Kontrollkästchen7")
    gestellt_nein = get_bool(ctx, "Kontrollkästchen8")
    gestellt_ja = get_bool(ctx, "Kontrollkästchen9")

    if tagegeld and not (gestellt_nein or gestellt_ja):
        issues.append(Issue(Severity.WARNING, "verpflegung",
                            "Tagegeld beantragt, aber nicht angekreuzt, ob Verpflegung "
                            "gestellt wurde (ja/nein)",
                            ["Kontrollkästchen8", "Kontrollkästchen9"]))

    mahlzeiten = {
        "Frühstück": "Textfeld38",
        "Mittagessen": "Textfeld39",
        "Abendessen": "Textfeld40",
    }
    if gestellt_ja and not any(get_text(ctx, f) for f in mahlzeiten.values()):
        issues.append(Issue(Severity.WARNING, "verpflegung",
                            "'Verpflegung gestellt: ja' angekreuzt, aber keine Mahlzeit "
                            "(Frühstück/Mittag/Abend) mit Datum benannt",
                            list(mahlzeiten.values())))

    # Mahlzeit-Daten müssen im Reisezeitraum liegen
    start = parse_date(get_text(ctx, "Textfeld20"))
    ende = parse_date(get_text(ctx, "Textfeld33")) or parse_date(get_text(ctx, "Textfeld24"))
    if start and ende:
        for name, fid in mahlzeiten.items():
            roh = get_text(ctx, fid)
            if not roh:
                continue
            d = parse_date(roh)
            if d is None:
                issues.append(Issue(Severity.WARNING, "verpflegung",
                                    f"{name}-Datum '{roh}' ist nicht lesbar", [fid]))
            elif not (start <= d <= ende):
                issues.append(Issue(Severity.WARNING, "verpflegung",
                                    f"{name} am {d:%d.%m.%Y} liegt außerhalb des Reise"
                                    f"zeitraums ({start:%d.%m.%Y} - {ende:%d.%m.%Y})", [fid]))
    return issues

# --- Übernachtung: Kosten vs. Pauschale ------------------------------------ #

def check_uebernachtung_art(ctx: Context) -> list[Issue]:
    """
    Übernachtung: tatsächliche Kosten (Kontrollkästchen11) und Pauschale
    (Kontrollkästchen16) schließen sich aus -> beide gesetzt = ERROR.
    """
    if get_bool(ctx, "Kontrollkästchen11") and get_bool(ctx, "Kontrollkästchen16"):
        return [Issue(Severity.ERROR, "uebernachtung_art",
                      "Sowohl Übernachtungskosten als auch Übernachtungspauschale "
                      "angekreuzt - nur eines ist zulässig",
                      ["Kontrollkästchen11", "Kontrollkästchen16"])]
    return []

# --- Übernachtung: Zimmernutzung ------------------------------------------- #

def check_zimmernutzung(ctx: Context) -> list[Issue]:
    """
    Liegen Übernachtungskosten vor (Kontrollkästchen11), muss die alleinige
    Zimmernutzung beantwortet sein: genau eine von ja (12) / nein (13).
      - keine gesetzt -> WARNING
    'gemeinsam genutzt' (14) -> 'mit wem' (Textfeld43) Pflicht.
    (Mehrere ja/nein fängt check_exklusive_gruppen ab.)
    """
    issues: list[Issue] = []
    if get_bool(ctx, "Kontrollkästchen11"):
        if exactly_one(ctx, "Kontrollkästchen12", "Kontrollkästchen13") == 0:
            issues.append(Issue(Severity.WARNING, "zimmernutzung",
                                "Übernachtungskosten vorhanden, aber alleinige Zimmer"
                                "nutzung (ja/nein) nicht angekreuzt",
                                ["Kontrollkästchen12", "Kontrollkästchen13"]))
    if get_bool(ctx, "Kontrollkästchen14") and not get_text(ctx, "Textfeld43"):
        issues.append(Issue(Severity.ERROR, "zimmernutzung",
                            "'Dienstlich gemeinsam genutzt' angekreuzt, aber 'mit wem' "
                            "(Textfeld43) fehlt", ["Textfeld43"]))
    return issues

# --- Übernachtung bei Tagesreise ------------------------------------------- #

def check_uebernachtung_tagesreise(ctx: Context) -> list[Issue]:
    """
    Ist eine Übernachtung angekreuzt (10/11/16), die Reise aber eintägig
    (Anreisetag == Rückreisetag) -> WARNING (Übernachtung bei Tagesreise?).
    """
    uebernachtung = (get_bool(ctx, "Kontrollkästchen10")
                     or get_bool(ctx, "Kontrollkästchen11")
                     or get_bool(ctx, "Kontrollkästchen16"))
    if not uebernachtung:
        return []
    start = parse_date(get_text(ctx, "Textfeld20"))
    rueck = parse_date(get_text(ctx, "Textfeld33")) or parse_date(get_text(ctx, "Textfeld24"))
    if start and rueck and start == rueck:
        return [Issue(Severity.WARNING, "uebernachtung_tagesreise",
                      f"Übernachtung angekreuzt, aber Reise ist eintägig "
                      f"({start:%d.%m.%Y}) - bitte prüfen",
                      ["Textfeld20", "Textfeld33"])]
    return []

# --- Beträge: positiv und lesbar ------------------------------------------- #

def check_betraege(ctx: Context) -> list[Issue]:
    """
    Alle einzelnen Betragsfelder (außerhalb der Nebenkosten-Tabelle, die
    check_nebenkosten prüft): wenn gefüllt, müssen sie eine Zahl > 0 sein.
      - unparsbar  -> ERROR
      - <= 0       -> ERROR
    """
    felder = {
        "Textfeld13": "Erhaltener Abschlag",
        "Textfeld42": "Übernachtungskosten",
        "Textfeld46": "Übernachtungspauschalbetrag",
        "Textfeld54": "ÖV-Kosten",
        "Textfeld55": "Flugkosten",
    }
    issues: list[Issue] = []
    for fid, name in felder.items():
        roh = get_text(ctx, fid)
        if not roh:
            continue
        betrag = parse_amount(roh)
        if betrag is None:
            issues.append(Issue(Severity.ERROR, "betrag",
                                f"{name}: '{roh}' ist keine gültige Zahl", [fid]))
        elif betrag <= 0:
            issues.append(Issue(Severity.ERROR, "betrag",
                                f"{name}: Betrag '{roh}' muss größer als 0 sein", [fid]))
    return issues

# --- Stammdaten: Pers.-Nr. Format ------------------------------------------ #

def check_persnr_format(ctx: Context) -> list[Issue]:
    """
    Pers.-Nr. SAP (Textfeld4): sofern gefüllt, nur Ziffern (6-10 Stellen,
    konservativ). Abweichung -> WARNING. (Fehlen fängt check_pflichtfelder.)
    """
    roh = get_text(ctx, "Textfeld4")
    if roh and not re.fullmatch(r"\d{6,10}", roh):
        return [Issue(Severity.WARNING, "persnr",
                      f"Pers.-Nr. SAP '{roh}' entspricht nicht dem erwarteten Format "
                      f"(nur Ziffern, 6-10 Stellen)", ["Textfeld4"])]
    return []

# --- Stammdaten: IBAN DE-Länge --------------------------------------------- #

def check_iban_de_laenge(ctx: Context) -> list[Issue]:
    """
    Ergänzend zu check_iban_bic: deutsche IBAN (DE...) muss exakt 22 Stellen
    haben. Abweichung -> WARNING. (Prüfziffer/Grundformat macht check_iban_bic.)
    """
    iban = re.sub(r"\s", "", get_text(ctx, "Textfeld12")).upper()
    if iban.startswith("DE") and len(iban) != 22:
        return [Issue(Severity.WARNING, "iban_de",
                      f"Deutsche IBAN hat {len(iban)} statt 22 Stellen", ["Textfeld12"])]
    return []

# =========================================================================== #
# Registry + Runner
# =========================================================================== #

RULES: list[Callable[[Context], list[Issue]]] = [
    check_reisedatum,
    check_rueckreise_begruendung,
    check_plausibilitaet_dauer,
    check_bezeichnung,
    check_telefon,
    check_email,
    check_kostenstelle,
    check_projekt,
    check_pflichtfelder,
    check_exklusive_gruppen,
    check_bedingte_felder,
    check_iban_bic,
    check_nebenkosten,
    check_uebernachtung_betrag,
    check_antragsdatum,
    check_ausschlussfrist,
    check_reiseweg_konsistenz,
    check_anordnung_genehmigung,
    check_bankverbindung_aussage,
    check_abreiseort,
    check_fahrtkosten_konsistenz,
    check_zahlweg,
    check_pkw_freitext,
    check_pkw_details,
    check_verpflegung,
    check_uebernachtung_art,
    check_zimmernutzung,
    check_uebernachtung_tagesreise,
    check_betraege,
    check_persnr_format,
    check_iban_de_laenge,
]

# Menschenlesbare Titel je Regel-Funktion (für die Übersicht im Report).
RULE_TITLES: dict[str, str] = {
    "check_reisedatum":            "Reisedaten-Reihenfolge (Hin-/Rückreise, Dienstgeschäft)",
    "check_rueckreise_begruendung": "Begründung bei abweichender Rückreise",
    "check_plausibilitaet_dauer":  "Plausibilität der Reisedauer",
    "check_bezeichnung":           "Bezeichnung der Organisationseinheit",
    "check_telefon":               "Telefonnummer",
    "check_email":                 "E-Mail Kostenstellenverantwortlicher",
    "check_kostenstelle":          "Kostenstelle",
    "check_projekt":               "Projektnummer",
    "check_pflichtfelder":         "Pflichtfelder (Name, Pers.-Nr., Antragsdatum, Zweck)",
    "check_exklusive_gruppen":     "Exklusive Checkbox-Gruppen",
    "check_bedingte_felder":       "Bedingte Pflichtfelder (Checkbox -> Textfeld)",
    "check_iban_bic":              "IBAN / BIC",
    "check_nebenkosten":           "Nebenkosten-Tabelle",
    "check_uebernachtung_betrag":  "Übernachtung > 80 EUR Begründung",
    # --- neue Regeln ---
    "check_antragsdatum":          "Antragsdatum (nicht vor Reiseende / nicht in Zukunft)",
    "check_ausschlussfrist":       "Ausschlussfrist (Reiseende < 6 Monate her)",
    "check_reiseweg_konsistenz":   "Reiseweg-Konsistenz (Hin-/Rückweg spiegelbildlich)",
    "check_anordnung_genehmigung": "Dienstreise angeordnet/genehmigt + durch wen",
    "check_bankverbindung_aussage": "Bankverbindung: Aussage zwingend",
    "check_abreiseort":            "Abreiseort genau eine Option",
    "check_fahrtkosten_konsistenz": "Fahrtkosten beantragt <-> Nachweis",
    "check_zahlweg":               "Fahrtkosten: Betrag <-> 'bezahlt durch'",
    "check_pkw_freitext":          "PKW im Freitext vs. Checkbox",
    "check_pkw_details":           "PKW: Anordnung / Mitfahrer / km",
    "check_verpflegung":           "Verpflegung / Tagegeld-Konsistenz",
    "check_uebernachtung_art":     "Übernachtung: Kosten vs. Pauschale exklusiv",
    "check_zimmernutzung":         "Übernachtung: Zimmernutzung / gemeinsam genutzt",
    "check_uebernachtung_tagesreise": "Übernachtung bei Tagesreise (Plausibilität)",
    "check_betraege":              "Betragsfelder positiv und lesbar",
    "check_persnr_format":         "Pers.-Nr. SAP Format",
    "check_iban_de_laenge":        "IBAN DE-Länge (22 Stellen)",
}

@dataclass
class RuleResult:
    """Ergebnis einer einzelnen Regel-Ausführung."""
    func: str                 # Funktionsname, z. B. "check_reisedatum"
    title: str                # menschenlesbarer Titel
    issues: list[Issue]       # von dieser Regel erzeugte Issues
    crashed: bool = False     # Regel hat eine Exception geworfen

    @property
    def worst(self) -> Optional[Severity]:
        """Höchster Schweregrad unter den Issues (None = sauber)."""
        for sev in (Severity.ERROR, Severity.WARNING, Severity.INFO):
            if any(i.severity is sev for i in self.issues):
                return sev
        return None


def run_rules(data: dict, mapping: dict, env: Optional[dict] = None,
              rules: Optional[list] = None) -> list[RuleResult]:
    """Regeln ausführen und das Ergebnis PRO Regel zurückgeben."""
    ctx = Context(data=data, mapping=mapping,
                  env=env if env is not None else load_env())
    results: list[RuleResult] = []
    for rule in (rules or RULES):
        title = RULE_TITLES.get(rule.__name__, rule.__name__)
        try:
            found = rule(ctx)
            results.append(RuleResult(rule.__name__, title, found))
        except Exception as exc:  # eine kaputte Regel darf nicht alles stoppen
            crash = Issue(Severity.WARNING, rule.__name__,
                          f"Regel fehlgeschlagen: {exc!r}")
            results.append(RuleResult(rule.__name__, title, [crash], crashed=True))
    return results


def validate(data: dict, mapping: dict, env: Optional[dict] = None,
             rules: Optional[list] = None) -> list[Issue]:
    """Alle (oder ausgewählte) Regeln ausführen, flache Liste von Issues zurück."""
    issues: list[Issue] = []
    for res in run_rules(data, mapping, env, rules):
        issues.extend(res.issues)
    return issues


# Symbole/Marker für die Ausgabe
_SEV_MARK = {Severity.ERROR: "✗", Severity.WARNING: "⚠", Severity.INFO: "ℹ"}
_SEV_LABEL = {Severity.ERROR: "FEHLER", Severity.WARNING: "WARNUNGEN",
              Severity.INFO: "HINWEISE"}
# Singular/Plural für die Count-Notiz in der Regel-Checkliste
_SEV_NOUN = {
    Severity.ERROR:   ("Fehler", "Fehler"),
    Severity.WARNING: ("Warnung", "Warnungen"),
    Severity.INFO:    ("Hinweis", "Hinweise"),
}


def _count_note(sev: Severity, n: int) -> str:
    singular, plural = _SEV_NOUN[sev]
    return f" ({n} {singular if n == 1 else plural})"


def print_report(results: list[RuleResult] | list[Issue]) -> None:
    """
    Hübscher Report:
      1. Alle Issues, gruppiert nach ERROR -> WARNING -> INFO.
      2. Übersicht ALLER geprüften Regeln mit Status-Marker
         (✓ sauber, ⚠ Warnung/Hinweis, ✗ Fehler).

    Akzeptiert sowohl eine Liste von RuleResult (volle Übersicht) als auch
    - rückwärtskompatibel - eine flache Liste von Issue (dann ohne die
    Regel-Checkliste, weil die Zuordnung fehlt).
    """
    # Rückwärtskompatibilität: flache Issue-Liste
    legacy = results and isinstance(results[0], Issue)
    if legacy:
        all_issues: list[Issue] = list(results)            # type: ignore[arg-type]
        rule_results: list[RuleResult] = []
    else:
        rule_results = list(results)                       # type: ignore[assignment]
        all_issues = [i for r in rule_results for i in r.issues]

    width = 72

    # --- Teil 1: Issues nach Severity ------------------------------------- #
    print("=" * width)
    print(" PRÜFBERICHT REISEKOSTENABRECHNUNG")
    print("=" * width)

    any_issue = False
    for sev in (Severity.ERROR, Severity.WARNING, Severity.INFO):
        bucket = [i for i in all_issues if i.severity is sev]
        if not bucket:
            continue
        any_issue = True
        print(f"\n{_SEV_MARK[sev]} {_SEV_LABEL[sev]} ({len(bucket)})")
        print("-" * width)
        for iss in bucket:
            f = f"  [{', '.join(iss.fields)}]" if iss.fields else ""
            print(f"  {_SEV_MARK[sev]} {iss.rule}: {iss.message}{f}")

    if not any_issue:
        print("\n✓ Keine Beanstandungen gefunden.")

    # --- Teil 2: Checkliste aller Regeln ---------------------------------- #
    if rule_results:
        print(f"\n{'=' * width}")
        print(" GEPRÜFTE REGELN")
        print("=" * width)
        for r in rule_results:
            w = r.worst
            if r.crashed:
                mark, note = "‼", " (Regel abgestürzt)"
            elif w is None:
                mark, note = "✓", ""
            else:
                mark = _SEV_MARK[w]
                note = _count_note(w, len(r.issues))
            print(f"  {mark} {r.title}{note}")

    # --- Zusammenfassung -------------------------------------------------- #
    counts = {s: sum(1 for i in all_issues if i.severity is s) for s in Severity}
    print(f"\n{'=' * width}")
    print(f" {counts[Severity.ERROR]} Fehler, "
          f"{counts[Severity.WARNING]} Warnungen, "
          f"{counts[Severity.INFO]} Hinweise", end="")
    if rule_results:
        ok = sum(1 for r in rule_results if r.worst is None and not r.crashed)
        print(f"  |  {ok}/{len(rule_results)} Regeln ohne Beanstandung", end="")
    print(f"\n{'=' * width}")

# --------------------------------------------------------------------------- #
# Extraktion aus dem PDF
# --------------------------------------------------------------------------- #

def extract_rka(path: str) -> dict:
    """Liest alle Formularwerte aus dem RKA-PDF."""
    from pikepdf.form import Pdf, Form
    data: dict = {}
    with Pdf.open(path) as pdf:
        form = Form(pdf)
        for field_name, field in form.items():
            if field.is_text or field.is_choice or field.is_radio_button:
                data[field_name] = field.value
            elif field.is_checkbox:
                data[field_name] = field.checked
    return data

# =========================================================================== #
# QUERPRÜFUNG (Cross-Check über mehrere PDFs)
# =========================================================================== #
#
# Annahme fuer den Stapel: UNTERSCHIEDLICHE Personen, die zum SELBEN Event
# gefahren sind - gemeinsam hin/zurueck oder getrennt. Die Querpruefung testet
# daher NICHT auf "gleiche Person", sondern auf Event-Konsistenz und auf eine
# plausible gemeinsame Fahrt (eine Person rechnet den PKW ab, die anderen sind
# Mitfahrer -> keine doppelte km-Erstattung).
#
# Eine Cross-Regel bekommt ALLE Dokumente als Liste von Doc und gibt Issues
# zurueck; der Dateibezug steht in der Message. Neue Cross-Regel: Funktion
# schreiben + in CROSS_RULES/CROSS_TITLES eintragen.

@dataclass
class Doc:
    """Ein eingelesenes RKA-Dokument."""
    path: str                 # Dateipfad
    name: str                 # Anzeigename (Basename)
    data: dict                # field_id -> Wert
    ctx: Context              # vorbereiteter Context (data+mapping+env)


def _doc_date(doc: Doc, field_id: str) -> Optional[date]:
    return parse_date(get_text(doc.ctx, field_id))


def _person(doc: Doc) -> str:
    """Anzeigename des Antragstellers (Name, Vorname)."""
    return get_text(doc.ctx, "Textfeld3") or f"({doc.name})"


def _name_key(s: str) -> str:
    """Normalisierter Namensschluessel fuer Mitfahrer-Abgleich: Reihenfolge-
    unabhaengig (Nachname/Vorname), ohne Mehrfach-Whitespace, case-insensitiv."""
    toks = re.split(r"[\s,]+", normalize_ws(s).casefold())
    return " ".join(sorted(t for t in toks if t))


def _name_tokens(s: str) -> set[str]:
    """Menge normalisierter Namens-Tokens (Vor-/Nachname), case-insensitiv."""
    return {t for t in re.split(r"[\s,]+", normalize_ws(s).casefold()) if t}


def _split_mitfahrer(roh: str) -> list[str]:
    """Mitfahrer-Freitext in einzelne Namen zerlegen.

    Namen enthalten selbst oft ein Komma ('Nachname, Vorname'), deshalb wird
    primaer an EINDEUTIGEN Trennern (Semikolon, Zeilenumbruch, ' und ', '/')
    getrennt. Nur wenn KEINER davon vorkommt, wird als Fallback am Komma
    getrennt (dann ist das Komma der Trenner, nicht Teil eines Namens).
    """
    hat_eindeutig = bool(re.search(r"[;\n\r/]| und ", roh))
    trenner = r"[;\n\r/]| und " if hat_eindeutig else r","
    return [n.strip() for n in re.split(trenner, roh) if n.strip()]


def check_x_event_zweck(docs: list["Doc"]) -> list[Issue]:
    """
    Alle Dokumente sollen dasselbe Event betreffen: Zweck der Reise (Textfeld28)
    sollte uebereinstimmen. Mehr als eine verschiedene (nicht-leere) Zweck-
    Angabe -> WARNING (unterschiedliche Events in einem Stapel?).
    """
    zwecke: dict[str, list[str]] = {}
    for d in docs:
        z = normalize_ws(get_text(d.ctx, "Textfeld28"))
        if z:
            zwecke.setdefault(z.casefold(), []).append(d.name)
    if len(zwecke) > 1:
        beschreibung = "; ".join(
            f"{', '.join(dateien)}" for dateien in zwecke.values())
        return [Issue(Severity.WARNING, "x_event_zweck",
                      "Unterschiedliche Reisezwecke im Stapel - gehoeren alle "
                      f"zum selben Event? Gruppen: {beschreibung}",
                      ["Textfeld28"])]
    return []


def check_x_event_zeitfenster(docs: list["Doc"]) -> list[Issue]:
    """
    Beim selben Event sollten die Dienstgeschaefts-Daten beieinanderliegen.
    Spannt das Dienstgeschaeft (frueheste Beginn Textfeld22 bis spaetestes Ende
    Textfeld24) ueber mehr als 14 Tage -> WARNING.
    """
    beginn = [d for d in (( _doc_date(x, "Textfeld22"), x) for x in docs) if d[0]]
    ende = [d for d in (( _doc_date(x, "Textfeld24"), x) for x in docs) if d[0]]
    if len(beginn) < 2 and len(ende) < 2:
        return []
    alle = [dt for dt, _ in beginn] + [dt for dt, _ in ende]
    if len(alle) < 2:
        return []
    spanne = (max(alle) - min(alle)).days
    if spanne > 14:
        return [Issue(Severity.WARNING, "x_event_zeitfenster",
                      f"Dienstgeschaefts-Daten im Stapel spannen {spanne} Tage "
                      f"({min(alle):%d.%m.%Y} - {max(alle):%d.%m.%Y}) - selbes Event?",
                      ["Textfeld22", "Textfeld24"])]
    return []


def _is_pkw_fahrer(doc: Doc) -> bool:
    """Dokument rechnet eine eigene Privat-PKW-Fahrt ab."""
    km = parse_amount(get_text(doc.ctx, "Textfeld50"))
    return get_bool(doc.ctx, "Kontrollkästchen18") or (km is not None and km > 0)


def check_x_gemeinsame_fahrt(docs: list["Doc"]) -> list[Issue]:
    """
    Gemeinsame Fahrt zum selben Event: Fahren mehrere am selben Tag dieselbe
    Strecke, sollte idealerweise EINE Person den PKW abrechnen und die anderen
    als Mitfahrer gelten.

    Gruppierung je (Abfahrtsdatum Textfeld20, Zielort Textfeld19, Startort
    Textfeld18), case-insensitiv. In einer Gruppe mit >= 2 PKW-Fahrern:
      -> WARNING (mehrere rechnen Privat-PKW fuer dieselbe Strecke/den selben
         Tag ab - fuhren sie wirklich getrennt, oder doppelte km-Erstattung?).
    """
    issues: list[Issue] = []
    gruppen: dict[tuple, list[Doc]] = {}
    for d in docs:
        start = _doc_date(d, "Textfeld20")
        von = normalize_ws(get_text(d.ctx, "Textfeld18")).casefold()
        nach = normalize_ws(get_text(d.ctx, "Textfeld19")).casefold()
        if start and (von or nach):
            gruppen.setdefault((start, von, nach), []).append(d)

    for (start, von, nach), gruppe in gruppen.items():
        fahrer = [d for d in gruppe if _is_pkw_fahrer(d)]
        if len(fahrer) >= 2:
            namen = ", ".join(f"{_person(d)} ({d.name})" for d in fahrer)
            strecke = f"{get_text(fahrer[0].ctx, 'Textfeld18')} -> " \
                      f"{get_text(fahrer[0].ctx, 'Textfeld19')}"
            issues.append(Issue(
                Severity.WARNING, "x_gemeinsame_fahrt",
                f"{len(fahrer)} Personen rechnen am {start:%d.%m.%Y} Privat-PKW "
                f"fuer dieselbe Strecke ({strecke}) ab: {namen} - gemeinsame "
                f"Fahrt? Dann darf nur eine die km abrechnen",
                ["Textfeld20", "Textfeld18", "Textfeld19", "Textfeld50"]))
    return issues


def check_x_mitfahrer_abgleich(docs: list["Doc"]) -> list[Issue]:
    """
    Nennt ein PKW-Fahrer Mitfahrer (Textfeld53), und ein genannter Mitfahrer
    taucht im Stapel als eigener Antragsteller auf, der FUER DIESELBE Fahrt
    (gleicher Abfahrtstag) ebenfalls Privat-PKW/km abrechnet -> WARNING
    (Mitfahrer kann keine eigene PKW-Fahrt fuer dieselbe Strecke haben).
    """
    issues: list[Issue] = []
    # Index: Antragsteller mit ihren Namens-Tokens
    antragsteller: list[tuple[set[str], Doc]] = [
        (_name_tokens(get_text(d.ctx, "Textfeld3")), d) for d in docs
    ]

    for fahrer in docs:
        mitfahrer_roh = get_text(fahrer.ctx, "Textfeld53")
        if not mitfahrer_roh or not _is_pkw_fahrer(fahrer):
            continue
        f_tag = _doc_date(fahrer, "Textfeld20")
        for roh in _split_mitfahrer(mitfahrer_roh):
            m_tokens = _name_tokens(roh)
            if not m_tokens:
                continue
            for kand_tokens, kandidat in antragsteller:
                if kandidat is fahrer or not kand_tokens:
                    continue
                # Mitfahrer-Nennung matcht, wenn ihre Tokens Teilmenge der
                # Antragsteller-Tokens sind ('Bea' -> 'Beispiel, Bea').
                if not m_tokens <= kand_tokens:
                    continue
                if _is_pkw_fahrer(kandidat) and _doc_date(kandidat, "Textfeld20") == f_tag:
                    issues.append(Issue(
                        Severity.ERROR, "x_mitfahrer_abgleich",
                        f"'{roh}' ist bei {_person(fahrer)} ({fahrer.name}) "
                        f"als Mitfahrer genannt, rechnet aber in {kandidat.name} "
                        f"selbst eine Privat-PKW-Fahrt am "
                        f"{f_tag:%d.%m.%Y} ab - doppelte km-Erstattung?",
                        ["Textfeld53", "Textfeld50"]))
    return issues


def check_x_person_doppelt(docs: list["Doc"]) -> list[Issue]:
    """
    Taucht DIESELBE Person (gleicher Name) mehrfach im Stapel auf, muessen ihre
    Stammdaten konsistent sein: Pers.-Nr. (Textfeld4) / IBAN (Textfeld12).
    Abweichung -> WARNING. (Verschiedene Personen sind der Normalfall und
    loesen hier nichts aus.)
    """
    issues: list[Issue] = []
    personen: dict[str, list[Doc]] = {}
    for d in docs:
        key = _name_key(get_text(d.ctx, "Textfeld3"))
        if key:
            personen.setdefault(key, []).append(d)

    for gruppe in personen.values():
        if len(gruppe) < 2:
            continue
        for fid, label in (("Textfeld4", "Pers.-Nr."), ("Textfeld12", "IBAN")):
            werte = {normalize_ws(get_text(d.ctx, fid)) for d in gruppe
                     if get_text(d.ctx, fid)}
            if len(werte) > 1:
                dateien = ", ".join(d.name for d in gruppe)
                issues.append(Issue(
                    Severity.WARNING, "x_person_doppelt",
                    f"{label} fuer '{_person(gruppe[0])}' weicht zwischen "
                    f"Dokumenten ab ({' / '.join(sorted(werte))}) - {dateien}",
                    [fid]))
    return issues


CROSS_RULES: list[Callable[[list["Doc"]], list[Issue]]] = [
    check_x_event_zweck,
    check_x_event_zeitfenster,
    check_x_gemeinsame_fahrt,
    check_x_mitfahrer_abgleich,
    check_x_person_doppelt,
]

CROSS_TITLES: dict[str, str] = {
    "check_x_event_zweck":        "Selbes Event (Reisezweck konsistent)",
    "check_x_event_zeitfenster":  "Event-Zeitfenster plausibel",
    "check_x_gemeinsame_fahrt":   "Gemeinsame Fahrt: nur einer rechnet PKW ab",
    "check_x_mitfahrer_abgleich": "Mitfahrer rechnet nicht selbst PKW ab",
    "check_x_person_doppelt":     "Doppelte Person: Stammdaten konsistent",
}


def run_cross_rules(docs: list["Doc"],
                    rules: Optional[list] = None) -> list[RuleResult]:
    """Querprüfungen ausführen, Ergebnis pro Cross-Regel zurückgeben."""
    results: list[RuleResult] = []
    for rule in (rules or CROSS_RULES):
        title = CROSS_TITLES.get(rule.__name__, rule.__name__)
        try:
            found = rule(docs)
            results.append(RuleResult(rule.__name__, title, found))
        except Exception as exc:
            crash = Issue(Severity.WARNING, rule.__name__,
                          f"Querprüfung fehlgeschlagen: {exc!r}")
            results.append(RuleResult(rule.__name__, title, [crash], crashed=True))
    return results


def print_cross_report(results: list[RuleResult], doc_count: int) -> None:
    """Report-Block für die Querprüfung über mehrere PDFs."""
    width = 72
    all_issues = [i for r in results for i in r.issues]
    print(f"\n{'=' * width}")
    print(f" QUERPRÜFUNG ({doc_count} Dokumente - selbes Event)")
    print("=" * width)

    any_issue = False
    for sev in (Severity.ERROR, Severity.WARNING, Severity.INFO):
        bucket = [i for i in all_issues if i.severity is sev]
        if not bucket:
            continue
        any_issue = True
        print(f"\n{_SEV_MARK[sev]} {_SEV_LABEL[sev]} ({len(bucket)})")
        print("-" * width)
        for iss in bucket:
            print(f"  {_SEV_MARK[sev]} {iss.rule}: {iss.message}")
    if not any_issue:
        print("\n✓ Keine dokumentübergreifenden Beanstandungen.")

    print(f"\n{'-' * width}")
    for r in results:
        w = r.worst
        if r.crashed:
            mark, note = "‼", " (Querprüfung abgestürzt)"
        elif w is None:
            mark, note = "✓", ""
        else:
            mark, note = _SEV_MARK[w], _count_note(w, len(r.issues))
        print(f"  {mark} {r.title}{note}")


# =========================================================================== #
# CLI
# =========================================================================== #

def _worst_severity(issues: list[Issue]) -> Optional[Severity]:
    for sev in (Severity.ERROR, Severity.WARNING, Severity.INFO):
        if any(i.severity is sev for i in issues):
            return sev
    return None


def _collect_pdfs(paths: list[str]) -> list[str]:
    """Argumente zu einer PDF-Dateiliste auflösen: einzelne Dateien, Glob-
    Muster (*.pdf) und Verzeichnisse (nicht-rekursiv) werden unterstützt."""
    import glob as _glob
    out: list[str] = []
    for p in paths:
        if os.path.isdir(p):
            out.extend(sorted(_glob.glob(os.path.join(p, "*.pdf"))))
        elif any(ch in p for ch in "*?["):
            out.extend(sorted(_glob.glob(p)))
        else:
            out.append(p)
    seen: set[str] = set()
    uniq: list[str] = []
    for p in out:
        ap = os.path.abspath(p)
        if ap not in seen:
            seen.add(ap)
            uniq.append(p)
    return uniq


def _results_to_dict(results: list[RuleResult]) -> list[dict]:
    return [
        {
            "func": r.func,
            "title": r.title,
            "crashed": r.crashed,
            "worst": r.worst.value if r.worst else None,
            "issues": [
                {"severity": i.severity.value, "rule": i.rule,
                 "message": i.message, "fields": i.fields}
                for i in r.issues
            ],
        }
        for r in results
    ]


def main(argv: Optional[list[str]] = None) -> int:
    import argparse
    import json

    parser = argparse.ArgumentParser(
        prog="rka-validierung",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        description="Regelbasierte Validierung von Reisekostenabrechnungen (RKA). "
                    "Prüft jede PDF einzeln und - bei mehreren - zusätzlich "
                    "dokumentübergreifend (selbes Event, gemeinsame Fahrt).",
        epilog="""\
Beispiele:
  # Eine einzelne Abrechnung prüfen
  rka-validierung RKA.pdf

  # Mehrere Dateien gemeinsam prüfen (einzeln + Querprüfung über alle)
  rka-validierung reise1.pdf reise2.pdf reise3.pdf

  # Alle PDFs eines Ordners (nicht-rekursiv) - z. B. ein Event-Stapel
  rka-validierung ./event-gamescom/

  # Per Glob-Muster
  rka-validierung "abrechnungen/*.pdf"

  # Eigene .env mit Sollwerten (Stempel, Tel., E-Mail, Kostenstelle, Projekte)
  rka-validierung RKA.pdf --env firma.env

  # Nur Einzelprüfung, Querprüfung überspringen
  rka-validierung *.pdf --no-cross

  # Kompakte Zusammenfassung je Datei (eine Zeile), keine Detail-Reports
  rka-validierung ./stapel/ --quiet

  # Maschinenlesbare Ausgabe (z. B. für Weiterverarbeitung / CI)
  rka-validierung *.pdf --json > bericht.json

Exit-Codes:
  0  keine Fehler (höchstens Warnungen/Hinweise)
  1  mindestens ein ERROR gefunden (einzeln oder dokumentübergreifend)
  2  keine der angegebenen PDFs konnte gelesen werden
""")
    parser.add_argument("pdfs", nargs="+",
                        help="Eine oder mehrere PDF-Dateien, Glob-Muster "
                             "(z. B. '*.pdf') oder Verzeichnisse.")
    parser.add_argument("--env", default=".env",
                        help="Pfad zur .env mit Sollwerten (Standard: .env).")
    parser.add_argument("--no-cross", action="store_true",
                        help="Keine Querprüfung über die Dokumente durchführen.")
    parser.add_argument("--json", action="store_true",
                        help="Ergebnis als JSON ausgeben (maschinenlesbar).")
    parser.add_argument("-q", "--quiet", action="store_true",
                        help="Nur Zusammenfassung je Datei, keine Detail-Reports.")
    args = parser.parse_args(argv)

    files = _collect_pdfs(args.pdfs)
    if not files:
        print("Keine PDF-Dateien gefunden.", file=sys.stderr)
        return 2

    env = load_env(args.env)
    docs: list[Doc] = []
    read_errors: list[tuple[str, str]] = []

    for path in files:
        name = os.path.basename(path)
        try:
            data = extract_rka(path)
        except Exception as exc:
            read_errors.append((name, str(exc)))
            continue
        ctx = Context(data=data, mapping=mapping, env=env)
        docs.append(Doc(path=path, name=name, data=data, ctx=ctx))

    # --- Einzelprüfung je Dokument ---------------------------------------- #
    per_doc: list[tuple[Doc, list[RuleResult]]] = []
    worst_overall: Optional[Severity] = None
    for d in docs:
        results = run_rules(d.data, mapping, env)
        per_doc.append((d, results))
        w = _worst_severity([i for r in results for i in r.issues])
        if w is Severity.ERROR:
            worst_overall = Severity.ERROR
        elif w is Severity.WARNING and worst_overall is not Severity.ERROR:
            worst_overall = Severity.WARNING

    # --- Querprüfung ------------------------------------------------------ #
    cross_results: list[RuleResult] = []
    if not args.no_cross and len(docs) >= 2:
        cross_results = run_cross_rules(docs)
        cw = _worst_severity([i for r in cross_results for i in r.issues])
        if cw is Severity.ERROR:
            worst_overall = Severity.ERROR
        elif cw is Severity.WARNING and worst_overall is not Severity.ERROR:
            worst_overall = Severity.WARNING

    # --- Ausgabe ---------------------------------------------------------- #
    if args.json:
        payload = {
            "documents": [
                {"file": d.name, "path": d.path, "rules": _results_to_dict(r)}
                for d, r in per_doc
            ],
            "cross_check": _results_to_dict(cross_results),
            "read_errors": [{"file": n, "error": e} for n, e in read_errors],
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        for d, results in per_doc:
            print(f"\n### Datei: {d.name}")
            if args.quiet:
                all_i = [i for r in results for i in r.issues]
                counts = {s: sum(1 for i in all_i if i.severity is s) for s in Severity}
                print(f"  {counts[Severity.ERROR]} Fehler, "
                      f"{counts[Severity.WARNING]} Warnungen, "
                      f"{counts[Severity.INFO]} Hinweise")
            else:
                print_report(results)
        if cross_results:
            print_cross_report(cross_results, len(docs))
        elif not args.no_cross and len(docs) < 2:
            print("\n(Querprüfung übersprungen - nur ein Dokument.)")

        if read_errors:
            print(f"\n{'=' * 72}")
            print(" LESEFEHLER")
            print("=" * 72)
            for n, e in read_errors:
                print(f"  ✗ {n}: {e}")

    # --- Exit-Code -------------------------------------------------------- #
    if read_errors and not docs:
        return 2
    if worst_overall is Severity.ERROR:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
