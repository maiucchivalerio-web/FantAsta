"""Prova del piano gratuito Highlightly per la Serie A 2026/27.

1) Legge la documentazione pubblica per elencare gli endpoint (nessuna richiesta API).
2) Fa poche richieste esplorative (max ~6) e stampa risposte accorciate: mai la chiave.
"""
import atexit
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://soccer.highlightly.net"
KEY = os.environ.get("HIGHLIGHTLY_KEY", "")
SEASON = os.environ.get("SEASON", "2026")
MATCH_DATE = os.environ.get("MATCH_DATE", "")  # es. 2026-10-11: giorno con partite già giocate
DOCS = [
    "https://highlightly.net/football-api/documentation/",
    "https://highlightly.net/football-api/",
]

out = []


@atexit.register
def write_summary():
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path and out:
        with open(path, "a", encoding="utf-8") as f:
            f.write("\n".join(out) + "\n")


def log(line=""):
    print(line)
    out.append(line)


def fetch(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "FantAsta-probe", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:  # rete, DNS, timeout
        return None, str(e)


def api(path, params=None, limit=1500):
    query = "?" + urllib.parse.urlencode(params) if params else ""
    status, body = fetch(BASE + path + query, {"x-rapidapi-key": KEY})
    try:
        data = json.loads(body)
    except ValueError:
        data = None
    log(f"### GET {path}{query} → HTTP {status}")
    log("```")
    log(body[:limit])
    log("```")
    return status, data


def items(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("data", "response", "results", "items"):
            if isinstance(data.get(k), list):
                return data[k]
    return []


log("## Prova Highlightly — Serie A")

log("### Endpoint trovati nella documentazione")
paths = set()
for url in DOCS:
    status, html = fetch(url)
    log(f"- {url} → HTTP {status}")
    if status == 200:
        for m in re.findall(r"(?:soccer|sports)\.highlightly\.net(/[A-Za-z0-9_\-/{}]+)", html):
            paths.add(m)
        for m in re.findall(r'"(/(?:football/)?[a-z][a-z\-]+(?:/\{[A-Za-z]+\})?)"', html):
            paths.add(m)
log("- " + (", ".join(sorted(paths)) if paths else "nessun endpoint estratto"))

if not KEY:
    log("ERRORE: il segreto HIGHLIGHTLY_KEY non è impostato nel repository.")
    raise SystemExit(1)

# Campionato: cerca Serie A in Italia
_, leagues = api("/leagues", {"countryCode": "IT"})
league_id = None
for lg in items(leagues):
    if "serie a" in str(lg.get("name", "")).lower():
        league_id = lg.get("id")
        break
log(f"- Serie A id: {league_id}")

if league_id:
    params = {"leagueId": league_id, "season": SEASON, "limit": 20}
    if MATCH_DATE:
        params["date"] = MATCH_DATE
    _, matches = api("/matches", params, limit=800)
    all_m = items(matches)
    finished = [m for m in all_m if "finish" in json.dumps(m.get("state", m.get("status", ""))).lower()]
    log(f"- Partite restituite: {len(all_m)}, terminate: {len(finished)}")
    pick = finished[0] if finished else (all_m[0] if all_m else None)
    if pick:
        mid = pick.get("id")
        log(f"- Partita di prova id={mid}")
        api(f"/lineups/{mid}", limit=3500)
        api(f"/events/{mid}", limit=3500)
        api(f"/statistics/{mid}", limit=800)

log("")
log("Fine prova: leggere le risposte sopra per capire cosa include il piano.")
