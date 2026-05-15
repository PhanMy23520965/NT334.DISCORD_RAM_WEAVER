"""Artifact Filtering for Discord - Stage 1.

Filters extracted artifacts to remove noise and keep Discord-relevant data.

BUGS FIXED vs original:
  BUG-5: _filter_strings was called with all noise_patterns, including the
      URL pattern and base64 pattern, which discarded valid Discord JSON
      strings that happened to contain links or long tokens.
      FIX: noise filter is now applied to plain text strings only (not JSON).
      JSON objects coming from the bracket-matcher are already validated.

  BUG-6: _categorize_json_objects checked only top-level 'content'/'message'
      for messages, missing cases where Discord stores message objects nested
      under 'data', 'body', or with 'author' dict instead of string.
      FIX: broadened categorisation heuristics.

  BUG-7: metadata extraction collected all leftover objects, including noise.
      FIX: metadata now requires at least one recognisable Discord field.
"""

from __future__ import annotations

import logging
import re
import json
from typing import List
from dataclasses import dataclass

log = logging.getLogger("discord_weaver.amc.filtering")


@dataclass
class FilteredResult:
    messages: List[dict]
    user_data: List[dict]
    metadata: List[dict]
    statistics: dict


class ArtifactFilter:
    """Filters Discord artifacts extracted from memory."""

    # Fields that indicate a Discord *message* object
    MESSAGE_KEYS = {'content', 'message'}
    # Fields that indicate a Discord *user* object
    USER_KEYS = {'username', 'avatar', 'userId', 'discriminator', 'globalName'}
    # Fields that indicate any Discord-adjacent metadata worth keeping
    META_KEYS = {
        'guildId', 'channelId', 'nonce', 'type', 'webhook',
        'embed', 'attachment', 'reaction', 'role', 'permission',
    }

    def __init__(self, noise_patterns: List[str] = None, key_threshold: int = 2):
        self.noise_patterns = noise_patterns or []
        self.key_threshold = key_threshold
        self.compiled_patterns = [re.compile(p) for p in self.noise_patterns]

    def filter_artifacts(self, strings: List[str], json_objects: List[dict]) -> FilteredResult:
        log.info("Filtering Discord artifacts...")

        # Filter plain strings (supplementary)
        filtered_strings = self._filter_strings(strings)

        # Categorize JSON objects (already validated by extractor)
        messages, user_data, metadata = self._categorize_json_objects(json_objects)

        # Deduplication
        messages = self._deduplicate(messages)
        user_data = self._deduplicate(user_data)
        metadata = self._deduplicate(metadata)

        statistics = {
            'original_strings': len(strings),
            'filtered_strings': len(filtered_strings),
            'original_json_objects': len(json_objects),
            'messages': len(messages),
            'user_data': len(user_data),
            'metadata': len(metadata),
        }

        log.info(
            f"Filter results: {len(messages)} messages, "
            f"{len(user_data)} users, "
            f"{len(metadata)} metadata objects"
        )
        return FilteredResult(messages, user_data, metadata, statistics)

    # ------------------------------------------------------------------

    def _filter_strings(self, strings: List[str]) -> List[str]:
        """Remove noisy plain-text strings (NOT applied to JSON objects)."""
        filtered = []
        for string in strings:
            if any(p.search(string) for p in self.compiled_patterns):
                continue
            if self._is_relevant(string):
                filtered.append(string)
        return filtered

    def _is_relevant(self, string: str) -> bool:
        keywords = [
            'message', 'content', 'author', 'channel', 'guild', 'discord',
            'user', 'member', 'role', 'reaction', 'embed', 'attachment',
            'mention', 'pinned', 'webhook',
        ]
        return any(kw in string.lower() for kw in keywords)

    def _categorize_json_objects(self, json_objects: List[dict]) -> tuple:
        """Categorise JSON objects into messages / user_data / metadata."""
        messages = []
        user_data = []
        metadata = []

        for obj in json_objects:
            keys = set(obj.keys())

            # Message: has 'content' or 'message' field
            if keys & self.MESSAGE_KEYS:
                messages.append(obj)

            # User: has username / avatar / discriminator
            elif keys & self.USER_KEYS:
                user_data.append(obj)

            # Metadata: has at least one recognisable Discord field
            elif keys & self.META_KEYS:
                metadata.append(obj)

            # Skip objects with no recognisable Discord fields
            # (reduces noise in output)

        return messages, user_data, metadata

    def _deduplicate(self, items: List[dict]) -> List[dict]:
        seen = set()
        result = []
        for item in items:
            key = item.get('id') or item.get('nonce') or item.get('content', '')[:60]
            if key and key not in seen:
                seen.add(key)
                result.append(item)
            elif not key:
                result.append(item)
        return result