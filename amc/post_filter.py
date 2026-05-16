"""Targeted Artifact Filtering for Discord Forensics.

Implements the post-extraction filtering layer to separate conversational
signal from system-level memory noise.
"""

from __future__ import annotations
import re
import logging
import math
from dataclasses import dataclass, field
from typing import List, Dict, Set, Optional

log = logging.getLogger("discord_weaver.amc.post_filter")

@dataclass
class PostFilterResult:
    """Container for post-filter results and forensic statistics."""
    messages: List[any]  # List of DiscordMessage objects
    statistics: Dict[str, any]
    snr_db: float = 0.0

class TargetedArtifactFilter:
    """RAM-Weaver Targeted Artifact Filtering (AMC Phase 2).
    
    Implements high-fidelity signal scoring and category rejection to isolate
    conversational Discord artifacts from system memory noise.
    """
    
    # Categories for noise rejection
    NOISE_CATEGORIES = {
        "UI_LOG": [
            r"window\.(blur|focus)", r"browser-window-(blur|focus)", 
            r"ui\.click", r"scrollerInner__", r"aria-label="
        ],
        "WEB_ASSET": [r"\.woff2", r"\.css", r"webpack", r"sentry", r"breadcrumbs"],
        "V8_INTERNAL": [r"v8::internal", r"__proto__", r"sdkProcessingMetadata", r"eventProcessors"],
        "FILE_PATH": [r"^[A-Za-z]:\\"],
        "SYSTEM_LOG": [r"ResizeObserver loop", r"MessageQueue", r"Draining message from queue"]
    }

    def __init__(self, max_output_bytes: int = 1024 * 1024, min_score: int = 20):
        self.max_output_bytes = max_output_bytes
        self.min_score = min_score
        self.noise_patterns = {
            cat: [re.compile(p, re.I) for p in patterns]
            for cat, patterns in self.NOISE_CATEGORIES.items()
        }

    def filter(self, messages: List[any]) -> PostFilterResult:
        """Run the multi-stage targeted artifact filtering pipeline."""
        input_messages_count = len(messages)
        input_bytes = sum(len(m.content) for m in messages)
        
        # Stage 1: Category Rejection
        rejected_by_cat = {cat: 0 for cat in self.NOISE_CATEGORIES}
        after_cat_rejection = []
        
        for msg in messages:
            content = msg.content
            rejected = False
            for cat, patterns in self.noise_patterns.items():
                if any(p.search(content) for p in patterns):
                    rejected_by_cat[cat] += 1
                    rejected = True
                    break
            if not rejected:
                after_cat_rejection.append(msg)
        
        # Stage 2: Signal Scoring (NLP Heuristics)
        after_scoring = []
        for msg in after_cat_rejection:
            score = self._calculate_signal_score(msg)
            if score >= self.min_score:
                after_scoring.append(msg)
        
        # Stage 3: Deduplication (Post-score)
        seen_content = set()
        after_dedup = []
        for msg in after_scoring:
            content_norm = msg.content.strip().lower()
            if content_norm not in seen_content:
                seen_content.add(content_norm)
                after_dedup.append(msg)
        
        # Stage 4: Size Budgeting (Keep highest score messages first if budget exceeded)
        final_messages = sorted(after_dedup, key=lambda x: self._calculate_signal_score(x), reverse=True)
        
        current_bytes = 0
        budgeted_messages = []
        for msg in final_messages:
            msg_len = len(msg.content)
            if current_bytes + msg_len <= self.max_output_bytes:
                budgeted_messages.append(msg)
                current_bytes += msg_len
            else:
                break
        
        # Sort budgeted messages by timestamp/original order if possible
        # (Stable sort by index if no timestamp available)
        budgeted_messages.sort(key=lambda x: getattr(x, 'best_timestamp', '') or '')

        # Statistics & SNR Calculation
        final_bytes = sum(len(m.content) for m in budgeted_messages)
        reduction_pct = (1 - (final_bytes / max(input_bytes, 1))) * 100
        
        # Signal-to-Noise Ratio (Forensic SNR)
        # SNR = 10 * log10(Signal_Messages / Noise_Messages)
        noise_count = max(input_messages_count - len(budgeted_messages), 1)
        signal_count = max(len(budgeted_messages), 1)
        snr_db = 10 * math.log10(signal_count / noise_count)

        stats = {
            'after_category_rejection': len(after_cat_rejection),
            'after_scoring': len(after_scoring),
            'after_dedup': len(after_dedup),
            'final_messages': len(budgeted_messages),
            'scoring_threshold': self.min_score,
            'input_bytes': input_bytes,
            'final_bytes': final_bytes,
            'reduction_pct': reduction_pct,
            'snr_db': snr_db,
            'input_messages': input_messages_count,
            'rejected_by_category': rejected_by_cat
        }

        return PostFilterResult(
            messages=budgeted_messages,
            statistics=stats,
            snr_db=snr_db
        )

    def _calculate_signal_score(self, msg: any) -> int:
        """Calculate signal score for a message fragment."""
        content = msg.content
        score = 0
        
        # 1. Length bonus
        if 5 < len(content) < 500:
            score += 20
        elif len(content) >= 500:
            score += 10
            
        # 2. Character diversity bonus (natural language vs repetitive code/hex)
        unique_chars = len(set(content))
        if unique_chars > 10:
            score += 15
            
        # 3. Conversational markers
        if any(c in content for c in [' ', '?', '!', '.', ',']):
            score += 10
            
        # 4. Keyword presence
        keywords = ['the', 'and', 'you', 'me', 'discord', 'message', 'chat', 'hello']
        if any(k in content.lower() for k in keywords):
            score += 15
            
        # 5. Outbound priority
        if getattr(msg, 'is_outbound', False):
            score += 30
            
        # 6. Metadata presence
        if getattr(msg, 'username', '') or getattr(msg, 'global_name', ''):
            score += 20
            
        return score
