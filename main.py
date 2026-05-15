#!/usr/bin/env python
"""Discord-Weaver Main Entry Point

Usage:
    python main.py setup      - Run first-time setup
    python main.py diagnose   - Run diagnostics
    python main.py test       - Test components
    python main.py [options]  - Run analysis
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

# Add current directory to path
sys.path.insert(0, str(Path(__file__).parent))


def cmd_setup():
    """Run setup."""
    print("Running setup...")
    from quickstart import main as quickstart_main
    quickstart_main()


def cmd_diagnose():
    """Run diagnostics."""
    print("Running diagnostics...")
    from diagnose import main as diagnose_main
    diagnose_main()


def cmd_test():
    """Run component tests."""
    print("Running component tests...")
    from test_components import main as test_main
    test_main()


def cmd_run(args):
    """Run analysis pipeline."""
    from amc.pipeline import AdaptiveMemoryCarver
    from config import AMCConfig
    
    if not args:
        print("Usage: python main.py run <dump_path> [pid]")
        sys.exit(1)
    
    dump_path = args[0]
    pid = int(args[1]) if len(args) > 1 else None
    
    print(f"Running analysis on {dump_path} (PID: {pid})")
    
    config = AMCConfig()
    carver = AdaptiveMemoryCarver(config)
    output = carver.run(dump_path, pid=pid)
    
    print(f"✓ Complete. Output: {output}")


def main():
    """Main entry point."""
    if len(sys.argv) < 2:
        print(__doc__)
        sys.exit(0)
    
    command = sys.argv[1]
    args = sys.argv[2:]
    
    commands = {
        'setup': cmd_setup,
        'diagnose': cmd_diagnose,
        'test': cmd_test,
        'run': lambda: cmd_run(args),
    }
    
    if command in commands:
        commands[command]()
    else:
        print(f"Unknown command: {command}")
        print(__doc__)
        sys.exit(1)


if __name__ == "__main__":
    main()
