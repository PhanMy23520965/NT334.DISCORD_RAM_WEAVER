# Discord-Weaver: Discord Memory Forensics Analysis

## Kiến trúc

Discord-Weaver là một công cụ phân tích pháp y bộ nhớ Discord, tương tự RAM-Weaver cho LINE Messenger.

```
[Discord Process]                  [Analysis Host (Windows/WSL)]
Discord.exe
     │                                        │
     ▼                                        │
Memory Dump (discord.raw) ───────────────────► │
                                              │
                                   [Stage 1: AMC]
                                 Adaptive Memory Carver
                                              │
                                              ├─ Memory Extraction
                                              │    ├─ String extraction
                                              │    └─ JSON parsing
                                              │
                                              └─ Artifact Filtering
                                                   ├─ Noise removal
                                                   └─ Deduplication

                                   [Stage 2: LLM]
                                              ├─ Message Restoration
                                              └─ Forensic Query
```

## Features

- **Stage 1: Adaptive Memory Carver (AMC)**
  - Extract Discord messages from memory dumps
  - Extract user information and metadata
  - JSON parsing and validation
  - Noise filtering and deduplication

- **Stage 2: LLM Query & Restoration**
  - Restore corrupted/partial messages using Gemini
  - Forensic queries on Discord data
  - Timeline analysis
  - User behavior analysis
  - Sentiment analysis
  - Interactive query session

## Setup

### 1) Cài đặt Dependencies

```bash
pip install google-generativeai
```

### 2) Chuẩn bị `.env`

Copy từ template và điền thông tin:

```bash
cp .env.template .env
```

Các biến cần thiết:
- `PYTHON_BIN`: Python executable path
- `DISCORD_DUMP_PATH`: Path to discord.raw file
- `DISCORD_PID`: Discord process ID (ví dụ: 352)
- `DISCORD_MODE`: Mode mặc định (restore/query/interactive)
- `GEMINI_API_KEY`: Google Gemini API key
- `DISCORD_OUTPUT_DIR`: Output directory (default: ./output_discord)
- `DISCORD_EXTRACTION_MODE`: Extraction mode (auto/heap/private_memory)

### 3) Lấy Gemini API Key

1. Vào https://ai.google.dev/
2. Click "Get API Key"
3. Tạo một project mới hoặc sử dụng project hiện tại
4. Copy API key vào `.env`

## Usage

### Cách 1: Pipeline Script (Recommended)

```bash
# Restore messages
bash run_pipeline.sh D:\\discord.raw 352 restore

# Execute query
bash run_pipeline.sh D:\\discord.raw 352 query "Who sent the most messages?"

# Interactive session
bash run_pipeline.sh D:\\discord.raw 352 interactive
```

### Cách 2: Chạy từng stage riêng

**Stage 1 - AMC:**
```bash
python -c "
from amc.pipeline import AdaptiveMemoryCarver
from config import AMCConfig

config = AMCConfig()
carver = AdaptiveMemoryCarver(config)
output = carver.run('D:\\discord.raw', pid=352)
"
```

**Stage 2 - LLM:**
```bash
# Restore
python llm/llm_runner.py restore output_discord/discord_amc_output_pid352.json

# Query
python llm/llm_runner.py query output_discord/discord_amc_output_pid352.json "Your question here"

# Interactive
python llm/llm_runner.py interactive output_discord/discord_amc_output_pid352.json
```

## Project Structure

```
NT334.Discord_Weaver/
├── .env.template           # Environment template
├── config.py              # Main configuration
├── run_pipeline.sh        # Pipeline orchestrator
├── README.md              # This file
│
├── amc/                   # Stage 1 - Memory Carver
│   ├── __init__.py
│   ├── pipeline.py        # Main AMC orchestrator
│   ├── extractor.py       # Memory extraction
│   └── filtering.py       # Artifact filtering
│
├── llm/                   # Stage 2 - LLM Query
│   ├── __init__.py
│   ├── llm_runner.py      # CLI entry point
│   ├── client.py          # Gemini API client
│   ├── restorer.py        # Message restoration
│   └── query_engine.py    # Query engine
│
├── output_discord/        # Stage 1 output
├── output/               # Final output
└── vad_dumps/            # Temporary VAD dumps
```

## Workflow

### Stage 1: Memory Carving

1. **Extraction**: Carves Discord strings and JSON objects from memory
2. **Filtering**: Removes noise, deduplicates, categorizes
3. **Output**: Produces JSON files with messages, user data, metadata

### Stage 2: LLM Processing

1. **Load**: Reads extracted data from Stage 1
2. **Process**: Uses Gemini to restore/analyze/query
3. **Output**: Produces restored messages or query responses

## Query Examples

```bash
# Timeline analysis
./run_pipeline.sh D:\\discord.raw 352 query "Analyze the message timeline - when was there most activity?"

# User analysis
./run_pipeline.sh D:\\discord.raw 352 query "Who are the main participants? List their activity levels."

# Suspicious activity
./run_pipeline.sh D:\\discord.raw 352 query "Identify any suspicious patterns or unusual behavior."

# Content analysis
./run_pipeline.sh D:\\discord.raw 352 query "What were the main topics discussed?"
```

## Output Files

**Stage 1 Output** (`output_discord/`):
- `discord_amc_output_pid{PID}.txt` - Text format output
- `discord_amc_output_pid{PID}.json` - JSON format output

**Stage 2 Output**:
- `restored_messages.json` - Restored messages (restore mode)
- `query_response.txt` - Query responses (query mode)

## Troubleshooting

### API Key Issues
```
Error: GEMINI_API_KEY not set
```
Solution: Make sure you set `GEMINI_API_KEY` in `.env` file

### Memory Dump Not Found
```
[ERROR] Dump file not found: D:\discord.raw
```
Solution: Verify the dump path in `.env` or command line

### No Output Files
Check:
1. Dump file is readable
2. Output directory has write permissions
3. Python environment has required packages

## Development

### Add Custom Query

Edit `llm/query_engine.py` and add a new method:

```python
def custom_analysis(self, messages: List[dict]) -> Optional[str]:
    """Your custom analysis."""
    context = self._prepare_message_context(messages)
    question = "Your question..."
    return self.query(context, question)
```

### Add Custom Filter

Edit `amc/filtering.py` to customize artifact filtering logic.

## Notes

- Ensure Discord process is fully captured in the dump
- Larger dumps take longer to process
- Gemini API calls are counted towards quota
- Interactive mode maintains conversation context

## References

- [Gemini API Documentation](https://ai.google.dev/)
- RAM-Weaver (parent project)
- Discord message structure analysis

---

**Created**: 2026
**Based on**: RAM-Weaver Architecture
**Status**: Active Development
=======
# NT334.DISCORD_RAM_WEAVER
>>>>>>> 4ac65e2dcf3736ca7bdeabd3cd3863d926b64563
