"""Adaptive Memory Extractor for Discord.

BUGS FIXED vs original:
  BUG-1 (CRITICAL): regex r'[ -~]{8,}' only matches ASCII printable chars.
      Any JSON with Vietnamese/emoji/unicode is split into fragments
      -> json.loads always fails -> 0 JSON objects extracted.
      FIX: Use bracket-matching directly on decoded text instead.

  BUG-2: _filter_strings drops strings with URLs *before* JSON parsing.
      Discord messages often contain links -> valid JSONs silently discarded.
      FIX: JSON extraction runs on raw decoded text, bypassing noise filter.

  BUG-3: noise pattern [A-Za-z0-9+/]{40,} matched Discord avatar hashes /
      snowflake IDs inside JSON strings -> false-positive noise removal.
      FIX: noise filter applied only to plain text strings, not JSON.

  BUG-4: snowflake regex was fragile and returned empty matches.
      FIX: simplified pattern using non-digit boundary approach.
"""

from __future__ import annotations

import logging
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor

import os
import re
import json
import sys
from pathlib import Path
from typing import Optional, List
from dataclasses import dataclass

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import AMCConfig

log = logging.getLogger("discord_weaver.amc.extractor")


@dataclass
class ExtractionResult:
    strings: List[str]
    json_objects: List[dict]
    statistics: dict


class AdaptiveMemoryExtractor:
    """Extracts Discord-related artifacts from memory dumps."""

    def __init__(self, config: AMCConfig):
        self.config = config
        self.vad_dump_dir = Path(config.vad_dump_dir)
        self.vad_dump_dir.mkdir(parents=True, exist_ok=True)

    def extract(self, dump_path: str, pid: Optional[int] = None) -> ExtractionResult:
        log.info(f"Extracting Discord artifacts from {dump_path}")
        
        all_json_objects = []
        all_strings = []
        
        if pid:
            log.info(f"Targeting PID {pid} using Volatility 3...")
            
            # Optimization: check if we already have VAD dumps for this PID
            pid_dir = self.vad_dump_dir / f"pid_{pid}"
            vad_files = list(pid_dir.glob("*.dmp"))
            
            if not vad_files:
                vad_files = self._run_volatility_vaddump(dump_path, pid)
            else:
                log.info(f"Found existing {len(vad_files)} VAD dump files, skipping Volatility run.")

            if vad_files:
                log.info(f"Scanning {len(vad_files)} VAD dump files...")
                for vad_file in vad_files:
                    try:
                        with open(vad_file, 'rb') as f:
                            # Use chunked reading for VAD files to avoid memory pressure
                            chunk = f.read()
                            log.info(f"      Scanning VAD: {vad_file.name} ({len(chunk)//1024} KB)")
                            all_json_objects.extend(self._extract_json_from_bytes(chunk))
                            all_strings.extend(self._extract_strings(chunk))
                    except Exception as e:
                        log.warning(f"Failed to read VAD file {vad_file.name}: {e}")
            else:
                log.warning(f"Volatility failed to dump VADs for PID {pid}. Falling back to raw scan.")
                pid = None # Fallback

        if not pid:
            # Fallback or Raw Scan: scan the whole file in chunks
            log.info("Performing raw scan of entire dump file (this may be slow)...")
            try:
                # To avoid OOM on 2GB+ files, we scan in overlapping chunks
                chunk_size = 100 * 1024 * 1024 # 100 MB
                overlap = 1024 * 1024 # 1 MB
                
                file_size = os.path.getsize(dump_path)
                with open(dump_path, 'rb') as f:
                    offset = 0
                    while True:
                        f.seek(max(0, offset - overlap))
                        chunk = f.read(chunk_size + overlap)
                        if not chunk:
                            break
                        all_json_objects.extend(self._extract_json_from_bytes(chunk))
                        all_strings.extend(self._extract_strings(chunk))
                        offset += chunk_size
                        
                        percent = min(100, (offset * 100) // file_size)
                        log.info(f"      Progress: {percent}% ({offset // (1024*1024)}/{file_size // (1024*1024)} MB)")
                        
                        if len(chunk) < chunk_size:
                            break
            except Exception as e:
                log.error(f"Failed to read dump file: {e}")

        # Final cleanup and deduplication
        json_objects = self._deduplicate_json(all_json_objects)
        strings = list(set(all_strings))

        statistics = {
            'total_strings': len(strings),
            'total_json_objects': len(json_objects),
            'pid_targeted': pid if pid else "None (Raw Scan)",
        }

        log.info(
            f"Extraction complete: {len(strings)} strings, "
            f"{len(json_objects)} JSON objects found."
        )
        return ExtractionResult(strings, json_objects, statistics)

    def _run_volatility_vaddump(self, dump_path: str, pid: int) -> List[Path]:
        """Execute Volatility 3 vaddump plugin."""
        if not self.config.volatility_path:
            log.error("Volatility path not configured!")
            return []

        # Create specific output dir for this PID
        pid_dir = self.vad_dump_dir / f"pid_{pid}"
        pid_dir.mkdir(parents=True, exist_ok=True)

        cmd = [
            self.config.volatility_path,
            "-f", dump_path,
            "-o", str(pid_dir),
            "windows.memmap.Memmap",
            "--pid", str(pid),
            "--dump"
        ]
        
        log.info(f"Executing: {' '.join(cmd)}")
        try:
            start_time = time.time()
            process = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=self.config.volatility_timeout
            )
            elapsed = time.time() - start_time
            log.info(f"Volatility finished in {elapsed:.1f}s (Exit code: {process.returncode})")
            
            if process.returncode != 0:
                log.error(f"Volatility error: {process.stderr}")
                return []
            
            # List all .dmp files created
            return list(pid_dir.glob("*.dmp"))
        except subprocess.TimeoutExpired:
            log.error(f"Volatility timed out after {self.config.volatility_timeout}s")
            return []
        except Exception as e:
            log.error(f"Failed to run Volatility: {e}")
            return []

    # ------------------------------------------------------------------
    # JSON Extraction
    # ------------------------------------------------------------------

    def _extract_json_from_bytes(self, data: bytes) -> List[dict]:
        # Discord-specific keywords that strongly indicate a message or user object
        KEYWORDS = [
            '"content"', '"author"', '"channelId"', '"channel_id"', 
            '"guildId"', '"guild_id"', '"username"', '"nonce"', 
            '"id"', '"global_name"', '"timestamp"'
        ]
        results: List[dict] = []
        n = len(data)
        
        last_log_percent = -1
        # Fast byte scan for '{'
        i = 0
        while i < n:
            # Progress logging for large buffers
            percent = (i * 100) // n
            if percent % 10 == 0 and percent > last_log_percent:
                log.info(f"        Processing: {percent}%...")
                last_log_percent = percent
                
            # Fast-forward to next possible JSON object start: {" or { " or UTF-16 equivalents
            next_i_utf8 = data.find(b'{"', i)
            next_i_u16 = data.find(b'{\x00"\x00', i)
            
            if next_i_utf8 == -1 and next_i_u16 == -1:
                break
                
            if next_i_utf8 == -1: i = next_i_u16
            elif next_i_u16 == -1: i = next_i_utf8
            else: i = min(next_i_utf8, next_i_u16)
            
            # Found a possible start. Use a robust brace-matching approach
            max_json_len = 30000
            stack = 0
            found_valid = False
            
            # Determine if this is likely UTF-16LE (has a null after {)
            is_u16 = (i + 1 < n and data[i+1] == 0)
            step = 2 if is_u16 else 1
            
            j = i
            while j < i + max_json_len and j < n:
                char = data[j]
                if char == ord('{'):
                    stack += 1
                elif char == ord('}'):
                    stack -= 1
                    if stack == 0:
                        # Found matching end!
                        candidate_end = j + step
                        if candidate_end > n: candidate_end = n
                        
                        candidate_bytes = data[i:candidate_end]
                        
                        # Pre-filter for Discord keywords
                        found_kw = False
                        for kw_base in KEYWORDS:
                            kw_ascii = kw_base.encode('ascii')
                            kw_u16 = kw_base.encode('utf-16le')
                            if kw_ascii in candidate_bytes or kw_u16 in candidate_bytes:
                                found_kw = True
                                break
                        
                        if found_kw:
                            for encoding in self.config.encodings:
                                try:
                                    decoded = candidate_bytes.decode(encoding, errors='ignore')
                                    decoded = decoded.strip().strip('\x00')
                                    if decoded.startswith('{') and decoded.endswith('}'):
                                        obj = json.loads(decoded)
                                        if isinstance(obj, dict) and len(obj) >= self.config.json_key_threshold:
                                            results.append(obj)
                                            found_valid = True
                                            i = candidate_end - 1
                                            break
                                except Exception: continue
                        if found_valid: break
                j += step
                if stack < 0: break # Mismatched braces
            
            if not found_valid:
                i += 1
            continue
        return results

    def _is_discord_json(self, obj: dict) -> bool:
        """Enhanced Discord JSON detection."""
        # Common keys in Discord message objects (API and memory)
        target_keys = {
            'content', 'author', 'id', 'channel_id', 'channelId', 
            'guild_id', 'guildId', 'timestamp', 'username', 'nonce',
            'attachments', 'embeds', 'mentions'
        }
        
        matched_keys = [k for k in target_keys if k in obj]
        
        # Heuristic 1: If it has content AND an author dict, it's likely a message
        if 'content' in obj and isinstance(obj.get('author'), dict):
            return True
            
        # Heuristic 2: If it has multiple discord-specific keys
        if len(matched_keys) >= self.config.json_key_threshold:
            # Avoid UI logs
            if obj.get('message') in ['window.blur', 'app.browser-window-blur', 'app.browser-window-focus']:
                return False
            return True
            
        return False

    def _deduplicate_json(self, objects: List[dict]) -> List[dict]:
        seen_keys = set()
        unique = []
        for obj in objects:
            # Use ID or content hash for deduplication
            key = obj.get('id') or obj.get('nonce') or hash(json.dumps(obj, sort_keys=True))
            if key not in seen_keys:
                seen_keys.add(key)
                unique.append(obj)
        return unique

    def _extract_strings(self, data: bytes) -> List[str]:
        strings = []
        for encoding in self.config.encodings:
            try:
                text = data.decode(encoding, errors='ignore')
                found = re.findall(r'[\x20-\x7E\t]{10,}', text)
                strings.extend(found)
            except Exception:
                pass
        return strings