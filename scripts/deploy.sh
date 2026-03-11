#!/usr/bin/env bash
set -euo pipefail

# Deploy PulseUP Telegram bot to VPS and push to GitHub
# Usage: ./scripts/deploy.sh [commit message]

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
VPS_HOST="vps"  # SSH config alias
VPS_DIR="/root/pulseup-telegram"
COMMIT_MSG="${1:-Auto-deploy from Mac}"

echo "=== PulseUP Telegram Deploy ==="

# 1. Sync code to VPS
echo "[1/4] Syncing code to VPS..."
rsync -avz --delete \
  --exclude='.venv' \
  --exclude='.git' \
  --exclude='__pycache__' \
  --exclude='.pytest_cache' \
  --exclude='*.egg-info' \
  --exclude='data/*.db' \
  --exclude='data/*.db-journal' \
  --exclude='.claude' \
  --exclude='.DS_Store' \
  --exclude='.env' \
  -e "ssh" \
  "$PROJECT_DIR/" "$VPS_HOST:$VPS_DIR/"

# 2. Commit and push to GitHub from VPS
echo "[2/4] Committing and pushing to GitHub..."
ssh "$VPS_HOST" "cd $VPS_DIR && git add -A && git diff --cached --quiet || git commit -m '$COMMIT_MSG' && git push origin main"

# 3. Rebuild and restart Docker
echo "[3/4] Rebuilding Docker containers..."
ssh "$VPS_HOST" "cd $VPS_DIR && docker compose up -d --build"

echo "[4/4] Done! Deployment complete."
echo "=== Deploy finished ==="
