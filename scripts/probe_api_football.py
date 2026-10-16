"""Prova del piano API-Football: verifica cosa è accessibile per la Serie A 2026/27.

Fa poche richieste (6) e stampa solo un riepilogo: mai la chiave.
"""
import atexit
import json
import os
import sys
import urllib.request

BASE = "https://v3.football.api-sports.io"
KEY = os.environ.get("API_FOOTBALL_KEY", "")
LEAGUE = 135  # Serie A
SEASON = int(os.environ.get("SEASON", "2026"))

out = []


@atexit.register
def write_summary():
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary and out:
        with open(summary, "a", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")


def log(line=""):
    print(line)
    out.append(line)


def get(path):
    req = urllib.request.Request(BASE + path, headers={"x-apisports-key": KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)


def errors_of(data):
    err = data.get("errors")
    return err if err else None


if not KEY:
    log("ERRORE: il segreto API_FOOTBALL_KEY non è impostato nel repository.")
    sys.exit(1)

log(f"## Prova API-Football — Serie A, stagione {SEASON}/{(SEASON + 1) % 100:02d}")

status = get("/status")
if errors_of(status):
    log(f"- /status: errore {errors_of(status)}")
    sys.exit(1)
resp = status.get("response", {})
sub = resp.get("subscription", {}) if isinstance(resp, dict) else {}
req = resp.get("requests", {}) if isinstance(resp, dict) else {}
log(f"- Piano: {sub.get('plan')} · attivo: {sub.get('active')} · richieste oggi: {req.get('current')}/{req.get('limit_day')}")

leagues = get(f"/leagues?id={LEAGUE}")
seasons = []
for item in leagues.get("response", []):
    seasons = item.get("seasons", [])
target = next((s for s in seasons if s.get("year") == SEASON), None)
log(f"- Stagioni elencate: {', '.join(str(s.get('year')) for s in seasons[-6:])}")
if target:
    cov = target.get("coverage", {})
    fx = cov.get("fixtures", {})
    log(f"- Copertura {SEASON}: formazioni={fx.get('lineups')} eventi={fx.get('events')} "
        f"stats giocatori partita={fx.get('statistics_players')} giocatori={cov.get('players')} "
        f"infortuni={cov.get('injuries')} pronostici={cov.get('predictions')}")
else:
    log(f"- La stagione {SEASON} non compare nell'elenco.")

fixtures = get(f"/fixtures?league={LEAGUE}&season={SEASON}&status=FT")
if errors_of(fixtures):
    log(f"- /fixtures: BLOCCATO → {errors_of(fixtures)}")
    log("")
    log("ESITO: il piano gratuito NON dà accesso a questa stagione.")
    sys.exit(0)
played = fixtures.get("response", [])
log(f"- Partite giocate disponibili: {len(played)}")
if not played:
    log("ESITO: nessuna partita giocata restituita.")
    sys.exit(0)

last = sorted(played, key=lambda f: f["fixture"]["timestamp"])[-1]
fid = last["fixture"]["id"]
home, away = last["teams"]["home"]["name"], last["teams"]["away"]["name"]
log(f"- Partita di prova: {home} - {away} (giornata: {last['league'].get('round')})")

lineups = get(f"/fixtures/lineups?fixture={fid}")
if errors_of(lineups):
    log(f"- Formazioni: BLOCCATE → {errors_of(lineups)}")
else:
    lu = lineups.get("response", [])
    if lu:
        t = lu[0]
        names = [p["player"]["name"] for p in t.get("startXI", [])][:4]
        log(f"- Formazioni: OK · {t['team']['name']} {t.get('formation')} · titolari es. {', '.join(names)}… · panchina {len(t.get('substitutes', []))}")
    else:
        log("- Formazioni: risposta vuota")

events = get(f"/fixtures/events?fixture={fid}")
if errors_of(events):
    log(f"- Eventi (cambi, gol, rigori): BLOCCATI → {errors_of(events)}")
else:
    ev = events.get("response", [])
    subs = [e for e in ev if e.get("type") == "subst"]
    pens = [e for e in ev if "Penalty" in (e.get("detail") or "")]
    log(f"- Eventi: OK · {len(ev)} eventi, di cui {len(subs)} cambi e {len(pens)} rigori")
    if subs:
        s = subs[0]
        log(f"  es. cambio {s['time'].get('elapsed')}': {s['player'].get('name')} ↔ {s.get('assist', {}).get('name')}")

injuries = get(f"/injuries?league={LEAGUE}&season={SEASON}")
if errors_of(injuries):
    log(f"- Infortuni: BLOCCATI → {errors_of(injuries)}")
else:
    log(f"- Infortuni/indisponibili registrati: {len(injuries.get('response', []))}")

log("")
log("ESITO: il piano gratuito dà accesso a questa stagione.")
