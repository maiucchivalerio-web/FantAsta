"""Prova di Bzzoiro Sports Data (BSD) per la Serie A: indisponibili (infortuni/squalifiche) e rigori.

Esplorativa: legge la documentazione pubblica per trovare gli endpoint, poi prova poche chiamate
e stampa le risposte accorciate. Mai la chiave.
"""
import atexit
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://sports.bzzoiro.com"
KEY = os.environ.get("BSD_KEY", "")
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


def fetch(url, auth=True):
    headers = {"User-Agent": "FantAsta-probe"}
    if auth:
        headers["Authorization"] = f"Token {KEY}"
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return None, str(e)


def api(path, params=None, limit=2500):
    query = "?" + urllib.parse.urlencode(params) if params else ""
    status, body = fetch(BASE + path + query)
    log(f"### GET {path}{query} → HTTP {status}")
    log("```")
    log(body[:limit])
    log("```")
    try:
        return status, json.loads(body)
    except ValueError:
        return status, None


def items(data):
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        for k in ("results", "data", "items", "response"):
            if isinstance(data.get(k), list):
                return data[k]
    return []


log("## Prova BSD (Bzzoiro) — Serie A")
log("### Endpoint nella documentazione")
paths = set()
for url in (f"{BASE}/docs/", f"{BASE}/free-football-api/"):
    status, html = fetch(url, auth=False)
    log(f"- {url} → HTTP {status}")
    if status == 200:
        paths.update(re.findall(r"(/api/[a-z0-9_\-/{}<>:]+)", html))
        for w in ("unavailable", "injur", "penalt", "lineup", "missing"):
            log(f"  - '{w}' citato nella pagina: {w in html.lower()}")
log("- " + (", ".join(sorted(paths)) if paths else "nessun endpoint estratto"))

if not KEY:
    log("ERRORE: segreto BSD_KEY mancante.")
    raise SystemExit(1)

# Schema OpenAPI: parametri e campi esatti degli endpoint che ci interessano
st, schema_txt = fetch(BASE + "/api/schema/?format=json")
log(f"### Schema → HTTP {st}")
try:
    schema = json.loads(schema_txt)
except ValueError:
    schema = None
    log(schema_txt[:500])
if schema:
    for path, ops in sorted(schema.get("paths", {}).items()):
        get = ops.get("get") or {}
        params = [p.get("name") for p in get.get("parameters", [])]
        log(f"- {path}: parametri {params}")
    comps = schema.get("components", {}).get("schemas", {})
    for name, sch in comps.items():
        props = list((sch.get("properties") or {}).keys())
        if any(w in " ".join(props).lower() for w in ("unavailable", "injur", "lineup", "penalt", "missing")) or name.lower().startswith(("event", "match", "player")):
            log(f"- schema {name}: {props}")

# Elenco campionati (paginato) per trovare la Serie A
serie_a, page = None, 1
while not serie_a and page <= 6:
    _, leagues = api("/api/leagues/", {"page": page}, limit=300)
    for lg in items(leagues):
        if str(lg.get("name", "")).strip().lower() == "serie a" and "ital" in str(lg.get("country", "")).lower():
            serie_a = lg.get("id")
    if not (leagues or {}).get("next"):
        break
    page += 1
log(f"- Serie A id: {serie_a}")

if serie_a:
    for params in ({"league": serie_a, "status": "finished"}, {"league": serie_a}, {"league_id": serie_a}):
        st, ev = api("/api/events/", params, limit=4000)
        evs = items(ev)
        if evs:
            blob = json.dumps(evs).lower()
            for w in ("unavailable_players", "injur", "suspen", "doubt", "penalt", "lineup", "minute"):
                log(f"- '{w}' presente negli eventi: {w in blob}")
            first = evs[0]
            log(f"- Campi di una partita: {sorted(first.keys()) if isinstance(first, dict) else type(first)}")
            if isinstance(first, dict) and first.get("id"):
                api(f"/api/events/{first['id']}/", limit=6000)
                api(f"/api/v2/matches/{first['id']}/", limit=6000)
            break

log("")
log("Fine prova.")
