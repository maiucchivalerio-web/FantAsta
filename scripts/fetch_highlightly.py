"""Scarica formazioni ed eventi delle partite di Serie A giocate (Highlightly) in data/serie-a-<anno>.json.

Incrementale: salta le partite già salvate. Rispetta un tetto di richieste (MAX_REQUESTS)
perché il piano gratuito ne concede 100 al giorno. Priorità: prima tutte le formazioni, poi gli eventi.
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone

BASE = "https://soccer.highlightly.net"
KEY = os.environ.get("HIGHLIGHTLY_KEY", "")
SEASON = int(os.environ.get("SEASON", "2026"))
LEAGUE_ID = 115669  # Serie A su Highlightly
MAX_REQUESTS = int(os.environ.get("MAX_REQUESTS", "85"))
PATH = f"data/serie-a-{SEASON}.json"

used = 0


class Budget(Exception):
    pass


def api(path, params=None):
    global used
    if used >= MAX_REQUESTS:
        raise Budget()
    used += 1
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"x-rapidapi-key": KEY, "User-Agent": "FantAsta"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:300]
        if e.code == 429:
            print(f"Limite giornaliero raggiunto ({path}): {body}")
            raise Budget()
        raise RuntimeError(f"HTTP {e.code} su {path}: {body}")


def load():
    if os.path.exists(PATH):
        with open(PATH, encoding="utf-8") as f:
            return json.load(f)
    return {"season": SEASON, "matches": {}}


def save(db):
    db["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    os.makedirs(os.path.dirname(PATH), exist_ok=True)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump(db, f, ensure_ascii=False, separators=(",", ":"))


def slim_player(p):
    return {"id": p.get("id"), "name": p.get("name"), "pos": p.get("position")}


def slim_team(t):
    return {
        "formation": t.get("formation"),
        "xi": [[slim_player(p) for p in row] for row in (t.get("initialLineup") or [])],
        "bench": [slim_player(p) for p in (t.get("substitutes") or [])],
    }


def list_matches():
    """Tutte le partite della stagione, paginando; se la paginazione non avanza si ferma."""
    seen, offset = {}, 0
    while True:
        data = api("/matches", {"leagueId": LEAGUE_ID, "season": SEASON, "limit": 100, "offset": offset})
        batch = data.get("data", []) if isinstance(data, dict) else []
        new = [m for m in batch if m.get("id") not in seen]
        for m in new:
            seen[m["id"]] = m
        # Si ferma quando una pagina non porta partite nuove (fine elenco, o offset ignorato dall'API)
        if not batch or not new or len(seen) >= 380:
            break
        offset += len(batch)
    return list(seen.values())


def main():
    if not KEY:
        raise SystemExit("Segreto HIGHLIGHTLY_KEY mancante.")
    db = load()
    stored = db["matches"]
    try:
        matches = list_matches()
        print(f"Partite in calendario: {len(matches)}")
        for m in matches:
            mid = str(m["id"])
            state = (m.get("state") or {})
            finished = (state.get("description") or "").lower() == "finished"
            entry = stored.setdefault(mid, {})
            entry.update({
                "round": m.get("round"), "date": m.get("date"),
                "home": (m.get("homeTeam") or {}).get("name"),
                "away": (m.get("awayTeam") or {}).get("name"),
                "score": (state.get("score") or {}).get("current"),
                "finished": finished,
            })
        todo = sorted((k for k, v in stored.items() if v.get("finished")), key=lambda k: stored[k].get("date") or "")
        # 1) formazioni di tutte le partite giocate, 2) eventi (cambi, gol, rigori)
        for mid in todo:
            if "lineups" not in stored[mid]:
                lu = api(f"/lineups/{mid}")
                stored[mid]["lineups"] = {"home": slim_team(lu.get("homeTeam") or {}), "away": slim_team(lu.get("awayTeam") or {})}
        for mid in todo:
            if "events" not in stored[mid]:
                ev = api(f"/events/{mid}")
                stored[mid]["events"] = [{
                    "team": (e.get("team") or {}).get("name"), "time": e.get("time"), "type": e.get("type"),
                    "player": e.get("player"), "playerId": e.get("playerId"),
                    "in": e.get("substituted"), "inId": e.get("assistingPlayerId"), "assist": e.get("assist"),
                } for e in (ev if isinstance(ev, list) else [])]
    except Budget:
        print(f"Tetto di richieste raggiunto ({used}): salvo quanto scaricato, rilancia più tardi per completare.")
    finally:
        save(db)
    played = [v for v in stored.values() if v.get("finished")]
    print(f"Richieste usate: {used}")
    print(f"Partite giocate: {len(played)} · con formazioni: {sum('lineups' in v for v in played)} · con eventi: {sum('events' in v for v in played)}")
    types = sorted({e.get('type') for v in played for e in v.get('events', [])})
    print(f"Tipi di evento visti: {types}")


if __name__ == "__main__":
    main()
