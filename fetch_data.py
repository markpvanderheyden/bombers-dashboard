import requests
import json
from datetime import datetime, timezone

TEAM_ID = "d72d96f1-df57-4a92-8b40-1cdf06723881"
TEAM_NAME = "NLSAA3 - Bombers"
BASE = "https://api.team-manager.gc.com"

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

    # Try to fetch completed game scores
    game_results = []
    for candidate in ["/games", "/game-streams", "/game-results"]:
        result = fetch_silent(f"{BASE}/teams/{TEAM_ID}{candidate}", headers)
        if result:
            game_results = result
            print(f"✓ Game scores fetched")
            break

    # Extract upcoming opponents from schedule
    now = datetime.now(timezone.utc)
    upcoming_opponents = {}
    for item in schedule:
        ev = item.get("event", item)
        if ev.get("event_type") != "game":
            continue
        pre = item.get("pregame_data", {})
        opponent_id = pre.get("opponent_id")
        opponent_name = pre.get("opponent_name", "")
        start = ev.get("start", {}).get("datetime", "")
        if not opponent_id or not start:
            continue
        try:
            game_time = datetime.fromisoformat(start.replace("Z", "+00:00"))
        except Exception:
            continue
        if game_time > now and opponent_id not in upcoming_opponents:
            upcoming_opponents[opponent_id] = opponent_name

    # Fetch each upcoming opponent's stats and roster
    opponent_data = {}
    if upcoming_opponents:
        print(f"\nFetching scouting data for {len(upcoming_opponents)} upcoming opponents...")
        for opp_id, opp_name in upcoming_opponents.items():
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
    }

    with open("data.js", "w") as f:
        f.write("const DASHBOARD_DATA = ")
        json.dump(data, f, indent=2)
        f.write(";")

    print("\n✓ data.js updated — open index.html in your browser.")

if __name__ == "__main__":
    main()
