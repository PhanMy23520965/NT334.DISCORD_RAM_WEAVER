"""Stage 1 – Adaptive Memory Carver Pipeline v2 for Discord.

Orchestrates the complete extraction pipeline:
    1. Volatility VAD dump (if PID provided)
    2. Sliding window regex extraction
    3. Deduplication & noise filtering
    4. **Post-filter: Targeted Artifact Filtering (RAM-Weaver paper)**
    5. Clean output generation (text + JSON)

Usage::

    from amc.pipeline import AdaptiveMemoryCarver
    from config import AMCConfig

    config = AMCConfig()
    carver = AdaptiveMemoryCarver(config)
    output_path = carver.run("discord1.raw", pid=6460)
"""

from __future__ import annotations

import logging
import json
import sys
import os
from datetime import datetime
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import AMCConfig
from .extractor import AdaptiveMemoryExtractor, ExtractionResult
from .post_filter import TargetedArtifactFilter, PostFilterResult

log = logging.getLogger("discord_weaver.amc.pipeline")


class AdaptiveMemoryCarver:
    """End-to-end Stage 1 orchestrator for Discord forensics (v2)."""

    def __init__(self, config: AMCConfig):
        self.config = config
        self.extractor = AdaptiveMemoryExtractor(config)
        self.output_dir = Path(config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self, dump_path: str, pid: Optional[int] = None) -> Optional[str]:
        """Run the complete AMC v2 pipeline.
        
        Returns:
            Path to the clean text output file.
        """
        log.info("=" * 70)
        log.info("STAGE 1: Adaptive Memory Carver v2 (Discord)")
        log.info("=" * 70)
        log.info(f"  Dump: {dump_path}")
        log.info(f"  PID:  {pid or 'N/A (raw scan)'}")

        # Step 1: Extract
        log.info("[1/3] Extracting Discord messages (regex + sliding window)...")
        result = self.extractor.extract(dump_path, pid)
        
        log.info(f"  → {result.statistics['unique_messages']} unique messages found")
        log.info(f"  → {result.statistics['duplicates_removed']} duplicates removed")

        # Step 2: Post-filter (RAM-Weaver Targeted Artifact Filtering)
        log.info("[2/3] Targeted Artifact Filtering (RAM-Weaver AMC)...")
        post_filter = TargetedArtifactFilter(
            max_output_bytes=1024 * 1024,  # 1 MB target to accommodate all fragmented texts for Gemini Flash
            min_score=20,
        )
        filter_result = post_filter.filter(result.messages)
        
        log.info(f"  → {filter_result.statistics['final_messages']} messages after filtering")
        log.info(f"  → SNR: {filter_result.snr_db:.2f} dB")

        # Step 3: Save outputs
        log.info("[3/3] Generating output files...")
        
        # Save the full debug output (unfiltered)
        text_file = self._save_text_output(result, filter_result, dump_path, pid)
        json_file = self._save_json_output(result, filter_result, dump_path, pid)
        
        # Save the LLM-ready clean output (filtered)
        llm_file = self._save_llm_output(result, filter_result, pid)
        
        llm_size = os.path.getsize(llm_file)
        log.info(f"✓ Stage 1 complete!")
        log.info(f"  Text output:  {text_file}")
        log.info(f"  JSON output:  {json_file}")
        log.info(f"  LLM-ready:    {llm_file}")
        log.info(f"  LLM size:     {llm_size / 1024:.1f} KB")
        log.info(f"  Messages:     {filter_result.statistics['final_messages']} "
                 f"(from {result.statistics['unique_messages']} raw)")
        log.info(f"  Reduction:    {filter_result.statistics['reduction_pct']:.1f}%")
        log.info(f"  SNR:          {filter_result.snr_db:.2f} dB")
        
        return str(llm_file)

    def _save_text_output(
        self,
        result: ExtractionResult,
        filter_result: PostFilterResult,
        dump_path: str,
        pid: Optional[int],
    ) -> Path:
        """Save human-readable forensic report."""
        pid_tag = str(pid) if pid else "raw"
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        output_file = self.output_dir / f"discord_amc_output_pid{pid_tag}.txt"

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=" * 70 + "\n")
            f.write("Discord-Weaver Stage 1 — Adaptive Memory Carver v2 Output\n")
            f.write("=" * 70 + "\n\n")
            
            f.write(f"Timestamp:    {timestamp}\n")
            f.write(f"Source:       {dump_path}\n")
            f.write(f"PID:          {pid or 'N/A'}\n")
            f.write(f"Owner:        {result.user_info.get('username', 'Unknown')}\n")
            f.write(f"Owner Email:  {result.user_info.get('email', 'N/A')}\n")
            f.write(f"Owner ID:     {result.user_info.get('id', 'N/A')}\n")
            f.write(f"Channels:     {', '.join(sorted(result.channel_ids)) if result.channel_ids else 'N/A'}\n")
            f.write("\n")
            
            f.write(f"Extraction Statistics:\n")
            f.write(f"  Raw candidates:     {result.statistics['total_raw_candidates']:,}\n")
            f.write(f"  Unique messages:    {result.statistics['unique_messages']:,}\n")
            f.write(f"  Duplicates removed: {result.statistics['duplicates_removed']:,}\n")
            f.write(f"  Extraction time:    {result.statistics['extraction_time_seconds']:.1f}s\n")
            f.write("\n")
            
            # Post-filter statistics (RAM-Weaver AMC)
            fs = filter_result.statistics
            f.write(f"Post-Filter Statistics (RAM-Weaver Targeted Artifact Filtering):\n")
            f.write(f"  After category rejection: {fs['after_category_rejection']:,}\n")
            f.write(f"  After signal scoring:     {fs['after_scoring']:,} (threshold ≥ {fs['scoring_threshold']})\n")
            f.write(f"  After deduplication:      {fs['after_dedup']:,}\n")
            f.write(f"  Final messages:           {fs['final_messages']:,}\n")
            f.write(f"  Size reduction:           {fs['input_bytes']:,} → {fs['final_bytes']:,} bytes ({fs['reduction_pct']:.1f}%)\n")
            f.write(f"  SNR:                      {fs['snr_db']:.2f} dB\n")
            f.write("\n")
            
            if fs.get('rejected_by_category'):
                f.write(f"  Category rejection breakdown:\n")
                for cat, count in sorted(fs['rejected_by_category'].items(), key=lambda x: -x[1]):
                    f.write(f"    {cat:25s}: {count:5d}\n")
                f.write("\n")
            
            # Messages grouped by source pattern
            source_groups = {}
            for msg in result.messages:
                source_groups.setdefault(msg.source, []).append(msg)
            
            f.write(f"Extraction sources (pre-filter):\n")
            for source, msgs in sorted(source_groups.items(), key=lambda x: -len(x[1])):
                f.write(f"  {source:25s}: {len(msgs):5d} messages\n")
            f.write("\n")
            
            f.write("-" * 70 + "\n")
            f.write(f"FILTERED MESSAGES ({fs['final_messages']} kept from "
                    f"{result.statistics['unique_messages']} raw)\n")
            f.write("-" * 70 + "\n\n")
            
            for i, msg in enumerate(filter_result.messages, 1):
                name = msg.global_name or msg.username or "(outbound/self)"
                ts = f" [{msg.best_timestamp}]" if msg.best_timestamp else ""
                ch = f" [ch:{msg.channel_id}]" if msg.channel_id else ""
                outbound_tag = " [→SENT]" if msg.is_outbound else ""
                
                f.write(f"[{i:04d}]{ts}{ch}{outbound_tag}\n")
                f.write(f"  {name}: {msg.content}\n\n")

        return output_file

    def _save_json_output(
        self,
        result: ExtractionResult,
        filter_result: PostFilterResult,
        dump_path: str,
        pid: Optional[int],
    ) -> Path:
        """Save structured JSON output for programmatic use."""
        pid_tag = str(pid) if pid else "raw"
        output_file = self.output_dir / f"discord_amc_output_pid{pid_tag}.json"
        
        data = {
            'metadata': {
                'version': 'AMC v2 + RAM-Weaver Post-Filter',
                'timestamp': datetime.now().isoformat(),
                'source': dump_path,
                'pid': pid,
                'extraction_statistics': result.statistics,
                'post_filter_statistics': filter_result.statistics,
                'snr_db': filter_result.snr_db,
                'user_info': result.user_info,
                'channel_ids': list(result.channel_ids),
            },
            'messages': [msg.to_dict() for msg in filter_result.messages],
        }

        with open(output_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return output_file

    def _save_llm_output(
        self,
        result: ExtractionResult,
        filter_result: PostFilterResult,
        pid: Optional[int],
    ) -> Path:
        """Save ultra-clean text output optimized for LLM consumption.
        
        Format (compact, per RAM-Weaver paper):
            === DISCORD FORENSIC EXTRACT ===
            Owner: username | Channels: ...
            === MESSAGES (N items, filtered from M raw) ===
            [timestamp] username: message content
        """
        pid_tag = str(pid) if pid else "raw"
        output_file = self.output_dir / f"amc_output_pid{pid_tag}.txt"
        
        owner = result.user_info.get('username', 'Unknown')
        channels = ', '.join(sorted(result.channel_ids)) if result.channel_ids else 'N/A'
        fs = filter_result.statistics
        
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("=== DISCORD FORENSIC EXTRACT ===\n")
            f.write(f"Owner: {owner} | Channels: {channels}\n")
            f.write(f"=== MESSAGES ({fs['final_messages']} items, "
                    f"filtered from {fs['input_messages']} raw, "
                    f"SNR: {fs['snr_db']:.1f} dB) ===\n")
            
            for msg in filter_result.messages:
                line = msg.to_chat_line()
                f.write(line + "\n")

        return output_file