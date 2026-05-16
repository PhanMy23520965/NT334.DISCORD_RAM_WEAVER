"""Artifact Filtering for Discord - Stage 1.

Filters extracted artifacts to remove noise and keep Discord-relevant data.

"""

from __future__ import annotations

import logging
import re
import json
from typing import List, Dict
from dataclasses import dataclass

log = logging.getLogger("discord_weaver.amc.filtering")


@dataclass
class FilteredResult:
    messages: List[dict]
    user_data: List[dict]
    metadata: List[dict]
    partial_messages: List[dict]  # FIX BUG-10: New field for partial messages
    messages_by_channel: Dict[str, List[dict]]  # FIX BUG-11: Channel grouping
    statistics: dict


class ArtifactFilter:
    """Filters Discord artifacts extracted from memory."""

    # Fields that indicate a Discord *message* object
    MESSAGE_KEYS = {'content', 'author', 'channel_id', 'channelId', 'guild_id', 'guildId', 'attachments'}
    # Fields that indicate a partial message (missing one of the above)
    PARTIAL_MESSAGE_KEYS = {'content', 'author', 'channel_id', 'channelId', 'timestamp', 'id', 'nonce'}
    # Fields that indicate a Discord *user* object
    USER_KEYS = {'username', 'avatar', 'userId', 'discriminator', 'globalName', 'public_flags'}
    # Fields that indicate any Discord-adjacent metadata worth keeping
    META_KEYS = {
        'guildId', 'channelId', 'nonce', 'type', 'webhook',
        'embed', 'attachment', 'reaction', 'role', 'permission',
        'read_state', 'user_settings', 'experiments'
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
        messages, user_data, metadata, partial_messages = self._categorize_json_objects(json_objects)

        # FIX BUG-11: Group messages by channel for context preservation
        messages_by_channel = self._group_by_channel(messages + partial_messages)

        # Deduplication
        messages = self._deduplicate(messages)
        user_data = self._deduplicate(user_data)
        metadata = self._deduplicate(metadata)
        partial_messages = self._deduplicate(partial_messages)

        statistics = {
            'original_strings': len(strings),
            'filtered_strings': len(filtered_strings),
            'original_json_objects': len(json_objects),
            'messages': len(messages),
            'user_data': len(user_data),
            'metadata': len(metadata),
            'partial_messages': len(partial_messages),  # FIX BUG-10: Report partial messages
            'channels_with_messages': len(messages_by_channel),  # FIX BUG-11: Channel count
        }

        log.info(
            f"Filter results: {len(messages)} complete messages, "
            f"{len(partial_messages)} partial messages, "
            f"{len(user_data)} users, "
            f"{len(metadata)} metadata objects, "
            f"{len(messages_by_channel)} channels"
        )
        return FilteredResult(messages, user_data, metadata, partial_messages, messages_by_channel, statistics)

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
        """Categorise JSON objects into messages / user_data / metadata / partial_messages."""
        messages = []
        user_data = []
        metadata = []
        partial_messages = []  # FIX BUG-10: New category

        for obj in json_objects:
            keys = set(obj.keys())
            
            # Message categorization
            content_keys = {'content', 'message', 'body', 'text', 'description', 'summary'}
            has_content = any(k in keys for k in content_keys)
            has_id = any(k in keys for k in ['id', 'nonce', 'message_id'])
            has_author = any(k in keys for k in ['author', 'username', 'author_id', 'user_id'])
            has_channel = any(k in keys for k in ['channel_id', 'channelId', 'guild_id', 'guildId'])
            
            # User Data (Check this first to avoid misclassification as partial message)
            if ('username' in keys or 'discriminator' in keys) and 'id' in keys:
                user_data.append(obj)
            
            # Complete Message
            elif has_content and (has_author and (has_channel or has_id)):
                messages.append(obj)
            
            # Partial Message / Fragment
            elif has_content or (has_id and (has_author or has_channel)):
                # Filter out obvious UI logs from partial messages
                if obj.get('message') in ['window.blur', 'app.browser-window-blur', 'app.browser-window-focus']:
                    metadata.append(obj)
                else:
                    partial_messages.append(obj)
            
            # User Data fallback
            elif keys & self.USER_KEYS:
                user_data.append(obj)
            
            # Metadata: anything else that looks like Discord
            elif keys & self.META_KEYS:
                metadata.append(obj)
            
            # Fallback: if it has any common Discord key, keep as metadata
            elif any(k in keys for k in ['id', 'timestamp', 'type', 'name']):
                metadata.append(obj)

        return messages, user_data, metadata, partial_messages

    def _group_by_channel(self, messages: List[dict]) -> Dict[str, List[dict]]:
        """FIX BUG-11: Group messages by channel for context preservation."""
        grouped = {}
        
        for msg in messages:
            # Try different channel ID formats
            channel_id = (
                msg.get('channel_id') or 
                msg.get('channelId') or 
                msg.get('guild_id') or 
                msg.get('guildId') or 
                'unknown_channel'
            )
            
            if channel_id not in grouped:
                grouped[channel_id] = []
            grouped[channel_id].append(msg)
        
        log.info(f"Grouped messages into {len(grouped)} channels")
        return grouped

    def _deduplicate(self, items: List[dict]) -> List[dict]:
        seen = set()
        result = []
        for item in items:
            # Safeguard: Ensure content is a string before slicing
            content_val = item.get('content', '')
            content_str = str(content_val)[:60] if content_val is not None else ""
            
            # Try multiple keys for deduplication
            key = (
                item.get('id') or 
                item.get('nonce') or 
                content_str or
                json.dumps(item, sort_keys=True, default=str)[:100]
            )
            
            if key and key not in seen:
                seen.add(key)
                result.append(item)
            elif not key:
                result.append(item)
        
        return result
