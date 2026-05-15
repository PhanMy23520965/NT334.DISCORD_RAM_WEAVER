# Discord-Weaver Quick Start Guide

## Project Overview

Discord-Weaver là công cụ phân tích pháp y bộ nhớ Discord, trích xuất và phân tích tin nhắn từ memory dump của Discord.exe.

**2 giai đoạn xử lý:**
1. **Stage 1 (AMC)**: Trích xuất dữ liệu từ memory dump
2. **Stage 2 (LLM)**: Khôi phục & phân tích dữ liệu với Gemini AI

---

## Installation

### 1. Cài đặt Dependencies

```bash
# Vào thư mục project
cd d:\nt334\NT334.Discord_Weaver

# Cài đặt Python packages
pip install -r requirements.txt
```

### 2. Chuẩn bị Environment

File `.env` đã được cấu hình với:
- **Dump path**: `D:/nt334/discord.raw` (chỉnh sửa nếu khác)
- **Discord PIDs**: Tất cả 6 processes (352, 8152, 3500, 7356, 9008, 9960)
- **Main PID**: 9008 (process chính - 22MB)
- **LLM Provider**: Gemini (API key đã có)

**Kiểm tra .env:**
```bash
# Mở .env và xác nhận:
- RAM_WEAVER_DUMP_PATH=D:/nt334/discord.raw (dump file của bạn)
- RAM_WEAVER_PID=9008 (hoặc PID khác nếu cần)
- GEMINI_API_KEY=AIzaSy... (có API key)
```

---

## Quick Start: Thu Thập Dữ Liệu

### Option 1: Thu từ TẤT CẢ Discord PIDs (Đầy đủ)

```bash
# Phân tích tất cả 6 processes Discord
python collect_all_discord.py D:/nt334/discord.raw
```

**Kết quả:** 
- Tạo folder `output_discord/combined_[timestamp]/`
- Chứa dữ liệu từ tất cả PIDs
- Có thể so sánh & loại bỏ trùng lặp

### Option 2: Thu từ PID Cụ Thể

```bash
# PID 9008 - Process chính (đầy đủ nhất)
python main.py run D:/nt334/discord.raw 9008

# Hoặc PID khác
python main.py run D:/nt334/discord.raw 352
python main.py run D:/nt334/discord.raw 8152
```

**Kết quả:** Lưu trong `output_discord/` và `output/`

### Option 3: Sử dụng Config Mặc Định

```bash
# Dùng settings từ .env (PID=9008)
python main.py run D:/nt334/discord.raw
```

---

## Stage-by-Stage Processing

### Stage 1: Extract Memory (Adaptive Memory Carver)

```bash
python -c "
from amc.pipeline import AdaptiveMemoryCarver
from config import AMCConfig

config = AMCConfig()
carver = AdaptiveMemoryCarver(config)
result = carver.run('D:/nt334/discord.raw', pid=9008)
print(f'Output: {result}')
"
```

**Output:** `output_discord/discord_amc_output_pid9008.json`

### Stage 2: Restore & Analyze (LLM)

```bash
# Khôi phục tin nhắn bị hỏng
python llm/llm_runner.py restore output_discord/discord_amc_output_pid9008.json

# Hoặc truy vấn dữ liệu
python llm/llm_runner.py query output_discord/discord_amc_output_pid9008.json "Who sent the most messages?"
```

---

## Analysis Examples

### Query: Basic Analysis

```bash
# Người gửi nhiều nhất
python llm/llm_runner.py query <output_file> "Ai gửi nhiều tin nhắn nhất?"

# Timeline
python llm/llm_runner.py query <output_file> "Tạo timeline sự kiện quan trọng"

# Phát hiện bất thường
python llm/llm_runner.py query <output_file> "Tìm các mô hình giao tiếp bất thường"

# Sentiment analysis
python llm/llm_runner.py query <output_file> "Phân tích tâm trạng của các tin nhắn"
```

### Query: Forensic Analysis

```bash
# Tin nhắn xóa
python llm/llm_runner.py query <output_file> "Tìm bằng chứng của tin nhắn bị xóa"

# Hành vi người dùng
python llm/llm_runner.py query <output_file> "Mô tả hành vi của từng người dùng"

# Dữ liệu metadata
python llm/llm_runner.py query <output_file> "Liệt kê tất cả metadata có sẵn"
```

---

## Diagnostic Commands

### Check Installation

```bash
# Kiểm tra cấu hình & dependencies
python diagnose.py

# Test các components
python test_components.py
```

### Verify Dump File

```bash
# Kiểm tra file dump có hợp lệ
python -c "
import os
dump_path = 'D:/nt334/discord.raw'
if os.path.exists(dump_path):
    size_mb = os.path.getsize(dump_path) / (1024*1024)
    print(f'✓ Dump file: {dump_path}')
    print(f'✓ Size: {size_mb:.2f} MB')
else:
    print(f'✗ File not found: {dump_path}')
"
```

---

## Output Files

### Location: `output_discord/` và `output/`

| File | Purpose |
|------|---------|
| `discord_amc_output_pid*.json` | Extracted Discord data (Stage 1) |
| `combined_[timestamp]/` | All PIDs combined results |
| `restored_messages.json` | Restored messages (Stage 2) |
| `query_response.txt` | Query results |

### Data Structure

```json
{
  "messages": [
    {
      "author": "username",
      "content": "message text",
      "timestamp": "2026-05-15T10:30:00",
      "channel_id": "123456",
      "message_id": "987654"
    }
  ],
  "users": [...],
  "channels": [...],
  "metadata": {...}
}
```

---

## Troubleshooting

### ❌ "Dump file not found"
```bash
# Xác nhận đường dẫn trong .env
# Sửa: RAM_WEAVER_DUMP_PATH=D:/nt334/discord.raw
cat .env | grep DUMP_PATH
```

### ❌ "Gemini API error"
```bash
# Kiểm tra API key
cat .env | grep GEMINI_API_KEY

# Lấy API key mới từ https://ai.google.dev/
# Cập nhật .env
```

### ❌ "PID not found in dump"
```bash
# Sử dụng PID khác từ danh sách
# Tất cả PIDs: 352, 8152, 3500, 7356, 9008, 9960
python main.py run D:/nt334/discord.raw 352
```

### ❌ Import errors
```bash
# Cài lại dependencies
pip install --upgrade -r requirements.txt

# Kiểm tra virtual environment
python -c "import sys; print(sys.executable)"
```

---

## Best Practices

✅ **Đầy đủ dữ liệu** - Thu từ tất cả PIDs để không thiếu thông tin
✅ **Xác minh kết quả** - So sánh dữ liệu từ các PIDs khác nhau
✅ **Khôi phục trước** - Chạy restore để làm sạch dữ liệu trước query
✅ **Ghi log** - Lưu query results để auditing

---

## Next Steps

1. ✅ Thu thập dữ liệu từ tất cả PIDs
   ```bash
   python collect_all_discord.py D:/nt334/discord.raw
   ```

2. ✅ Khôi phục & làm sạch dữ liệu
   ```bash
   python llm/llm_runner.py restore output_discord/discord_amc_output_pid9008.json
   ```

3. ✅ Thực hiện phân tích/query
   ```bash
   python llm/llm_runner.py query <output_file> "Your question"
   ```

4. ✅ Review output trong `output_discord/`

---

## Reference

- **Config file**: `config.py`
- **AMC Engine**: `amc/pipeline.py`
- **LLM Runner**: `llm/llm_runner.py`
- **Full docs**: `README.md`

**Questions?** Check `diagnose.py` output or review individual module docstrings.
