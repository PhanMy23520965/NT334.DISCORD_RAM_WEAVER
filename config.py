"""Configuration for Discord-Weaver (flat layout).

AMCConfig (Stage 1) + LLMConfig (Stage 2) for Discord memory analysis.
Adapted from RAM-Weaver for Discord application forensics.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Optional


# =============================================================================
# Stage 1 – Adaptive Memory Carver for Discord
# =============================================================================

@dataclass
class AMCConfig:
    volatility_path: str | None = None
    python_executable: str | None = None
    volatility_timeout: int = 300
    vad_dump_dir: str = "./vad_dumps"
    output_dir: str = "./output_discord"
    extraction_mode: str = "auto"
    encodings: list[str] = field(
        default_factory=lambda: ["utf-8", "utf-16-le"]
    )
    min_string_len: int = 8
    json_keys_of_interest: list[str] = field(default_factory=lambda: [
        "content", "author", "username", "id", "timestamp", "channelId",
        "guildId", "nonce", "type", "webhook", "bot", "message",
        "embed", "attachment", "url",
    ])
    json_key_threshold: int = 2
    noise_patterns: list[str] = field(default_factory=lambda: [
        r"[A-Za-z]:\\[\w\\/. -]+",                          # Windows file paths
        r"\{[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\}",  # GUIDs
        r"https?://[^\s\"'<>]{5,200}",                      # URLs
        r"(?:[0-9]{1,3}\.){3}[0-9]{1,3}",                  # IPv4 addresses
        r"[A-Za-z0-9+/]{40,}={0,2}",                        # base64 blobs ≥40 chars
        r"\\x[0-9a-fA-F]{2}",                               # escaped hex literals
    ])

    def __post_init__(self) -> None:
        if self.volatility_path is None:
            self.volatility_path = os.environ.get("DISCORD_VOL_PATH")
        if self.python_executable is None:
            self.python_executable = (
                os.environ.get("DISCORD_PYTHON") or
                os.environ.get("PYTHON_BIN") or
                sys.executable
            )
        if not self.vad_dump_dir:
            self.vad_dump_dir = os.environ.get("DISCORD_VAD_DUMP_DIR", "./vad_dumps")
        if not self.output_dir:
            self.output_dir = os.environ.get("DISCORD_OUTPUT_DIR", "./output_discord")


# =============================================================================
# Stage 2 – LLM Query & Restoration for Discord
# =============================================================================

@dataclass
class LLMConfig:
    model_name: str = "gemini-2.5-flash"
    api_key: str | None = None
    temperature: float = 0.7
    max_tokens: int = 4096
    timeout: int = 30
    retry_count: int = 3
    chunk_size: int = 8000

    def __post_init__(self) -> None:
        if self.api_key is None:
            self.api_key = os.environ.get("GEMINI_API_KEY")
        if not self.model_name:
            self.model_name = os.environ.get("DISCORD_GEMINI_MODEL", "gemini-2.5-flash")


# =============================================================================
# Main Config Loader
# =============================================================================

@dataclass
class DiscordWeaverConfig:
    amc: AMCConfig = field(default_factory=AMCConfig)
    llm: LLMConfig = field(default_factory=LLMConfig)
    dump_path: str | None = None
    pid: int | None = None
    mode: str = "restore"

    @classmethod
    def from_env(cls) -> "DiscordWeaverConfig":
        """Load configuration from environment variables."""
        return cls(
            amc=AMCConfig(),
            llm=LLMConfig(),
            dump_path=os.environ.get("DISCORD_DUMP_PATH"),
            pid=int(os.environ.get("DISCORD_PID", "0")) or None,
            mode=os.environ.get("DISCORD_MODE", "restore"),
        )
