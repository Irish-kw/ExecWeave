#!/bin/bash
export PATH="/workspace/execweave-venv/bin:/home/box/.local/bin:$PATH"
export DISPLAY=:3
export GEMINI_FORCE_FILE_STORAGE=true
export TZ=UTC
cd /workspace/agy-pr40
exec /workspace/execweave-venv/bin/execweave live --open --watch-root /workspace/agy-pr40 \
  --output-dir /workspace/ExecWeave/artifacts/grok_bot_real_machine/pr40_20260901T102302Z/raw/run2 \
  --linger 1800 -- /home/box/.local/bin/agy
