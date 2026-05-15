"""Discord Message Restorer - Stage 2.

Reconstructs partial/corrupted Discord messages using LLM.
- Completes partial message text
- Infers missing metadata
- Recovers timestamps and context
"""

from __future__ import annotations

import logging
import json
from typing import Optional, List, Dict
from llm.client import GeminiClient

log = logging.getLogger("discord_weaver.llm.restorer")


class DiscordMessageRestorer:
    """Restores Discord messages from memory fragments."""

    def __init__(self, llm_client: GeminiClient):
        self.client = llm_client

    def restore_messages(
        self, 
        corrupted_messages: List[dict],
        partial_messages: List[dict] = None,
        messages_by_channel: Dict[str, List[dict]] = None
    ) -> List[dict]:
        """Restore corrupted Discord messages.
        
        Args:
            corrupted_messages: List of complete but corrupted message objects
            partial_messages: List of incomplete message objects (FIX BUG-12)
            messages_by_channel: Channel context for restoration (FIX BUG-14)
            
        Returns:
            List of restored messages
        """
        restored = []
        partial_messages = partial_messages or []
        messages_by_channel = messages_by_channel or {}
        
        # Combine all messages
        all_messages = corrupted_messages + partial_messages
        
        for i, msg in enumerate(all_messages):
            if i % 10 == 0:
                print(f"      Restoring message {i+1}/{len(all_messages)}...")
            
            # Get channel context for this message (FIX BUG-14)
            channel_id = (
                msg.get('channel_id') or 
                msg.get('channelId') or 
                'unknown'
            )
            channel_context = messages_by_channel.get(channel_id, [])
            
            # Process with context awareness
            restored_msg = self.restore_single_message(msg, channel_context)
            if restored_msg:
                restored.append(restored_msg)
        
        return restored

    def restore_single_message(
        self, 
        corrupted_msg: dict,
        channel_context: List[dict] = None
    ) -> Optional[dict]:
        """Restore a single corrupted Discord message.
        
        Args:
            corrupted_msg: Partial/corrupted message object
            channel_context: Nearby messages for context (FIX BUG-14)
            
        Returns:
            Restored message or None if restoration failed
        """
        channel_context = channel_context or []
        
        # Check if message needs restoration
        has_content = bool(corrupted_msg.get('content'))
        has_author = bool(corrupted_msg.get('author') or corrupted_msg.get('username'))
        
        # FIX BUG-12: Handle partial messages (missing content OR author)
        is_partial = not (has_content and has_author)
        
        # If complete and clean, skip restoration
        if not is_partial:
            content_val = corrupted_msg.get('content', '')
            content = str(content_val) if content_val is not None else ""
            if len(content) > 100 and not self._looks_corrupted(content):
                return corrupted_msg

        # Try to restore (FIX BUG-13: Enhanced prompt, FIX BUG-14: With context)
        prompt = self._build_restore_prompt(corrupted_msg, channel_context, is_partial)
        
        try:
            restoration = self.client.query(prompt)
            
            if restoration:
                # Update message content with restoration
                restored = corrupted_msg.copy()
                
                # Determine what was restored
                if is_partial:
                    if not has_content:
                        restored['content'] = restoration
                        restored['restored_content'] = True
                    if not has_author:
                        # Try to extract author if present in restoration
                        restored['author_restored'] = True
                    restored['restored_from_partial'] = True
                else:
                    restored['content'] = restoration
                    restored['restored'] = True
                    restored['original_content'] = corrupted_msg.get('content', '')
                
                return restored
        except Exception as e:
            log.error(f"Restoration failed for message {corrupted_msg.get('id')}: {e}")
        
        return corrupted_msg

    def _looks_corrupted(self, text: str) -> bool:
        """Check if text looks corrupted."""
        if not text:
            return True
        
        # Heuristics: too many special chars, broken UTF-8, etc.
        if len(text) == 0:
            return True
            
        special_char_ratio = sum(1 for c in text if ord(c) < 32 or ord(c) > 126) / len(text)
        return special_char_ratio > 0.1

    def _build_restore_prompt(
        self, 
        msg: dict, 
        channel_context: List[dict],
        is_partial: bool = False
    ) -> str:
        """Build restoration prompt for Gemini with Discord context (FIX BUG-13, BUG-14)."""
        content = msg.get('content', '')
        author = msg.get('author', msg.get('username', 'Unknown'))
        channel_id = msg.get('channel_id') or msg.get('channelId', 'Unknown')
        timestamp = msg.get('timestamp', 'Unknown')
        
        # Build context from nearby messages (FIX BUG-14)
        context_str = "No nearby messages"
        if channel_context:
            # Get up to 3 recent messages for context
            recent_messages = channel_context[-3:]
            context_lines = []
            for ctx_msg in recent_messages:
                ctx_author = ctx_msg.get('author', ctx_msg.get('username', 'Unknown'))
                ctx_content = str(ctx_msg.get('content', ''))[:100]
                context_lines.append(f"  {ctx_author}: {ctx_content}")
            if context_lines:
                context_str = "\n".join(context_lines)
        
        if is_partial:
            # Enhanced prompt for partial messages (FIX BUG-12)
            prompt = f"""Restore this incomplete/partial Discord message from memory dump.

Message Metadata:
- Author: {author}
- Channel ID: {channel_id}
- Timestamp: {timestamp}
- Extracted Content: {content if content else "(MISSING)"}

Channel Context (recent messages):
{context_str}

Task:
1. If author is missing: infer from context
2. If content is empty: reconstruct from metadata and context
3. If content is partial: complete it naturally
4. Maintain Discord message style and context
5. Return ONLY the complete message content, no metadata or explanation

Restored Message:"""
        else:
            # Standard prompt for corrupted complete messages (FIX BUG-13)
            prompt = f"""Restore this Discord message that may be corrupted or truncated.

Message Metadata:
- Author: {author}
- Channel ID: {channel_id}
- Timestamp: {timestamp}
- Partial Content: {content}

Channel Context (recent messages):
{context_str}

Task:
1. Complete any truncated text
2. Fix encoding/corruption issues
3. Maintain original meaning and Discord context
4. Consider the conversation context provided
5. Return ONLY the restored message content, no explanation

Restored Message:"""
        
        return prompt
