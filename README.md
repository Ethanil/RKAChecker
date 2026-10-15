# RKA-Checker

Regelbasierte Validierung von Reisekostenabrechnungen (RKA-PDFs) als
Kommandozeilen-Tool. Prüft jede PDF einzeln gegen ~30 Regeln und – bei mehreren
Dateien – zusätzlich dokumentübergreifend (selbes Event, gemeinsame Fahrt,
doppelte km-Erstattung).

## Nutzung

Repo herunterladen, dann einfach:

```powershell
py main.py RKA.pdf
```

Beim **ersten** Start installiert `main.py` die benötigte Abhängigkeit
(`pikepdf`) automatisch in die gerade verwendete Python-Umgebung und startet
sich einmal neu. Danach läuft jeder weitere Aufruf sofort. Kein manuelles
`pip install`, keine EXE – der Quellcode bleibt voll editierbar.

> Voraussetzung: Python ≥ 3.11 mit funktionierendem `pip`.
> Manuelle Installation (optional): `py -m pip install -r requirements.txt`

### Beispiele

```powershell
py main.py RKA.pdf                      # eine Abrechnung
py main.py reise1.pdf reise2.pdf        # mehrere (einzeln + Querprüfung)
py main.py .\event-gamescom\            # alle PDFs eines Ordners
py main.py "abrechnungen\*.pdf"         # Glob-Muster
py main.py RKA.pdf --env firma.env      # eigene Sollwerte-Datei
py main.py *.pdf --no-cross             # ohne Querprüfung
py main.py .\stapel\ --quiet            # nur Kurz-Zusammenfassung je Datei
py main.py *.pdf --json > bericht.json  # maschinenlesbar
```

Alle Optionen und Exit-Codes: `py main.py --help`.

## Sollwerte (.env)

Firmen-/Instituts-spezifische Sollwerte für den Abgleich stehen in `.env`:

```
RKA_STEMPEL=Bezeichnung
RKA_TEL=12345
RKA_EMAIL=name@tu-darmstadt.de
RKA_KOSTENSTELLE=123456
RKA_PROJEKTNUMMERN=P1234,P5678
```

Fehlt ein Schlüssel, wird die betroffene Regel als Hinweis übersprungen
(kein Fehler).

## Eigene Regeln

Einzelregel: Funktion `check_*(ctx) -> list[Issue]` schreiben und in `RULES`
+ `RULE_TITLES` eintragen. Dokumentübergreifende Regel: `check_x_*(docs)` und
in `CROSS_RULES` + `CROSS_TITLES` eintragen.
