#!/bin/bash
cd ~/bombers-dashboard

echo "Fetching latest stats from GameChanger..."
python3 fetch_data.py

echo ""
echo "Pushing to GitHub..."
git add data.js
git commit -m "Update stats $(date '+%b %d %Y')"
git push

echo ""
echo "✅ Done! Site will be live at https://bombers2026dashboard.netlify.app in ~30 seconds."
read -p "Press Enter to close..."
