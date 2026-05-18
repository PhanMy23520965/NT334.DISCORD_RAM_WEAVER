"""Adaptive Memory Extractor v2 for Discord.

Complete rewrite focused on regex-based extraction with sliding window scanning.
Replaces the slow JSON brace-matching approach with efficient pattern matching.

Architecture:
    Phase 1: Volatility VAD dump (subprocess)
    Phase 2: Sliding window scanner (chunked file reading)  
    Phase 3: Multi-pattern regex extraction (core engine)
    Phase 4: Deduplication layer
"""

from __future__ import annotations

import logging
import subprocess
import time
import hashlib
import os
import re
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Set, Tuple
from dataclasses import dataclass, field

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from config import AMCConfig

log = logging.getLogger("discord_weaver.amc.extractor")


# ============================================================================
# Data Models
# ============================================================================

@dataclass
class DiscordMessage:
    """A single extracted Discord message."""
    username: str = ""
    global_name: str = ""
    content: str = ""
    nonce: str = ""
    message_id: str = ""
    channel_id: str = ""
    guild_id: str = ""
    timestamp: str = ""
    is_outbound: bool = False       # User's own outgoing message
    source: str = "unknown"         # regex pattern that found it

    @property
    def signature(self) -> str:
        """Unique signature for deduplication."""
        # Primary key: content + username (case-insensitive)
        key = f"{self.username.lower().strip()}:{self.content.strip()}"
        return hashlib.md5(key.encode('utf-8', errors='ignore')).hexdigest()
    
    @property
    def nonce_key(self) -> str:
        """Nonce-based key for outbound message dedup."""
        return self.nonce if self.nonce else ""
    
    def to_chat_line(self) -> str:
        """Format as clean chat line: [time] username: content"""
        name = self.global_name or self.username or "Unknown"
        ts = f"[{self.best_timestamp}] " if self.best_timestamp else ""
        return f"{ts}{name}: {self.content}"
    
    @property
    def best_timestamp(self) -> str:
        """Get the most accurate timestamp, decoding Snowflake IDs if needed."""
        if self.timestamp:
            return self.timestamp
        # Decode from message_id or nonce (both are Snowflake IDs)
        snowflake = self.message_id or self.nonce
        if snowflake and snowflake.isdigit():
            try:
                # Discord Snowflake format: (id >> 22) + 1420070400000
                ts_ms = (int(snowflake) >> 22) + 1420070400000
                return datetime.fromtimestamp(ts_ms / 1000.0).strftime('%Y-%m-%d %H:%M:%S')
            except Exception:
                pass
        return ""

    @property
    def timestamp_source(self) -> str:
        """Describe where the exported timestamp came from."""
        if self.timestamp:
            return "embedded_timestamp"
        if self.message_id and self.message_id.isdigit():
            return "message_id_snowflake"
        if self.nonce and self.nonce.isdigit():
            return "nonce_snowflake"
        return "unavailable"
    
    def to_dict(self) -> dict:
        """Convert to dict for JSON serialization."""
        return {
            'username': self.username,
            'global_name': self.global_name,
            'content': self.content,
            'nonce': self.nonce,
            'message_id': self.message_id,
            'channel_id': self.channel_id,
            'guild_id': self.guild_id,
            'timestamp': self.best_timestamp,
            'raw_timestamp': self.timestamp,
            'timestamp_source': self.timestamp_source,
            'is_outbound': self.is_outbound,
            'source': self.source,
        }


@dataclass
class ExtractionResult:
    """Result of the AMC extraction pipeline."""
    messages: List[DiscordMessage]
    user_info: Dict[str, str]       # Detected user info (id, username, email)
    channel_ids: Set[str]
    statistics: dict


# ============================================================================
# Compiled Regex Patterns
# ============================================================================

# Pattern 1: Outbound message payloads (user sending a message)
# {"mobile_network_type":"unknown","content":"...","nonce":"...","tts":false,"flags":0}
RE_OUTBOUND = re.compile(
    r'"content"\s*:\s*"(?P<content>[^"]{1,2000})"'
    r'.{0,300}?'
    r'"nonce"\s*:\s*"(?P<nonce>\d{15,25})"',
    re.DOTALL
)

# Pattern 1b: Outbound with nonce before content
RE_OUTBOUND_REV = re.compile(
    r'"nonce"\s*:\s*"(?P<nonce>\d{15,25})"'
    r'.{0,300}?'
    r'"content"\s*:\s*"(?P<content>[^"]{1,2000})"',
    re.DOTALL
)

# Pattern 2: API response — username near content (author → content)
RE_API_MSG = re.compile(
    r'"username"\s*:\s*"(?P<username>[^"]{1,100})"'
    r'.{0,800}?'
    r'"content"\s*:\s*"(?P<content>[^"]*)"',
    re.DOTALL
)

# Pattern 3: API response — content near username (content → author)  
RE_API_MSG_REV = re.compile(
    r'"content"\s*:\s*"(?P<content>[^"]+)"'
    r'.{0,800}?'
    r'"username"\s*:\s*"(?P<username>[^"]{1,100})"',
    re.DOTALL
)

# Pattern 4: Full author block with nested object
RE_AUTHOR_BLOCK = re.compile(
    r'"author"\s*:\s*\{[^}]*?"username"\s*:\s*"(?P<username>[^"]+)"'
    r'[^}]*?\}'
    r'.{0,500}?'
    r'"content"\s*:\s*"(?P<content>[^"]*)"',
    re.DOTALL
)

# Pattern 4b: Content before author block
RE_AUTHOR_BLOCK_REV = re.compile(
    r'"content"\s*:\s*"(?P<content>[^"]+)"'
    r'.{0,500}?'
    r'"author"\s*:\s*\{[^}]*?"username"\s*:\s*"(?P<username>[^"]+)"',
    re.DOTALL
)

# Pattern 5: Standalone content fields with nearby id/nonce
RE_CONTENT_WITH_ID = re.compile(
    r'"content"\s*:\s*"(?P<content>[^"]{1,2000})"'
    r'.{0,200}?'
    r'"id"\s*:\s*"(?P<id>\d{15,25})"',
    re.DOTALL
)

# Pattern 6: Windows Toast XML notification — captures messages received from others
# <text>Asamai</text><text>message content</text>
RE_TOAST_MSG = re.compile(
    r'<text>(?P<username>[^<]{1,100})</text>\s*<text>(?P<content>[^<]{1,2000})</text>',
    re.DOTALL
)

# Pattern 7: Outbound payload inside _version JSON wrapper (fragmented / binary adjacent)
# "content":"...","nonce":"..." inside {"op":...,"d":{"content":"...","nonce":"...",...},...,"_version":2}
RE_OUTBOUND_WRAPPED = re.compile(
    r'"content"\s*:\s*"(?P<content>[^"]{1,2000})"'
    r'.{0,300}?'
    r'"nonce"\s*:\s*"(?P<nonce>\d{15,25})"'
    r'.{0,500}?'
    r'_version',
    re.DOTALL
)

# Pattern 8: msgpack-style binary format — global_name near content field
# (Discord stores messages in a compact binary format in V8 heap)
# Looks like: ...global_namem....my phan...contentm...actual message...
RE_BINARY_MSG = re.compile(
    r'global_name.{1,20}(?P<global_name>[A-Za-z][\w ]{0,30}).{0,800}?'
    r'content.{1,20}(?P<content>[\w][^\x00-\x1f]{3,500}?)'
    r'(?=[\x00-\x1f"\{\}])',
    re.DOTALL
)

# Metadata extractors
RE_CHANNEL_ID = re.compile(r'"channel_id"\s*:\s*"(?P<channel_id>\d{15,25})"')
RE_GUILD_ID = re.compile(r'"guild_id"\s*:\s*"(?P<guild_id>\d{15,25})"')
RE_TIMESTAMP = re.compile(r'"timestamp"\s*:\s*"(?P<timestamp>\d{4}-\d{2}-\d{2}T[^"]+)"')
RE_GLOBAL_NAME = re.compile(r'"global_name"\s*:\s*"(?P<global_name>[^"]+)"')
RE_MSG_ID = re.compile(r'"id"\s*:\s*"(?P<id>\d{15,25})"')
RE_TOP_LEVEL_MSG_ID = re.compile(
    r'"id"\s*:\s*"(?P<id>\d{15,25})"\s*,\s*"type"\s*:\s*\d+',
    re.DOTALL
)

# User info detection
RE_USER_INFO = re.compile(
    r'"user"\s*:\s*\{'
    r'[^}]*?"id"\s*:\s*"(?P<id>\d{15,25})"'
    r'[^}]*?"username"\s*:\s*"(?P<username>[^"]+)"'
    r'(?:[^}]*?"email"\s*:\s*"(?P<email>[^"]+)")?',
    re.DOTALL
)

# ============================================================================
# Noise Detection
# ============================================================================

NOISE_CONTENT_PATTERNS = [
    'preloaded using link preload',
    'ResizeObserver loop',
    'MessageQueue',
    'browser-window-blur',
    'browser-window-focus',
    'window.blur',
    'window.focus',
    'app.browser-window',
    'ui.click',
    'woff2',
    'breadcrumbs',
    'sdkProcessingMetadata',
    'eventProcessors',
    'fingerprint',
    'propagationContext',
    'sentry',
    'webpack',
    'electron',
    'nativeBuildNumber',
    'app_start_time',
    'The resource https://',
    'link preload but not used',
    'Please make sure it has',
    'Queueing message to be sent',
    'Draining message from queue',
    'Draining Message Queue',
    'Finished draining message',
    'undelivered notifications',
    'file already exists',
    # JavaScript/CSS selectors
    'scrollerInner__',
    'aria-label=',
    # V8 internals
    'v8::internal',
    '__proto__',
]

NOISE_USERNAME_PATTERNS = [
    'undefined',
    'null',
    'true',
    'false',
    'object',
    'function',
    'NaN',
]


def is_noise_content(content: str) -> bool:
    """Check if content is noise/metadata rather than a real message."""
    if not content or not content.strip():
        return True
    
    content_lower = content.lower().strip()
    
    # Too short to be meaningful (but allow emoji-only)
    if len(content_lower) < 1:
        return True
    
    # Contains noise patterns
    for pattern in NOISE_CONTENT_PATTERNS:
        if pattern.lower() in content_lower:
            return True
    
    # Looks like a URL only
    if content_lower.startswith(('http://', 'https://')) and ' ' not in content_lower:
        # URLs alone are still data, keep them
        return False
    
    # Looks like a file path
    if re.match(r'^[A-Za-z]:\\', content):
        return True
    
    # Mostly non-printable characters
    printable_ratio = sum(1 for c in content if c.isprintable()) / max(len(content), 1)
    if printable_ratio < 0.5:
        return True
    
    # Very long base64-like strings
    if len(content) > 100 and re.match(r'^[A-Za-z0-9+/=]+$', content):
        return True
    
    return False


def is_noise_username(username: str) -> bool:
    """Check if username is noise."""
    if not username or not username.strip():
        return True
    
    if username.lower().strip() in NOISE_USERNAME_PATTERNS:
        return True
    
    # Too long for a Discord username (max 32 chars)
    if len(username) > 32:
        return True
    
    # Contains suspicious patterns
    if re.match(r'^\d+$', username):  # All digits
        return True
    
    return False


# ============================================================================
# Main Extractor Class
# ============================================================================

class AdaptiveMemoryExtractor:
    """Extracts Discord chat messages from memory dumps using regex patterns.
    
    v2 Architecture:
        1. Volatility VAD dump → .dmp files
        2. Sliding window scanner → text chunks
        3. Multi-regex extraction → DiscordMessage objects
        4. Deduplication → unique messages
    """

    def __init__(self, config: AMCConfig):
        self.config = config
        self.vad_dump_dir = Path(config.vad_dump_dir)
        self.vad_dump_dir.mkdir(parents=True, exist_ok=True)
        
        # Deduplication state
        self._seen_signatures: Set[str] = set()
        self._seen_nonces: Set[str] = set()
        self._detected_owner: str = ""  # Auto-detected dump owner username
        self._user_info: Dict[str, str] = {}
        self._channel_ids: Set[str] = set()

    def extract(self, dump_path: str, pid: Optional[int] = None) -> ExtractionResult:
        """Run the full extraction pipeline."""
        log.info(f"AMC v2: Extracting Discord messages from {dump_path}")
        start_time = time.time()
        
        all_messages: List[DiscordMessage] = []
        
        if pid:
            log.info(f"Targeting PID {pid} using Volatility 3...")
            
            # Check for existing VAD dumps
            pid_dir = self.vad_dump_dir / f"pid_{pid}"
            vad_files = list(pid_dir.glob("*.dmp"))
            
            if not vad_files:
                vad_files = self._run_volatility_vaddump(dump_path, pid)
            else:
                log.info(f"Found existing {len(vad_files)} VAD dump files, skipping Volatility.")
            
            if vad_files:
                total_size = sum(f.stat().st_size for f in vad_files)
                log.info(f"Scanning {len(vad_files)} VAD files ({total_size / (1024*1024):.1f} MB)...")
                
                for i, vad_file in enumerate(vad_files):
                    file_size = vad_file.stat().st_size
                    if file_size < 100:  # Skip tiny files
                        continue
                    log.info(f"  [{i+1}/{len(vad_files)}] {vad_file.name} ({file_size / (1024*1024):.1f} MB)")
                    messages = self._scan_file_sliding_window(str(vad_file))
                    all_messages.extend(messages)
                    log.info(f"    → Found {len(messages)} raw message candidates")
            else:
                log.warning(f"No VAD dumps for PID {pid}, falling back to raw scan")
                pid = None
        
        if not pid:
            # Raw scan of entire dump
            log.info("Performing raw scan of entire dump file...")
            all_messages = self._scan_file_sliding_window(dump_path)
        
        # Deduplicate
        unique_messages = self._deduplicate(all_messages)
        
        # Auto-assign owner username to outbound messages
        if self._detected_owner:
            for msg in unique_messages:
                if msg.is_outbound and not msg.username:
                    msg.username = self._detected_owner
        
        elapsed = time.time() - start_time
        
        statistics = {
            'total_raw_candidates': len(all_messages),
            'unique_messages': len(unique_messages),
            'duplicates_removed': len(all_messages) - len(unique_messages),
            'detected_owner': self._detected_owner,
            'user_info': self._user_info,
            'channels_found': len(self._channel_ids),
            'channel_ids': list(self._channel_ids),
            'extraction_time_seconds': round(elapsed, 2),
            'pid': pid,
        }
        
        log.info(f"Extraction complete in {elapsed:.1f}s:")
        log.info(f"  Raw candidates:    {len(all_messages):,}")
        log.info(f"  Unique messages:   {len(unique_messages):,}")
        log.info(f"  Duplicates removed: {len(all_messages) - len(unique_messages):,}")
        log.info(f"  Detected owner:    {self._detected_owner or 'N/A'}")
        log.info(f"  Channels found:    {len(self._channel_ids)}")
        
        return ExtractionResult(
            messages=unique_messages,
            user_info=self._user_info,
            channel_ids=self._channel_ids,
            statistics=statistics,
        )

    # ------------------------------------------------------------------
    # Phase 1: Volatility VAD Dump
    # ------------------------------------------------------------------

    def _run_volatility_vaddump(self, dump_path: str, pid: int) -> List[Path]:
        """Execute Volatility 3 to dump process memory."""
        if not self.config.volatility_path:
            log.error("Volatility path not configured!")
            return []

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
            
            return list(pid_dir.glob("*.dmp"))
        except subprocess.TimeoutExpired:
            log.error(f"Volatility timed out after {self.config.volatility_timeout}s")
            return []
        except Exception as e:
            log.error(f"Failed to run Volatility: {e}")
            return []

    # ------------------------------------------------------------------
    # Phase 2: Sliding Window Scanner
    # ------------------------------------------------------------------

    def _scan_file_sliding_window(self, filepath: str) -> List[DiscordMessage]:
        """Scan a file using overlapping sliding window for regex extraction."""
        file_size = os.path.getsize(filepath)
        chunk_size = self.config.chunk_size
        overlap_size = self.config.overlap_size
        
        messages: List[DiscordMessage] = []
        
        with open(filepath, 'rb') as f:
            prev_tail = b''
            bytes_read = 0
            last_pct = -1
            
            while True:
                chunk = f.read(chunk_size)
                if not chunk:
                    break
                
                bytes_read += len(chunk)
                
                # Combine with tail from previous chunk to handle boundary cases
                combined = prev_tail + chunk
                
                # Try UTF-8 decode
                text = combined.decode('utf-8', errors='ignore')
                if text:
                    msgs = self._extract_messages_from_text(text)
                    messages.extend(msgs)
                
                # Also try UTF-16LE decode (V8 engine uses this)
                try:
                    text_u16 = combined.decode('utf-16-le', errors='ignore')
                    if text_u16 and len(text_u16) > 10:
                        msgs_u16 = self._extract_messages_from_text(text_u16)
                        messages.extend(msgs_u16)
                except Exception:
                    pass
                
                # Save overlap for next iteration
                prev_tail = chunk[-overlap_size:] if len(chunk) >= overlap_size else chunk
                
                # Progress logging
                pct = (bytes_read * 100) // file_size
                if pct >= last_pct + 10:
                    log.info(f"    Scan progress: {pct}% ({bytes_read // (1024*1024)}/{file_size // (1024*1024)} MB)")
                    last_pct = pct
        
        # Also detect user info and channel IDs
        self._detect_metadata_from_file(filepath)
        
        return messages

    # ------------------------------------------------------------------
    # Phase 3: Multi-Pattern Regex Extraction
    # ------------------------------------------------------------------

    def _enrich_message_metadata(
        self,
        msg: DiscordMessage,
        text: str,
        start: int,
        end: int,
        radius: int = 1200,
    ) -> DiscordMessage:
        """Attach nearby Discord metadata to a regex match when available."""
        nearby = text[max(0, start - radius):min(len(text), end + radius)]

        if not msg.timestamp:
            ts = RE_TIMESTAMP.search(nearby)
            if ts:
                msg.timestamp = ts.group('timestamp')

        if not msg.channel_id:
            channel = RE_CHANNEL_ID.search(nearby)
            if channel:
                msg.channel_id = channel.group('channel_id')
                self._channel_ids.add(msg.channel_id)

        if not msg.guild_id:
            guild = RE_GUILD_ID.search(nearby)
            if guild:
                msg.guild_id = guild.group('guild_id')

        if not msg.message_id:
            # Avoid generic "id" matches inside author/user objects; these are
            # not message timestamps. Message objects normally carry id + type.
            msg_id = RE_TOP_LEVEL_MSG_ID.search(nearby)
            if msg_id:
                msg.message_id = msg_id.group('id')

        if not msg.global_name:
            global_name = RE_GLOBAL_NAME.search(nearby)
            if global_name and not is_noise_username(global_name.group('global_name')):
                msg.global_name = global_name.group('global_name')

        return msg

    def _extract_messages_from_text(self, text: str) -> List[DiscordMessage]:
        """Extract Discord messages from text using multiple regex patterns."""
        messages: List[DiscordMessage] = []
        
        # --- Pattern 1: Outbound messages (user sending) ---
        for m in RE_OUTBOUND.finditer(text):
            content = m.group('content')
            nonce = m.group('nonce')
            if not is_noise_content(content):
                msg = DiscordMessage(
                    content=content,
                    nonce=nonce,
                    is_outbound=True,
                    source='outbound',
                )
                msg = self._enrich_message_metadata(msg, text, m.start(), m.end())
                messages.append(msg)
        
        for m in RE_OUTBOUND_REV.finditer(text):
            content = m.group('content')
            nonce = m.group('nonce')
            if not is_noise_content(content):
                msg = DiscordMessage(
                    content=content,
                    nonce=nonce,
                    is_outbound=True,
                    source='outbound_rev',
                )
                msg = self._enrich_message_metadata(msg, text, m.start(), m.end())
                messages.append(msg)
        
        # --- Pattern 2: API messages with author block ---
        for m in RE_AUTHOR_BLOCK.finditer(text):
            username = m.group('username')
            content = m.group('content')
            if not is_noise_content(content) and not is_noise_username(username):
                msg = DiscordMessage(
                    username=username,
                    content=content,
                    source='author_block',
                )
                msg = self._enrich_message_metadata(msg, text, m.start(), m.end())
                messages.append(msg)
        
        for m in RE_AUTHOR_BLOCK_REV.finditer(text):
            username = m.group('username')
            content = m.group('content')
            if not is_noise_content(content) and not is_noise_username(username):
                msg = DiscordMessage(
                    username=username,
                    content=content,
                    source='author_block_rev',
                )
                msg = self._enrich_message_metadata(msg, text, m.start(), m.end())
                messages.append(msg)
        
        # --- Pattern 3: Simple username + content proximity ---
        for m in RE_API_MSG.finditer(text):
            username = m.group('username')
            content = m.group('content')
            if not is_noise_content(content) and not is_noise_username(username):
                # Verify the gap doesn't cross message boundaries
                gap = m.group(0)[len(f'"username":"{username}"'):]
                gap = gap[:gap.find(f'"content":"{content}"')]
                if '"content"' not in gap:  # No other content field in between
                    msg = DiscordMessage(
                        username=username,
                        content=content,
                        source='api_username_content',
                    )
                    msg = self._enrich_message_metadata(msg, text, m.start(), m.end())
                    messages.append(msg)
        
        for m in RE_API_MSG_REV.finditer(text):
            username = m.group('username')
            content = m.group('content')
            if not is_noise_content(content) and not is_noise_username(username):
                msg = DiscordMessage(
                    username=username,
                    content=content,
                    source='api_content_username',
                )
                msg = self._enrich_message_metadata(msg, text, m.start(), m.end())
                messages.append(msg)
        
        # --- Pattern 4: Content + ID (fallback for fragmented data) ---
        for m in RE_CONTENT_WITH_ID.finditer(text):
            content = m.group('content')
            msg_id = m.group('id')
            if not is_noise_content(content):
                msg = DiscordMessage(
                    content=content,
                    message_id=msg_id,
                    source='content_with_id',
                )
                msg = self._enrich_message_metadata(msg, text, m.start(), m.end())
                messages.append(msg)
        
        # --- Pattern 6: Windows Toast XML notification (messages received from others) ---
        for m in RE_TOAST_MSG.finditer(text):
            username = m.group('username')
            content = m.group('content')
            if not is_noise_content(content) and not is_noise_username(username):
                # Skip system notifications (Windows Defender, etc.)
                if any(skip in username for skip in ['Windows', 'Microsoft', 'Defender', 'Security']):
                    continue
                msg = DiscordMessage(
                    username=username,
                    global_name=username,
                    content=content,
                    source='toast_notification',
                )
                msg = self._enrich_message_metadata(msg, text, m.start(), m.end())
                messages.append(msg)
        
        # --- Pattern 7: Outbound wrapped in _version container ---
        for m in RE_OUTBOUND_WRAPPED.finditer(text):
            content = m.group('content')
            nonce = m.group('nonce')
            if not is_noise_content(content):
                msg = DiscordMessage(
                    content=content,
                    nonce=nonce,
                    is_outbound=True,
                    source='outbound_wrapped',
                )
                msg = self._enrich_message_metadata(msg, text, m.start(), m.end())
                messages.append(msg)
        
        # --- Extract metadata for context enrichment ---
        # Channel IDs
        for m in RE_CHANNEL_ID.finditer(text):
            self._channel_ids.add(m.group('channel_id'))
        
        # Timestamps — try to attach to nearby messages
        # (handled in post-processing)
        
        # Global names
        for m in RE_GLOBAL_NAME.finditer(text):
            gn = m.group('global_name')
            if not is_noise_username(gn):
                # Try to find nearby username to map global_name → username
                pos = m.start()
                nearby = text[max(0, pos-500):pos+500]
                um = re.search(r'"username"\s*:\s*"([^"]+)"', nearby)
                if um:
                    # Store mapping (useful for display)
                    for msg in messages:
                        if msg.username == um.group(1) and not msg.global_name:
                            msg.global_name = gn
        
        # User info detection (for auto-detecting dump owner)
        for m in RE_USER_INFO.finditer(text):
            user_id = m.group('id')
            username = m.group('username')
            email = m.group('email') if m.group('email') else ""
            
            if not is_noise_username(username):
                self._user_info = {
                    'id': user_id,
                    'username': username,
                    'email': email,
                }
                if not self._detected_owner:
                    self._detected_owner = username
                    log.info(f"  Auto-detected dump owner: {username} (ID: {user_id})")
        
        return messages

    def _detect_metadata_from_file(self, filepath: str):
        """Quick scan for metadata (user info, channels) in smaller chunks."""
        # Only scan first 50MB for metadata to save time
        max_scan = 50 * 1024 * 1024
        file_size = os.path.getsize(filepath)
        scan_size = min(file_size, max_scan)
        
        with open(filepath, 'rb') as f:
            data = f.read(scan_size)
        
        text = data.decode('utf-8', errors='ignore')
        
        # Find user info if not already detected
        if not self._detected_owner:
            for m in RE_USER_INFO.finditer(text):
                username = m.group('username')
                if not is_noise_username(username):
                    self._detected_owner = username
                    self._user_info = {
                        'id': m.group('id'),
                        'username': username,
                        'email': m.group('email') or '',
                    }
                    log.info(f"  Detected owner from metadata: {username}")
                    break
        
        # Collect channel IDs
        for m in RE_CHANNEL_ID.finditer(text):
            self._channel_ids.add(m.group('channel_id'))
        
        # Try to find channel names from URL patterns
        # https://discordapp.com/channels/@me/1504737847104766034
        for m in re.finditer(r'channels/@me/(\d{15,25})', text):
            self._channel_ids.add(m.group(1))

    # ------------------------------------------------------------------
    # Phase 4: Deduplication
    # ------------------------------------------------------------------

    def _deduplicate(self, messages: List[DiscordMessage]) -> List[DiscordMessage]:
        """Remove duplicate messages using content-only hash (ignores username for dedup).
        
        Merges metadata: if two messages have same content, the one with more
        metadata (username, global_name, channel_id) wins.
        """
        # Use content-only signature for dedup (normalized whitespace, lowercased)
        seen_content_sigs: Set[str] = set()
        seen_nonces: Set[str] = set()
        
        # Map content_sig -> index in unique list
        content_to_idx: dict = {}
        unique: List[DiscordMessage] = []
        
        for msg in messages:
            # Skip empty content
            if not msg.content or not msg.content.strip():
                continue
            
            # Nonce-based dedup for outbound messages
            if msg.nonce:
                if msg.nonce in seen_nonces:
                    continue
                seen_nonces.add(msg.nonce)
            
            # Content-based dedup (normalize: strip + lowercase)
            content_norm = msg.content.strip().lower()
            content_sig = hashlib.md5(content_norm.encode('utf-8', errors='ignore')).hexdigest()
            
            if content_sig in content_to_idx:
                # Merge metadata into existing entry
                existing = unique[content_to_idx[content_sig]]
                
                # Take the username if existing lacks one
                if not existing.username and msg.username:
                    existing.username = msg.username
                # Take global_name if missing
                if not existing.global_name and msg.global_name:
                    existing.global_name = msg.global_name
                # Take channel_id if missing
                if not existing.channel_id and msg.channel_id:
                    existing.channel_id = msg.channel_id
                # Take timestamp if missing
                if not existing.timestamp and msg.timestamp:
                    existing.timestamp = msg.timestamp
                # Take message_id if missing
                if not existing.message_id and msg.message_id:
                    existing.message_id = msg.message_id
                # Take nonce if missing
                if not existing.nonce and msg.nonce:
                    existing.nonce = msg.nonce
                # If new version has better source priority, note it
                source_priority = {
                    'author_block': 1, 'author_block_rev': 1,
                    'outbound': 2, 'outbound_rev': 2, 'outbound_wrapped': 2,
                    'api_username_content': 3, 'api_content_username': 3,
                    'toast_notification': 4,
                    'content_with_id': 5,
                    'unknown': 99,
                }
                # Keep higher priority source name
                continue
            
            content_to_idx[content_sig] = len(unique)
            seen_content_sigs.add(content_sig)
            unique.append(msg)
        
        return unique
