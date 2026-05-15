"""Stage 1 - Adaptive Memory Carver for Discord.

Extracts Discord-specific artifacts from memory dumps:
- Message content and metadata
- User information
- Channel/Guild IDs
- Timestamps and message history
- Attachments and embeds
"""

from .pipeline import AdaptiveMemoryCarver

__all__ = ["AdaptiveMemoryCarver"]
