"""Gemini API Client for Discord message analysis.

Handles communication with Google's Gemini API for:
- Message restoration
- Query-based analysis
- Forensic reconstruction
"""

from __future__ import annotations

import logging
import os
from typing import Optional
import google.generativeai as genai

log = logging.getLogger("discord_weaver.llm.client")


class GeminiClient:
    """Client for Gemini API interaction."""

    def __init__(self, api_key: str, model_name: str = "gemini-2.5-flash", 
                 temperature: float = 0.7, max_tokens: int = 4096):
        self.api_key = api_key
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        
        if api_key:
            genai.configure(api_key=api_key)
            self.model = genai.GenerativeModel(model_name)
        else:
            log.warning("No API key provided - Gemini client will not function")
            self.model = None

    def query(self, prompt: str, system_instruction: Optional[str] = None) -> Optional[str]:
        """Send a query to Gemini and get response.
        
        Args:
            prompt: The query/prompt to send
            system_instruction: Optional system instruction
            
        Returns:
            Model response or None if error
        """
        if not self.model:
            log.error("Gemini client not initialized - check API key")
            return None

        try:
            if system_instruction:
                response = self.model.generate_content(
                    [system_instruction, prompt],
                    generation_config=genai.types.GenerationConfig(
                        temperature=self.temperature,
                        max_output_tokens=self.max_tokens,
                    )
                )
            else:
                response = self.model.generate_content(
                    prompt,
                    generation_config=genai.types.GenerationConfig(
                        temperature=self.temperature,
                        max_output_tokens=self.max_tokens,
                    )
                )
            
            return response.text if response else None
        except Exception as e:
            log.error(f"Gemini query failed: {e}")
            return None

    def batch_query(self, prompts: list[str], system_instruction: Optional[str] = None) -> list[str]:
        """Send multiple queries to Gemini.
        
        Args:
            prompts: List of prompts to send
            system_instruction: Optional system instruction
            
        Returns:
            List of responses
        """
        responses = []
        for prompt in prompts:
            response = self.query(prompt, system_instruction)
            responses.append(response or "")
        return responses
