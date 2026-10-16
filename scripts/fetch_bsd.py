"""Scarica da BSD (Bzzoiro) per la Serie A: rose con infortuni, probabili formazioni della prossima
giornata e rigori dalle partite giocate. Salva in data/bsd-serie-a.json (sovrascritto a ogni esecuzione,
tranne i rigori che sono incrementali)."""
import json
import os
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

BASE = "https://sports.bzzoiro.com"
KEY = os.environ.get("BSD_KEY", "")
LEAGUE_ID = 4  # Serie A su BSD
SEASON_START = os.environ.get("SEASON_START", "2026-08-01")
PATH = "data/bsd-serie-a.json"
used = 0


def api(path, params=None):
    global used
    used += 1
    url = BASE + path + ("?" + urllib.parse.urlencode(params) if params else "")
    req = urllib.request.Request(url, headers={"Authorization": f"Token {KEY}", "User-Agent": "FantAsta"})
    try:
        with urllib.request.urlopen(req, timeout=40) as r:
            return json.load(r)
    except urllib.error.HTTPError as e:
        print(f"HTTP {e.code} su {path}: {e.read().decode('utf-8', 'replace')[:200]}")
        return None


def paged(path, params):
    out, offset = [], 0
    while True:
        data = api(path, {**params, "limit": 100, "offset": offset}) or {}
        batch = data.get("results") or data.get("events") or []
        out.extend(batch)
        if not data.get("next") or not batch:
            return out
        offset += len(batch)


def slim_players(lst):
    return [{"name": p.get("name"), "short": p.get("short_name"), "pos": p.get("position"),
             "score": p.get("ai_score")} for p in (lst or [])]


def main():
    if not KEY:
        raise SystemExit("Segreto BSD_KEY mancante.")
    old = {}
    if os.path.exists(PATH):
        with open(PATH, encoding="utf-8") as f:
            old = json.load(f)
    today = date.today()

    # 1) Rose con disponibilità (infortuni) per ogni squadra di Serie A
    teams = paged("/api/v2/teams/", {"league_id": LEAGUE_ID})
    squads = {}
    for t in teams:
        sq = api(f"/api/v2/teams/{t['id']}/squad/") or {}
        players = (sq if isinstance(sq, list) else (sq.get("players") or sq.get("squad") or sq.get("results") or []))
        if not players:
            print(f"Rosa vuota per {t.get('name')}: chiavi risposta {list(sq.keys())[:12] if isinstance(sq, dict) else type(sq)}")
        squads[t.get("name")] = [{
            "name": p.get("name"), "short": p.get("short_name"), "pos": p.get("position"),
            "availability": p.get("availability"), "injury": p.get("injury_type"),
            "return": p.get("injury_expected_return"),
        } for p in players]
    print(f"Rose scaricate: {len(squads)} squadre")

    # 2) Probabili formazioni delle partite dei prossimi 7 giorni
    upcoming = paged("/api/v2/events/", {"league_id": LEAGUE_ID, "date_from": today.isoformat(),
                                          "date_to": (today + timedelta(days=7)).isoformat()})
    predicted = []
    for ev in upcoming:
        if ev.get("status") not in ("notstarted", "scheduled", None):
            continue
        lu = api(f"/api/v2/events/{ev['id']}/lineups/") or {}
        sides = lu.get("lineups") or {}
        entry = {"id": ev["id"], "date": ev.get("event_date"), "round": ev.get("round_number"),
                 "home": ev.get("home_team"), "away": ev.get("away_team"),
                 "status": lu.get("lineup_status"), "unavailable": lu.get("unavailable_players")}
        for side in ("home", "away"):
            s = sides.get(side) or {}
            entry[side + "_lineup"] = {"formation": s.get("formation"), "confidence": s.get("confidence"),
                                       "xi": slim_players(s.get("players")), "bench": slim_players(s.get("substitutes"))}
        predicted.append(entry)
    print(f"Probabili formazioni: {len(predicted)} partite")

    # 3) Rigori dalle partite giocate (incidenti), incrementale
    pens = old.get("penalties", {})
    finished = paged("/api/v2/events/", {"league_id": LEAGUE_ID, "date_from": SEASON_START,
                                          "date_to": today.isoformat(), "status": "finished"})
    sample_types = set()
    for ev in finished:
        eid = str(ev["id"])
        if eid in pens:
            continue
        inc = api(f"/api/v2/events/{eid}/incidents/") or {}
        items = inc.get("incidents") if isinstance(inc, dict) else inc
        found = []
        for it in items or []:
            blob = json.dumps(it, ensure_ascii=False).lower()
            sample_types.add(str(it.get("incident_type") or it.get("type") or "")[:40])
            if "penalt" in blob and "shootout" not in blob:
                found.append(it)
        pens[eid] = {"home": ev.get("home_team"), "away": ev.get("away_team"), "round": ev.get("round_number"), "items": found}
    print(f"Partite giocate analizzate per i rigori: {len(pens)} · tipi di incidenti visti: {sorted(sample_types)[:30]}")
    print(f"Incidenti con rigore trovati: {sum(len(v['items']) for v in pens.values())}")
    if any(v["items"] for v in pens.values()):
        ex = next(v["items"][0] for v in pens.values() if v["items"])
        print("Esempio incidente rigore:", json.dumps(ex, ensure_ascii=False)[:600])

    os.makedirs("data", exist_ok=True)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "squads": squads, "predicted": predicted, "penalties": pens},
                  f, ensure_ascii=False, separators=(",", ":"))
    injured = sum(1 for s in squads.values() for p in s if (p.get("availability") or "").lower() not in ("", "available", "none"))
    print(f"Giocatori non disponibili nelle rose: {injured}")
    print(f"Richieste BSD usate: {used}")


if __name__ == "__main__":
    main()
