#!/usr/bin/env bash
# =============================================================================
# run_pipeline.sh - Discord-Weaver pipeline runner
# =============================================================================

set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# --- Load .env (REQUIRED) ---
if [[ -f "$ROOT_DIR/.env" ]]; then
  echo "[INFO] Loading configuration from .env..."
  set -a
  source <(sed 's/\r$//' "$ROOT_DIR/.env")
  set +a
else
  echo "[ERROR] .env file not found. Please create it first."
  exit 1
fi

export PYTHONIOENCODING=utf-8

# --- Configuration from .env (Strict) ---
PYTHON_BIN="${RAM_WEAVER_PYTHON:-${PYTHON_BIN:-python}}"
DUMP_PATH="${RAM_WEAVER_DUMP_PATH:-}"
PID="${RAM_WEAVER_PID:-all}"
MODE="${RAM_WEAVER_MODE:-restore}"

# Logic to handle arguments:
# 1. No args: Use both from .env
# 2. First arg is a PID or 'all': Use it as PID, use .env for DUMP_PATH
# 3. First arg is a file: Use it as DUMP_PATH, next arg as PID
if [[ "${1:-}" == "all" ]] || [[ "${1:-}" =~ ^[0-9]+$ ]]; then
  PID="$1"
  DUMP_PATH="$DUMP_PATH"
  PID="${1:-$PID}"
  MODE="${2:-$MODE}"
else
  DUMP_PATH="${1:-$DUMP_PATH}"
  PID="${2:-$PID}"
  MODE="${3:-$MODE}"
fi

if [[ -z "$DUMP_PATH" ]]; then
  echo "[ERROR] RAM_WEAVER_DUMP_PATH not set in .env"
  exit 1
fi

# Parse ALL_PIDS from .env
if [[ -n "${RAM_WEAVER_PIDs:-}" ]]; then
  IFS=',' read -r -a ALL_PIDS <<< "$RAM_WEAVER_PIDs"
else
  echo "[ERROR] RAM_WEAVER_PIDs not set in .env"
  exit 1
fi

AMC_OUTPUT_DIR="${RAM_WEAVER_OUTPUT_DIR:-$ROOT_DIR/output_discord}"
CHUNKS_FILE="$AMC_OUTPUT_DIR/discord_amc_output_pid${PID}.json"

# --- Function to convert paths to Windows format ---
to_win_path() {
  local p="$1"
  if command -v wslpath >/dev/null 2>&1; then
    wslpath -w "$p"
  elif [[ "$p" == /* ]]; then
    echo "$p" | sed -e 's/^\/\([a-zA-Z]\)\//\1:\\/' -e 's/\//\\/g'
  else
    echo "$p"
  fi
}

WIN_DUMP_PATH=$(to_win_path "$DUMP_PATH")
WIN_ROOT_DIR=$(to_win_path "$ROOT_DIR")
WIN_CHUNKS_FILE=$(to_win_path "$CHUNKS_FILE")
WIN_OUTPUT_DIR=$(to_win_path "$AMC_OUTPUT_DIR")

# --- Validate dump file exists ---
if [[ ! -f "$DUMP_PATH" ]]; then
  # Try to find the file in Linux/WSL context
  if [[ "$DUMP_PATH" == *":"* ]]; then
     DRIVE=$(echo "$DUMP_PATH" | cut -d':' -f1 | tr '[:upper:]' '[:lower:]')
     REMAINDER=$(echo "$DUMP_PATH" | cut -d':' -f2- | sed 's/\\/\//g')
     DUMP_PATH_ALT="/mnt/${DRIVE}${REMAINDER}"
     if [[ ! -f "$DUMP_PATH_ALT" ]]; then DUMP_PATH_ALT="/${DRIVE}${REMAINDER}"; fi
     if [[ -f "$DUMP_PATH_ALT" ]]; then 
       DUMP_PATH="$DUMP_PATH_ALT"
       WIN_DUMP_PATH=$(to_win_path "$DUMP_PATH")
     fi
  fi
fi

if [[ ! -f "$DUMP_PATH" ]]; then
  echo "[ERROR] Dump file not found: $DUMP_PATH"
  exit 1
fi

# --- Stage 1: Adaptive Memory Carver ---
echo "----------------------------------------------------------------------"
echo "Discord-Weaver: Stage 1 - Adaptive Memory Carver (AMC)"
echo "----------------------------------------------------------------------"

# Cleanup old results
echo "[INFO] Cleaning up old results..."
mkdir -p "$AMC_OUTPUT_DIR"
mkdir -p "$ROOT_DIR/vad_dumps"
rm -f "$AMC_OUTPUT_DIR"/*.json "$AMC_OUTPUT_DIR"/*.txt
rm -rf "$ROOT_DIR/vad_dumps"/*

# Pass variables via sys.argv
$PYTHON_BIN -c '
import sys, os, logging, json, glob
logging.basicConfig(level=logging.INFO, format="%(levelname)s:%(name)s:%(message)s")

root_dir = sys.argv[1]
dump_path = sys.argv[2]
output_dir_path = sys.argv[3]
chunks_file = sys.argv[4]
pid_arg = sys.argv[5]
all_pids_str = sys.argv[6]

sys.path.insert(0, root_dir)
from amc.pipeline import AdaptiveMemoryCarver
from config import AMCConfig

config = AMCConfig()
carver = AdaptiveMemoryCarver(config)

pids = [int(x) for x in all_pids_str.split()] if pid_arg == "all" else [int(pid_arg)]

for p in pids:
    print(f"\n--- Processing PID {p} ---")
    output = carver.run(dump_path, pid=p)

if pid_arg == "all":
    print("\nMerging results for all PIDs...")
    merged = {"messages": [], "user_data": [], "metadata": [], "statistics": {}}
    files_found = 0
    for f_path in glob.glob(os.path.join(output_dir_path, "discord_amc_output_pid[0-9]*.json")):
        try:
            with open(f_path, "r", encoding="utf-8") as f:
                data = json.load(f)
                merged["messages"].extend(data.get("messages", []))
                merged["user_data"].extend(data.get("user_data", []))
                merged["metadata"].extend(data.get("metadata", []))
                for k, v in data.get("statistics", {}).items():
                    if isinstance(v, (int, float)):
                        merged["statistics"][k] = merged["statistics"].get(k, 0) + v
            files_found += 1
        except Exception: pass
    
    with open(chunks_file, "w", encoding="utf-8") as f:
        json.dump(merged, f, ensure_ascii=False, indent=2)
    print(f"✓ Merged {files_found} files")
' "$WIN_ROOT_DIR" "$WIN_DUMP_PATH" "$WIN_OUTPUT_DIR" "$WIN_CHUNKS_FILE" "$PID" "${ALL_PIDS[*]}"

# --- Stage 2: LLM Query & Restoration ---
echo "----------------------------------------------------------------------"
echo "Discord-Weaver: Stage 2 - LLM Query & Restoration"
echo "----------------------------------------------------------------------"

case "$MODE" in
  restore)
    $PYTHON_BIN "$WIN_ROOT_DIR/llm/llm_runner.py" restore "$WIN_CHUNKS_FILE"
    ;;
  query)
    QUERY_TEXT="${4:-What is in this memory dump?}"
    $PYTHON_BIN "$WIN_ROOT_DIR/llm/llm_runner.py" query "$WIN_CHUNKS_FILE" "$QUERY_TEXT"
    ;;
  interactive)
    $PYTHON_BIN "$WIN_ROOT_DIR/llm/llm_runner.py" interactive "$WIN_CHUNKS_FILE"
    ;;
esac

echo "[DONE] Discord-Weaver Pipeline Complete"
