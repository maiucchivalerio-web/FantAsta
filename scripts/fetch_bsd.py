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
    if teams:
        print(f"Campi squadra: {sorted(teams[0].keys())}")
    logos = {}
    for t in teams:
        for k, v in t.items():
            if isinstance(v, str) and any(w in k.lower() for w in ("logo", "crest", "image", "badge")) and v.startswith("http"):
                logos[t.get("name")] = v
                break
    print(f"Stemmi trovati: {len(logos)}")
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
                                          "date_to": (today + timedelta(days=14)).isoformat()})
    upcoming = [ev for ev in upcoming if ev.get("status") in ("notstarted", "scheduled", None)]
    upcoming.sort(key=lambda ev: ev.get("event_date") or "")
    # Solo la prima partita futura di ogni squadra
    seen_teams, todo = set(), []
    for ev in upcoming:
        teams_ev = {ev.get("home_team"), ev.get("away_team")}
        if teams_ev - seen_teams:
            todo.append(ev)
            seen_teams |= teams_ev
    recent = paged("/api/v2/events/", {"league_id": LEAGUE_ID, "date_from": (today - timedelta(days=10)).isoformat(),
                                        "date_to": today.isoformat(), "status": "finished"})
    recent.sort(key=lambda ev: ev.get("event_date") or "", reverse=True)
    predicted = []

    def add_lineup(ev, kind):
        lu = api(f"/api/v2/events/{ev['id']}/lineups/") or {}
        sides = lu.get("lineups") or {}
        entry = {"id": ev["id"], "date": ev.get("event_date"), "round": ev.get("round_number"),
                 "home": ev.get("home_team"), "away": ev.get("away_team"), "kind": kind,
                 "status": lu.get("lineup_status"), "unavailable": lu.get("unavailable_players")}
        for side in ("home", "away"):
            s = sides.get(side) or {}
            entry[side + "_lineup"] = {"formation": s.get("formation"), "confidence": s.get("confidence"),
                                       "xi": slim_players(s.get("players")), "bench": slim_players(s.get("substitutes"))}
        predicted.append(entry)
        return entry

    covered = set()
    for ev in todo:
        e = add_lineup(ev, "next")
        for side in ("home", "away"):
            if e[side + "_lineup"]["xi"]:
                covered.add(e[side])
    # Squadre senza probabile formazione: ultima formazione realmente schierata
    for ev in recent:
        if {ev.get("home_team"), ev.get("away_team")} - covered:
            e = add_lineup(ev, "last")
            for side in ("home", "away"):
                if e[side + "_lineup"]["xi"]:
                    covered.add(e[side])
    print(f"Formazioni: {sum(1 for p in predicted if p['kind'] == 'next')} prossime, {sum(1 for p in predicted if p['kind'] == 'last')} ultime giocate · squadre coperte: {len(covered)}")

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

    # 4) Classifica (per la difficoltà del calendario)
    standings = []
    st = api(f"/api/v2/leagues/{LEAGUE_ID}/standings/") or {}
    rows = st.get("standings") or st.get("results") or st.get("table") or (st if isinstance(st, list) else [])
    if rows and isinstance(rows[0], dict) and isinstance(rows[0].get("rows") or rows[0].get("table"), list):
        rows = rows[0].get("rows") or rows[0].get("table")
    if rows:
        print(f"Campi classifica: {sorted(rows[0].keys())[:20]}")
    for r in rows:
        team = r.get("team")
        name = team.get("name") if isinstance(team, dict) else (r.get("team_name") or team)
        standings.append({"team": name, "pos": r.get("position") or r.get("rank"), "pts": r.get("points") or r.get("pts"),
                          "played": r.get("played") or r.get("matches_played"), "gf": r.get("goals_for"), "ga": r.get("goals_against")})
    print(f"Classifica: {len(standings)} squadre")

    # 5) Statistiche per giocatore di ogni partita giocata (incrementale) -> fantamedia stimata
    pstats = old.get("player_stats", {})
    team_names = {}
    for ev in finished:
        team_names[ev.get("home_team_id")] = ev.get("home_team")
        team_names[ev.get("away_team_id")] = ev.get("away_team")
    shown_keys = False
    for ev in finished:
        eid = str(ev["id"])
        if eid in pstats:
            continue
        items, page = [], 1
        while page <= 5:
            data = api("/api/player-stats/", {"event": eid, "page": page}) or {}
            batch = data.get("results") or []
            items.extend(batch)
            if not data.get("next") or not batch:
                break
            page += 1
        if items and not shown_keys:
            print(f"Campi statistiche giocatore: {sorted(items[0].keys())[:45]}")
            print(f"Esempio player: {json.dumps(items[0].get('player'), ensure_ascii=False)[:300]}")
            shown_keys = True
        rows_ev = []
        for it in items:
            pl = it.get("player") or {}
            team = pl.get("team") if isinstance(pl, dict) else None
            tname = team.get("name") if isinstance(team, dict) else team_names.get(team) or team_names.get(it.get("team_id"))
            rows_ev.append({
                "name": pl.get("name"), "short": pl.get("short_name"), "pos": pl.get("position"), "team": tname,
                "min": it.get("minutes_played"), "rating": it.get("rating"), "g": it.get("goals"), "a": it.get("goal_assist"),
                "yc": it.get("yellow_card"), "rc": it.get("red_card"), "pm": it.get("penalty_miss"), "ps": it.get("penalty_save"),
                "gc": it.get("goals_conceded"),
            })
        pstats[eid] = {"home": ev.get("home_team"), "away": ev.get("away_team"), "round": ev.get("round_number"), "players": rows_ev}
    print(f"Statistiche giocatori: {len(pstats)} partite, {sum(len(v['players']) for v in pstats.values())} righe")

    os.makedirs("data", exist_ok=True)
    with open(PATH, "w", encoding="utf-8") as f:
        json.dump({"updated": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                   "squads": squads, "predicted": predicted, "penalties": pens, "logos": logos,
                   "standings": standings, "player_stats": pstats},
                  f, ensure_ascii=False, separators=(",", ":"))
    injured = sum(1 for s in squads.values() for p in s if (p.get("availability") or "").lower() not in ("", "available", "none"))
    print(f"Giocatori non disponibili nelle rose: {injured}")
    print(f"Richieste BSD usate: {used}")


if __name__ == "__main__":
    main()
