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
    raw_data: bytes
    statistics: dict


class AdaptiveMemoryExtractor:
    """Extracts Discord-related artifacts from memory dumps."""

    def __init__(self, config: AMCConfig):
        self.config = config
        self.vad_dump_dir = Path(config.vad_dump_dir)
        self.vad_dump_dir.mkdir(parents=True, exist_ok=True)

    def extract(self, dump_path: str, pid: Optional[int] = None) -> ExtractionResult:
        log.info(f"Extracting Discord artifacts from {dump_path}")

        try:
            with open(dump_path, 'rb') as f:
                raw_data = f.read()
        except Exception as e:
            log.error(f"Failed to read dump file: {e}")
            return ExtractionResult([], [], b'', {'error': str(e)})

        # FIX BUG-1/2: extract JSON directly from raw bytes (unicode-aware)
        json_objects = self._extract_json_from_bytes(raw_data)

        # Extract plain strings for supplementary use only
        strings = self._extract_strings(raw_data)

        statistics = {
            'total_strings': len(strings),
            'total_json_objects': len(json_objects),
            'dump_size_bytes': len(raw_data),
        }

        log.info(
            f"Extraction: {len(strings)} strings, "
            f"{len(json_objects)} JSON objects, "
            f"dump = {len(raw_data):,} bytes"
        )
        return ExtractionResult(strings, json_objects, raw_data, statistics)

    # ------------------------------------------------------------------
    # FIX: bracket-matching JSON extractor (unicode-aware)
    # ------------------------------------------------------------------

    def _extract_json_from_bytes(self, data: bytes) -> List[dict]:
        """Extract JSON objects directly from raw binary data.

        Uses bracket-matching on decoded text so unicode chars inside
        message content (Vietnamese, emoji, CJK...) do NOT break parsing.
        """
        results: List[dict] = []
        seen_ids: set = set()

        for encoding in self.config.encodings:
            try:
                text = data.decode(encoding, errors='ignore')
            except Exception:
                continue

            for obj in self._bracket_match_json(text):
                if not isinstance(obj, dict):
                    continue
                if not self._is_discord_json(obj):
                    continue
                # Deduplicate
                obj_key = obj.get('id') or obj.get('nonce') or json.dumps(obj, sort_keys=True)[:80]
                if obj_key not in seen_ids:
                    seen_ids.add(obj_key)
                    results.append(obj)

        log.debug(f"bracket-match: {len(results)} unique Discord JSON objects")
        return results

    def _bracket_match_json(self, text: str) -> List[dict]:
        """Walk text and yield all balanced {…} blocks that parse as JSON."""
        objects = []
        depth = 0
        start = -1
        i = 0
        n = len(text)

        while i < n:
            ch = text[i]
            if ch == '{':
                if depth == 0:
                    start = i
                depth += 1
            elif ch == '}':
                if depth > 0:
                    depth -= 1
                    if depth == 0 and start >= 0:
                        candidate = text[start:i + 1]
                        if len(candidate) >= 20:
                            try:
                                obj = json.loads(candidate)
                                objects.append(obj)
                            except (json.JSONDecodeError, ValueError):
                                pass
                        start = -1
            elif ch == '"':
                # Skip string literals so inner braces are ignored
                i += 1
                while i < n:
                    c = text[i]
                    if c == '\\':
                        i += 1  # skip escaped char
                    elif c == '"':
                        break
                    i += 1
            i += 1

        return objects

    # ------------------------------------------------------------------
    # Plain string extraction (supplementary only)
    # ------------------------------------------------------------------

    def _extract_strings(self, data: bytes) -> List[str]:
        strings = []
        for encoding in self.config.encodings:
            try:
                text = data.decode(encoding, errors='ignore')
                found = re.findall(r'[\x20-\x7E\t]{8,}', text)
                strings.extend(found)
            except Exception:
                pass
        strings.extend(self._extract_discord_patterns(data))
        return list(set(s for s in strings if len(s) >= self.config.min_string_len))

    def _extract_discord_patterns(self, data: bytes) -> List[str]:
        patterns = []
        # FIX BUG-4: simpler snowflake pattern
        for m in re.finditer(rb'[^0-9]([0-9]{17,19})[^0-9]', data):
            try:
                patterns.append(f"snowflake:{m.group(1).decode('ascii')}")
            except Exception:
                pass
        return patterns

    def _is_discord_json(self, obj: dict) -> bool:
        discord_keys = {
            'content', 'author', 'id', 'channelId', 'guildId',
            'timestamp', 'username', 'nonce', 'type', 'webhook',
        }
        matched = sum(1 for k in discord_keys if k in obj)
        return matched >= self.config.json_key_threshold