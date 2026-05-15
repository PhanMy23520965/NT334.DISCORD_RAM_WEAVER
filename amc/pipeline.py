"""Stage 1 – Adaptive Memory Carver Pipeline for Discord.

Orchestrates:
    1. Memory Extraction  (AdaptiveMemoryExtractor)
    2. Artifact Filtering (ArtifactFilter)

Usage::

    from amc.pipeline import AdaptiveMemoryCarver
    from config import AMCConfig

    config = AMCConfig()
    carver = AdaptiveMemoryCarver(config)
    output_path = carver.run("discord.raw", pid=352)
"""

from __future__ import annotations

import logging
import json
import sys
import os
from pathlib import Path
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import AMCConfig
from .extractor import AdaptiveMemoryExtractor
from .filtering import ArtifactFilter

log = logging.getLogger("discord_weaver.amc.pipeline")


class AdaptiveMemoryCarver:
    """End-to-end Stage 1 orchestrator for Discord forensics."""

    def __init__(self, config: AMCConfig):
        self.config = config
        self.extractor = AdaptiveMemoryExtractor(config)
        self.filter = ArtifactFilter(
            noise_patterns=config.noise_patterns,
            key_threshold=config.json_key_threshold,
        )
        self.output_dir = Path(config.output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def run(self, dump_path: str, pid: Optional[int] = None) -> Optional[str]:
        """Run the complete Stage 1 pipeline."""
        log.info("=" * 70)
        log.info("STAGE 1: Adaptive Memory Carver (Discord)")
        log.info("=" * 70)

        # Step 1: Extract
        log.info("[1/2] Extracting Discord artifacts...")
        extraction_result = self.extractor.extract(dump_path, pid)
        log.info(f"      Strings   : {extraction_result.statistics['total_strings']:,}")
        log.info(f"      JSON objs : {extraction_result.statistics['total_json_objects']:,}")

        # Step 2: Filter & categorise
        log.info("[2/2] Filtering artifacts...")
        filter_result = self.filter.filter_artifacts(
            extraction_result.strings,
            extraction_result.json_objects,
        )
        log.info(f"      Messages  : {filter_result.statistics['messages']}")
        log.info(f"      Users     : {filter_result.statistics['user_data']}")
        log.info(f"      Metadata  : {filter_result.statistics['metadata']}")

        # Step 3: Save
        output_file = self._save_output(filter_result, pid)
        log.info(f"✓ Stage 1 complete. Output: {output_file}")
        return str(output_file)

    def _save_output(self, filter_result, pid: Optional[int]) -> Path:
        pid_tag = str(pid) if pid is not None else "unknown"
        output_file = self.output_dir / f"discord_amc_output_pid{pid_tag}.txt"

        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("Discord-Weaver Stage 1 – Adaptive Memory Carver Output\n")
            f.write("=" * 70 + "\n\n")
            f.write(f"Statistics:\n{json.dumps(filter_result.statistics, indent=2)}\n\n")

            f.write(f"Messages ({len(filter_result.messages)}):\n")
            f.write("-" * 70 + "\n")
            for msg in filter_result.messages[:100]:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")

            f.write(f"\nUser Data ({len(filter_result.user_data)}):\n")
            f.write("-" * 70 + "\n")
            for user in filter_result.user_data[:50]:
                f.write(json.dumps(user, ensure_ascii=False) + "\n")

            f.write(f"\nMetadata ({len(filter_result.metadata)}):\n")
            f.write("-" * 70 + "\n")
            for meta in filter_result.metadata[:50]:
                f.write(json.dumps(meta, ensure_ascii=False) + "\n")

        json_file = self.output_dir / f"discord_amc_output_pid{pid_tag}.json"
        with open(json_file, 'w', encoding='utf-8') as f:
            json.dump({
                'statistics': filter_result.statistics,
                'messages': filter_result.messages,
                'user_data': filter_result.user_data,
                'metadata': filter_result.metadata,
            }, f, ensure_ascii=False, indent=2)

        return output_file