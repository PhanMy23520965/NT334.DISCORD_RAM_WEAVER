#!/usr/bin/env python
"""
Collect data from ALL Discord processes at once
Runs pipeline for each Discord PID and merges results
"""

import os
import sys
from pathlib import Path
import shutil
from datetime import datetime

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))

from amc.pipeline import AdaptiveMemoryCarver
from config import AMCConfig


# All Discord PIDs found
DISCORD_PIDS = [352, 8152, 3500, 7356, 9008, 9960]


def collect_from_all_pids(dump_path):
    """Collect memory from all Discord processes."""
    
    if not os.path.exists(dump_path):
        print(f"✗ Error: Dump file not found: {dump_path}")
        sys.exit(1)
    
    print(f"=== Discord Weaver - Multi-PID Collection ===")
    print(f"Dump: {dump_path}")
    print(f"PIDs to analyze: {DISCORD_PIDS}")
    print(f"Total processes: {len(DISCORD_PIDS)}\n")
    
    config = AMCConfig()
    carver = AdaptiveMemoryCarver(config)
    
    results = {}
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    
    for idx, pid in enumerate(DISCORD_PIDS, 1):
        print(f"[{idx}/{len(DISCORD_PIDS)}] Processing PID {pid}...")
        try:
            output = carver.run(dump_path, pid=pid)
            results[pid] = output
            print(f"    ✓ Success: {output}\n")
        except Exception as e:
            print(f"    ✗ Failed: {e}\n")
            results[pid] = None
    
    # Summary
    print("\n=== Collection Summary ===")
    successful = sum(1 for v in results.values() if v is not None)
    print(f"Successful: {successful}/{len(DISCORD_PIDS)}")
    
    for pid, output in results.items():
        status = "✓" if output else "✗"
        print(f"  {status} PID {pid}: {output if output else 'Failed'}")
    
    # Create combined output directory
    combined_dir = f"output_discord/combined_{timestamp}"
    os.makedirs(combined_dir, exist_ok=True)
    
    print(f"\n✓ Results combined in: {combined_dir}")
    print("\nNext steps:")
    print("  1. Review all extracted data in output_discord/")
    print("  2. Merge Discord conversation threads from all PIDs")
    print("  3. Remove duplicates based on message timestamps/content")
    
    return results


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python collect_all_discord.py <dump_path>")
        print(f"Example: python collect_all_discord.py D:/nt334/discord.raw")
        sys.exit(1)
    
    dump_path = sys.argv[1]
    collect_from_all_pids(dump_path)
