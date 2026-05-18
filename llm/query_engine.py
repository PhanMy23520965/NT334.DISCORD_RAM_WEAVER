"""Query Engine for Discord forensic analysis.

Enables forensic queries on extracted Discord data:
- Timeline reconstruction
- User relationship analysis
- Message pattern detection
- Metadata analysis
"""

from __future__ import annotations

import logging
import json
from typing import Optional, List, Dict
from llm.client import GeminiClient

log = logging.getLogger("discord_weaver.llm.query_engine")


class DiscordQueryEngine:
    """Query engine for Discord forensic analysis."""

    def __init__(self, llm_client: GeminiClient):
        self.client = llm_client

    def query(self, context: str, question: str) -> Optional[str]:
        """Execute a forensic query on Discord data.
        
        Args:
            context: Extracted Discord data as text/JSON
            question: Forensic question to answer
            
        Returns:
            Query response or None if failed
        """
        log.info(f"Executing query: {question}")
        
        prompt = self._build_query_prompt(context, question)
        
        try:
            response = self.client.query(prompt)
            return response
        except Exception as e:
            log.error(f"Query failed: {e}")
            return None

    def timeline_analysis(self, messages: List[dict]) -> Optional[str]:
        """Analyze message timeline."""
        context = self._prepare_message_context(messages)
        
        question = """Analyze the Discord message timeline:
1. When was the conversation most active?
2. What are the key events in chronological order?
3. Who were the main participants?
4. Any suspicious activity patterns?"""
        
        return self.query(context, question)

    def user_analysis(self, user_data: List[dict], messages: List[dict]) -> Optional[str]:
        """Analyze user behavior and relationships."""
        context = self._prepare_user_context(user_data, messages)
        
        question = """Analyze Discord user activity:
1. Who are the most active users?
2. What are communication patterns?
3. Any suspicious user behavior?
4. User roles and permissions overview?"""
        
        return self.query(context, question)

    def sentiment_analysis(self, messages: List[dict]) -> Optional[str]:
        """Analyze message sentiment and tone."""
        context = self._prepare_message_context(messages)
        
        question = """Perform sentiment analysis on Discord messages:
1. Overall sentiment (positive/negative/neutral)?
2. Sentiment trends over time?
3. Any controversial discussions?
4. Emotional tone patterns?"""
        
        return self.query(context, question)

    def _build_query_prompt(self, context: str, question: str) -> str:
        """Build query prompt for Gemini."""
        prompt = f"""You are a Discord forensic analyst. Analyze the following extracted Discord data:

CONTEXT:
{context}

QUESTION:
{question}

Please provide a detailed forensic analysis based on the Discord data provided."""
        
        return prompt

    def _prepare_message_context(self, messages: List[dict]) -> str:
        """Prepare message context for query."""
        context_lines = []
        
        for msg in messages[:100]:  # Limit to first 100
            author_data = msg.get('author')
            if isinstance(author_data, dict):
                author = author_data.get('global_name') or author_data.get('username') or "Unknown"
            else:
                author = author_data or msg.get('global_name') or msg.get('username') or "Unknown"
            content = msg.get('content', '')
            timestamp = msg.get('timestamp') or msg.get('raw_timestamp') or 'Unknown'
            channel = msg.get('channel_id') or msg.get('channelId') or 'Unknown'
            
            context_lines.append(
                f"[{timestamp}] {author} ({channel}): {content}"
            )
        
        return "\n".join(context_lines)

    def _prepare_user_context(self, user_data: List[dict], messages: List[dict]) -> str:
        """Prepare user context for query."""
        context = "Users:\n"
        
        for user in user_data[:50]:
            username = user.get('username', 'Unknown')
            user_id = user.get('id', 'Unknown')
            context += f"  - {username} (ID: {user_id})\n"
        
        context += "\nRecent Messages:\n"
        context += self._prepare_message_context(messages)
        
        return context
