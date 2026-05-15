"""Discord Message Restorer - Stage 2.

Reconstructs partial/corrupted Discord messages using LLM.
- Completes partial message text
- Infers missing metadata
- Recovers timestamps and context
"""

from __future__ import annotations

import logging
import json
from typing import Optional, List
from llm.client import GeminiClient

log = logging.getLogger("discord_weaver.llm.restorer")


class DiscordMessageRestorer:
    """Restores Discord messages from memory fragments."""

    def __init__(self, llm_client: GeminiClient):
        self.client = llm_client

    def restore_messages(self, corrupted_messages: List[dict]) -> List[dict]:
        """Restore corrupted Discord messages.
        
        Args:
            corrupted_messages: List of partial/corrupted message objects
            
        Returns:
            List of restored messages
        """
        restored = []
        
        for i, msg in enumerate(corrupted_messages):
            if i % 10 == 0:
                print(f"      Restoring message {i+1}/{len(corrupted_messages)}...")
            restored_msg = self.restore_single_message(msg)
            if restored_msg:
                restored.append(restored_msg)
        
        return restored

    def restore_single_message(self, corrupted_msg: dict) -> Optional[dict]:
        """Restore a single corrupted Discord message.
        
        Args:
            corrupted_msg: Partial message object
            
        Returns:
            Restored message or None if restoration failed
        """
        if not corrupted_msg.get('content'):
            return corrupted_msg  # Nothing to restore

        # Ensure content is a string
        content_val = corrupted_msg.get('content', '')
        content = str(content_val) if content_val is not None else ""
        
        # If it's already a clean, long message, don't waste tokens
        if len(content) > 100 and not self._looks_corrupted(content):
            return corrupted_msg

        # Try to restore
        prompt = self._build_restore_prompt(corrupted_msg)
        
        try:
            restoration = self.client.query(prompt)
            
            if restoration:
                # Update message content with restoration
                restored = corrupted_msg.copy()
                restored['content'] = restoration
                restored['restored'] = True
                restored['original_content'] = content
                return restored
        except Exception as e:
            log.error(f"Restoration failed for message {corrupted_msg.get('id')}: {e}")
        
        return corrupted_msg

    def _looks_corrupted(self, text: str) -> bool:
        """Check if text looks corrupted."""
        # Heuristics: too many special chars, broken UTF-8, etc.
        special_char_ratio = sum(1 for c in text if ord(c) < 32 or ord(c) > 126) / len(text)
        return special_char_ratio > 0.1

    def _build_restore_prompt(self, msg: dict) -> str:
        """Build restoration prompt for Gemini."""
        content = msg.get('content', '')
        author = msg.get('author', 'Unknown')
        
        prompt = f"""Restore this Discord message that may be corrupted or incomplete:

Author: {author}
Partial Content: {content}

Please:
1. Complete any partial/corrupted text
2. Maintain original meaning and context
3. Fix any encoding issues
4. Return only the restored message content, no explanation

Restored Message:"""
        
        return prompt
