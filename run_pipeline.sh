#!/usr/bin/env bash
# =============================================================================
# run_pipeline.sh – Discord-Weaver pipeline runner
# =============================================================================
# Orchestrates both stages of Discord forensic analysis:
#   Stage 1: Adaptive Memory Carver (AMC)
#   Stage 2: LLM Query & Restoration
# =============================================================================

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# ── Load .env ────────────────────────────────────────────────────────────────
if [[ -f "$ROOT_DIR/.env" ]]; then
  set -a
  source "$ROOT_DIR/.env"
  set +a
else
  echo "[WARNING] .env file not found. Creating from template..."
  cp "$ROOT_DIR/.env.template" "$ROOT_DIR/.env"
  echo "[INFO] Edit $ROOT_DIR/.env with your settings"
fi

export PYTHONIOENCODING=utf-8

# ── Runtime config ───────────────────────────────────────────────────────────
PYTHON_BIN="${PYTHON_BIN:-python}"
DUMP_PATH="${1:-${RAM_WEAVER_DUMP_PATH:-}}"
PID="${2:-${RAM_WEAVER_PID:-all}}"
MODE="${3:-${RAM_WEAVER_MODE:-restore}}"
QUERY_TEXT=""

# Danh sách tất cả Discord PIDs
ALL_PIDS=(352 8152 3500 7356 9008 9960)

AMC_OUTPUT_DIR="${RAM_WEAVER_OUTPUT_DIR:-$ROOT_DIR/output_discord}"
CHUNKS_FILE="$AMC_OUTPUT_DIR/discord_amc_output_pid${PID}.json"

# ── Usage ─────────────────────────────────────────────────────────────────────
usage() {
  cat <<USAGE
Discord-Weaver Pipeline

Usage:
  ./run_pipeline.sh [dump_path] [pid|all] [restore|query|interactive] ["query text"]

Examples:
  # Restore all Discord PIDs (352, 8152, 3500, 7356, 9008, 9960)
  ./run_pipeline.sh D:\\discord.raw all restore

  # Restore specific PID
  ./run_pipeline.sh D:\\discord.raw 9008 restore

  # Query all PIDs
  ./run_pipeline.sh D:\\discord.raw all query "Who sent the most messages?"

  # Interactive mode
  ./run_pipeline.sh D:\\discord.raw 9008 interactive

Environment:
  RAM_WEAVER_DUMP_PATH  - Default dump file path
  RAM_WEAVER_PID        - Default Discord PID (default: all)
  RAM_WEAVER_MODE       - Default mode (restore/query/interactive)
  GEMINI_API_KEY        - Google Gemini API key
USAGE
}

# ── Validate inputs ─────────────────────────────────────────────────────────
if [[ -z "$DUMP_PATH" ]]; then
  echo "[ERROR] Missing dump_path" >&2
  usage
  exit 1
fi

if [[ ! -f "$DUMP_PATH" ]]; then
  echo "[ERROR] Dump file not found: $DUMP_PATH" >&2
  exit 1
fi

# ── Stage 1: Adaptive Memory Carver ──────────────────────────────────────────
echo ""
echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║ Discord-Weaver: Stage 1 - Adaptive Memory Carver (AMC)                 ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo ""

$PYTHON_BIN -c """
import sys, os
sys.path.insert(0, '$ROOT_DIR')
from amc.pipeline import AdaptiveMemoryCarver
from config import AMCConfig

config = AMCConfig()
carver = AdaptiveMemoryCarver(config)
output = carver.run('$DUMP_PATH', pid=$PID)
print(f'✓ Stage 1 complete: {output}')
"""

# ── Validate Stage 1 output ──────────────────────────────────────────────────
if [[ ! -f "$CHUNKS_FILE" ]]; then
  echo "[ERROR] Stage 1 output file not found: $CHUNKS_FILE" >&2
  exit 1
fi

# ── Stage 2: LLM Query & Restoration ─────────────────────────────────────────
echo ""
echo "╔════════════════════════════════════════════════════════════════════════╗"
echo "║ Discord-Weaver: Stage 2 - LLM Query & Restoration                      ║"
echo "╚════════════════════════════════════════════════════════════════════════╝"
echo ""

case "$MODE" in
  restore|interactive) ;;
  query)
    if [[ $# -ge 4 ]]; then
      QUERY_TEXT=\"${*:4}\"
    elif [[ -n \"${DISCORD_QUERY:-}\" ]]; then
      QUERY_TEXT=\"$DISCORD_QUERY\"
    else
      echo \"[ERROR] Query mode requires query text\" >&2
      exit 1
    fi
    ;;
  *)
    echo \"[ERROR] Unknown mode: $MODE\" >&2
    echo \"Supported: restore, query, interactive\" >&2
    exit 1
    ;;
esac

case "$MODE" in
  restore)
    $PYTHON_BIN \"$ROOT_DIR/llm/llm_runner.py\" restore \"$CHUNKS_FILE\"
    ;;
  query)
    $PYTHON_BIN \"$ROOT_DIR/llm/llm_runner.py\" query \"$CHUNKS_FILE\" \"$QUERY_TEXT\"
    ;;
  interactive)
    $PYTHON_BIN \"$ROOT_DIR/llm/llm_runner.py\" interactive \"$CHUNKS_FILE\"
    ;;
esac

echo \"\"
echo \"╔════════════════════════════════════════════════════════════════════════╗\"
echo \"║ ✓ Discord-Weaver Pipeline Complete                                     ║\"
echo \"╚════════════════════════════════════════════════════════════════════════╝\"
echo \"\"
