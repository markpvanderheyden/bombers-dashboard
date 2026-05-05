import requests
import json
from datetime import datetime

TEAM_ID = "d72d96f1-df57-4a92-8b40-1cdf06723881"
TEAM_NAME = "NLSAA3 - Bombers"
BASE = "https://api.team-manager.gc.com"

def fetch(url, headers):
    r = requests.get(url, headers=headers)
    r.raise_for_status()
    return r.json()

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
        try:
            game_results = fetch(f"{BASE}/teams/{TEAM_ID}{candidate}", headers)
            print(f"✓ Game scores fetched from {candidate}")
            break
        except Exception:
            continue

    data = {
        "team_name": TEAM_NAME,
        "team_id": TEAM_ID,
        "fetched_at": datetime.now().isoformat(),
        "stats": stats,
        "roster": roster,
        "events": schedule,
        "game_results": game_results,
    }

    with open("data.js", "w") as f:
        f.write("const DASHBOARD_DATA = ")
        json.dump(data, f, indent=2)
        f.write(";")

    print("\n✓ data.js updated — open index.html in your browser.")

if __name__ == "__main__":
    main()
