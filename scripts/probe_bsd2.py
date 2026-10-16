"""Seconda prova BSD: endpoint di calcio utili (probabili formazioni, rose/infortuni, statistiche, incidenti)."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

BASE = "https://sports.bzzoiro.com"
KEY = os.environ.get("BSD_KEY", "")


def fetch(path, params=None, auth=True):
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    headers = {"User-Agent": "FantAsta-probe"}
    if auth:
        headers["Authorization"] = f"Token {KEY}"
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=headers), timeout=40) as r:
            return r.status, r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")


def show(path, params=None, limit=2500):
    st, body = fetch(path, params)
    print(f"### GET {path}{'?' + urllib.parse.urlencode(params) if params else ''} → HTTP {st}")
    print(body[:limit])
    print()
    try:
        return json.loads(body)
    except ValueError:
        return None


st, txt = fetch("/api/schema/", {"format": "json"}, auth=False)
schema = json.loads(txt)
print("## Endpoint calcio (/api/...)")
for path, ops in sorted(schema["paths"].items()):
    if path.startswith("/api/"):
        get = ops.get("get") or {}
        print(f"- {path} {[p.get('name') for p in get.get('parameters', [])]}")
print()

# Prossime partite di Serie A (league_id=4) e partite giocate di ieri/oggi
nxt = show("/api/v2/events/", {"league_id": 4, "date_from": "2026-10-17", "date_to": "2026-10-19"}, 1500)
done = show("/api/v2/events/", {"league_id": 4, "date_from": "2026-10-04", "date_to": "2026-10-05"}, 800)


def ids(d):
    if isinstance(d, dict):
        for k in ("results", "events", "data"):
            if isinstance(d.get(k), list):
                return [x.get("id") for x in d[k]]
    return []


up = ids(nxt)
past = ids(done)
if up:
    for path in (f"/api/v2/events/{up[0]}/predicted-lineups/", f"/api/v2/events/{up[0]}/lineups/", f"/api/predicted-lineups/{up[0]}/"):
        show(path, limit=3500)
if past:
    for path in (f"/api/v2/events/{past[0]}/incidents/", f"/api/v2/events/{past[0]}/player-stats/"):
        show(path, limit=3500)
