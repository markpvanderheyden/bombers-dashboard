import requests
import json
from datetime import datetime, timezone

TEAM_ID = "d72d96f1-df57-4a92-8b40-1cdf06723881"
TEAM_NAME = "NLSAA3 - Bombers"
BASE = "https://api.team-manager.gc.com"
SPRAY_CACHE_VERSION = "v2"  # bump to force re-processing of all game streams

def fetch(url, headers):
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.json()

def fetch_silent(url, headers):
    try:
        r = requests.get(url, headers=headers)
        r.raise_for_status()
        return r.json()
    except Exception:
        return None

def flatten_events(events_raw):
    """Parse event_data JSON strings and flatten transaction containers."""
    flat = []
    for ew in (events_raw or []):
        try:
            ev = json.loads(ew.get("event_data", "{}"))
        except Exception:
            continue
        if ev.get("code") == "transaction":
            for ne in ev.get("events") or []:
                flat.append(ne)
        else:
            flat.append(ev)
    return flat

def extract_hits(flat_events, team_id):
    """Return list of {player_id, x, y, result, type} for the given team's batters."""
    # Build lineups and identify home/away teams
    lineups = {}
    away_team = home_team = None

    for ev in flat_events:
        code = ev.get("code", "")
        attrs = ev.get("attributes") or {}
        if code == "set_teams":
            away_team = attrs.get("awayId")
            home_team = attrs.get("homeId")
        if code == "fill_lineup_index":
            tid = attrs.get("teamId")
            idx = attrs.get("index")
            pid = attrs.get("playerId")
            if tid not in lineups:
                lineups[tid] = {}
            if idx is not None and pid:
                lineups[tid][idx] = pid

    if not lineups.get(team_id):
        return []

    def lineup_size(tid):
        lp = lineups.get(tid) or {}
        keys = [k for k in lp if k is not None]
        return max(keys) + 1 if keys else 9

    # Initialize game state — away team bats first
    batting_team = away_team or team_id
    bat_idx = {}
    for tid in (away_team, home_team):
        if tid:
            bat_idx[tid] = 0

    balls = strikes = outs = 0
    pending_bip = False
    hits = []

    for ev in flat_events:
        code = ev.get("code", "")
        attrs = ev.get("attributes") or {}

        if code == "goto_lineup_index":
            tid = attrs.get("teamId")
            if tid:
                batting_team = tid
                bat_idx[tid] = attrs.get("index", 0)
                balls = strikes = 0

        elif code == "pitch":
            result = attrs.get("result", "")
            if result == "ball":
                balls += 1
                if balls >= 4:  # Walk — advance lineup, no out
                    bat_idx[batting_team] = (bat_idx.get(batting_team, 0) + 1) % lineup_size(batting_team)
                    balls = strikes = 0
            elif result in ("strike_looking", "strike_swinging"):
                strikes += 1
                if strikes >= 3:  # Strikeout
                    outs += 1
                    bat_idx[batting_team] = (bat_idx.get(batting_team, 0) + 1) % lineup_size(batting_team)
                    balls = strikes = 0
                    if outs >= 3:
                        outs = 0
                        batting_team = home_team if batting_team == away_team else away_team
            elif result == "foul":
                if strikes < 2:
                    strikes += 1
            elif result == "ball_in_play":
                pending_bip = True

        elif code == "ball_in_play" and pending_bip:
            pending_bip = False
            play_result = attrs.get("playResult", "")
            is_batter_out = ("batter_out" in play_result.lower() or
                             "sacrifice" in play_result.lower())

            # Record hit location if our team is batting
            if batting_team == team_id:
                idx = bat_idx.get(team_id, 0)
                pid = (lineups.get(team_id) or {}).get(idx)
                defenders = attrs.get("defenders") or []
                if pid and defenders:
                    loc = defenders[0].get("location") or {}
                    x = loc.get("x")
                    y = loc.get("y")
                    if x is not None and y is not None:
                        hits.append({
                            "player_id": pid,
                            "x": round(float(x), 1),
                            "y": round(float(y), 1),
                            "result": play_result,
                            "type": attrs.get("playType", ""),
                        })

            # Advance the current batting team's lineup (this at-bat is over)
            prev_team = batting_team
            bat_idx[prev_team] = (bat_idx.get(prev_team, 0) + 1) % lineup_size(prev_team)

            if is_batter_out:
                outs += 1
                if outs >= 3:
                    outs = 0
                    batting_team = home_team if prev_team == away_team else away_team

            balls = strikes = 0

    return hits

def main():
    token = input("Enter your Gc-Token: ").strip()
    device_id = input("Enter your Gc-Device-Id (press Enter to skip): ").strip()

    headers = {
        "Gc-Token": token,
        "Gc-App-Name": "web",
        "Accept": "application/json",
    }
    if device_id:
        headers["Gc-Device-Id"] = device_id

    print("Fetching roster...", end=" ", flush=True)
    roster = fetch(f"{BASE}/teams/{TEAM_ID}/players", headers)
    print("✓")

    print("Fetching stats...", end=" ", flush=True)
    stats = fetch(f"{BASE}/teams/{TEAM_ID}/season-stats", headers)
    print("✓")

    print("Fetching schedule...", end=" ", flush=True)
    schedule = fetch(f"{BASE}/teams/{TEAM_ID}/schedule?fetch_place_details=true", headers)
    print("✓")

    # Load existing data to preserve cached values
    existing_scores = {}
    existing_hit_chart = {}
    try:
        with open("data.js", "r") as f:
            content = f.read().replace("const DASHBOARD_DATA = ", "").rstrip(";")
            existing = json.loads(content)
            for g in existing.get("game_results", []):
                existing_scores[g["event_id"]] = g
            cached = existing.get("hit_chart", {})
            # Only reuse cache if it matches current version
            if cached.get("_version") == SPRAY_CACHE_VERSION:
                existing_hit_chart = cached
    except Exception:
        pass

    # Fetch game scores
    print("Fetching game scores...", end=" ", flush=True)
    result = fetch_silent(f"{BASE}/teams/{TEAM_ID}/game-summaries", headers)
    if result and isinstance(result, list):
        for g in result:
            eid = g.get("event_id")
            if eid:
                existing_scores[eid] = g
        print("✓")
    else:
        print("(using cached scores)")

    game_results = list(existing_scores.values())

    # Build set of Bombers player IDs
    team_player_ids = {p["id"] for p in roster}

    # Fetch game stream events for spray chart
    hit_chart = dict(existing_hit_chart)
    hit_chart["_version"] = SPRAY_CACHE_VERSION
    fetched_streams = set(hit_chart.get("_fetched_streams", []))
    completed_games = [g for g in game_results if g.get("game_status") == "completed"]

    if completed_games:
        new_streams = [g for g in completed_games
                       if (g.get("game_stream") or {}).get("id")
                       and (g.get("game_stream") or {}).get("id") not in fetched_streams]

        if new_streams:
            print(f"\nFetching spray chart data ({len(new_streams)} game stream(s))...")
            for game in new_streams:
                stream_id = game["game_stream"]["id"]
                print(f"  Stream {stream_id[:8]}...", end=" ", flush=True)
                events_raw = fetch_silent(f"{BASE}/game-streams/{stream_id}/events", headers)
                if not events_raw or not isinstance(events_raw, list):
                    print("(no data)")
                    continue

                flat = flatten_events(events_raw)
                game_hits = extract_hits(flat, TEAM_ID)

                for h in game_hits:
                    pid = h.pop("player_id")
                    if pid not in hit_chart:
                        hit_chart[pid] = []
                    hit_chart[pid].append(h)

                fetched_streams.add(stream_id)
                print(f"✓ ({len(game_hits)} batted balls)")
        else:
            print("\nSpray chart data up to date.")

    hit_chart["_fetched_streams"] = list(fetched_streams)

    # Extract all opponents from schedule
    all_opponents = {}
    for item in schedule:
        ev = item.get("event", item)
        if ev.get("event_type") != "game":
            continue
        pre = item.get("pregame_data", {})
        opponent_id = pre.get("opponent_id")
        opponent_name = pre.get("opponent_name", "")
        if opponent_id and opponent_id not in all_opponents:
            all_opponents[opponent_id] = opponent_name

    # Fetch each opponent's stats and roster
    opponent_data = {}
    if all_opponents:
        print(f"\nFetching scouting data for {len(all_opponents)} opponents...")
        for opp_id, opp_name in all_opponents.items():
            short_name = opp_name.split(" - ")[-1] if " - " in opp_name else opp_name
            print(f"  {short_name}...", end=" ", flush=True)
            opp_stats = fetch_silent(f"{BASE}/teams/{opp_id}/season-stats", headers)
            opp_roster = fetch_silent(f"{BASE}/teams/{opp_id}/players", headers)
            opp_record = fetch_silent(f"{BASE}/teams/{opp_id}", headers)
            if opp_stats or opp_roster:
                opponent_data[opp_id] = {
                    "name": opp_name,
                    "stats": opp_stats,
                    "roster": opp_roster or [],
                    "record": opp_record,
                }
                print("✓")
            else:
                print("(no access)")

    data = {
        "team_name": TEAM_NAME,
        "team_id": TEAM_ID,
        "fetched_at": datetime.now().isoformat(),
        "stats": stats,
        "roster": roster,
        "events": schedule,
        "game_results": game_results,
        "opponent_data": opponent_data,
        "hit_chart": hit_chart,
    }

    with open("data.js", "w") as f:
        f.write("const DASHBOARD_DATA = ")
        json.dump(data, f, indent=2)
        f.write(";")

    print("\n✓ data.js updated — open index.html in your browser.")

if __name__ == "__main__":
    main()
