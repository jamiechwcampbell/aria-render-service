#!/bin/bash
# Bootstrap a public python:3.12-slim worker: install ffmpeg + deps, then run the queue handler.
# Used because this box has no Docker and no GHCR write:packages scope to bake/push an image.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
export HF_HOME="${HF_HOME:-/data/cache}"
export TTS_THREADS="${TTS_THREADS:-4}"
mkdir -p "$HF_HOME" /data

log() { echo "[render-start $(date -u +%H:%M:%S)] $*"; }

if ! command -v ffmpeg >/dev/null 2>&1; then
  log "Installing ffmpeg and build deps"
  apt-get update -qq
  apt-get install -y --no-install-recommends ffmpeg libsndfile1 libgomp1 ca-certificates curl git
  rm -rf /var/lib/apt/lists/*
fi

APP_DIR="${APP_DIR:-/data/render-service}"
BUNDLE_URL="${RENDER_BUNDLE_URL:-}"
if [ ! -f "$APP_DIR/handler.py" ]; then
  if [ -n "$BUNDLE_URL" ]; then
    log "Fetching render bundle"
    curl -fsSL "$BUNDLE_URL" -o /tmp/render-service.tgz
    mkdir -p /tmp/render-src
    tar -xzf /tmp/render-service.tgz -C /tmp/render-src
    # archive may be top-level folder or flat
    if [ -f /tmp/render-src/handler.py ]; then
      mkdir -p "$APP_DIR"
      cp -a /tmp/render-src/. "$APP_DIR/"
    else
      src=$(find /tmp/render-src -maxdepth 2 -type f -name handler.py -printf '%h\n' | head -1)
      mkdir -p "$APP_DIR"
      cp -a "$src"/. "$APP_DIR/"
    fi
  else
    log "ERROR: handler.py missing and RENDER_BUNDLE_URL is not set"
    exit 1
  fi
fi
cd "$APP_DIR"

if ! python -c "import torch, kokoro, runpod" >/dev/null 2>&1; then
  log "Installing Python dependencies (CPU torch)"
  pip install --no-cache-dir --upgrade pip
  pip install --no-cache-dir torch --index-url https://download.pytorch.org/whl/cpu
  pip install --no-cache-dir -r requirements.txt
fi

log "Preloading Kokoro voices"
python -c "from app.tts import VOICES; print('voices', list(VOICES))"
log "Starting RunPod serverless handler"
exec python -u handler.py
