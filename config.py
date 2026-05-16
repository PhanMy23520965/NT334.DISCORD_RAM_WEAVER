"""Configuration for Discord-Weaver (flat layout).

AMCConfig (Stage 1) + LLMConfig (Stage 2) for Discord memory analysis.
Adapted from RAM-Weaver for Discord application forensics.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv(Path(__file__).parent / ".env")


# =============================================================================
# Stage 1 – Adaptive Memory Carver for Discord
# =============================================================================

@dataclass
class AMCConfig:
    volatility_path: str | None = None
    python_executable: str | None = None
    volatility_plugin: str = "windows.memmap.Memmap"
    volatility_timeout: int = 600
    vad_dump_dir: str = "./vad_dumps"
    output_dir: str = "./output_discord"
    extraction_mode: str = "auto"
    # Sliding window settings
    chunk_size: int = 64 * 1024          # 64KB chunks for scanning
    overlap_size: int = 8 * 1024         # 8KB overlap to catch boundary messages
    # Regex settings
    regex_max_gap: int = 800             # Max chars between username and content
    encodings: list[str] = field(
        default_factory=lambda: ["utf-8", "utf-16-le"]
    )
    noise_patterns: list[str] = field(default_factory=lambda: [
        r"[A-Za-z]:\\[\w\\/. -]+",
        r"\{[0-9a-fA-F]{8}(?:-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}\}",
        r"(?:[0-9]{1,3}\.){3}[0-9]{1,3}",
    ])

    def __post_init__(self) -> None:
        if self.volatility_path is None:
            self.volatility_path = (
                os.environ.get("DISCORD_VOL_PATH") or
                os.environ.get("RAM_WEAVER_VOL_PATH")
            )
        if self.python_executable is None:
            self.python_executable = (
                os.environ.get("DISCORD_PYTHON") or
                os.environ.get("RAM_WEAVER_PYTHON") or
                os.environ.get("PYTHON_BIN") or
                sys.executable
            )
        if not self.vad_dump_dir:
            self.vad_dump_dir = (
                os.environ.get("DISCORD_VAD_DUMP_DIR") or
                os.environ.get("RAM_WEAVER_VAD_DUMP_DIR") or
                "./vad_dumps"
            )
        if not self.output_dir:
            self.output_dir = (
                os.environ.get("DISCORD_OUTPUT_DIR") or
                os.environ.get("RAM_WEAVER_OUTPUT_DIR") or
                "./output_discord"
            )


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
