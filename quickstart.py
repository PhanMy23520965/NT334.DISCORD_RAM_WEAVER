#!/usr/bin/env python
"""Discord-Weaver Quick Start Guide

This script helps you set up and run your first Discord forensic analysis.
"""

from __future__ import annotations

import sys
import os
from pathlib import Path


def print_banner():
    """Print welcome banner."""
    print(r"""
    ╔════════════════════════════════════════════════════════════════╗
    ║                   Discord-Weaver Quick Start                   ║
    ║         Discord Memory Forensics Analysis Tool                 ║
    ╚════════════════════════════════════════════════════════════════╝
    """)


def step1_check_env():
    """Step 1: Check environment."""
    print("\n[Step 1/5] Checking environment...")
    
    env_file = Path(__file__).parent / ".env"
    
    if not env_file.exists():
        print("  ✗ .env file not found")
        print("  → Creating from template...")
        template = Path(__file__).parent / ".env.template"
        if template.exists():
            with open(template) as f:
                content = f.read()
            with open(env_file, 'w') as f:
                f.write(content)
            print("  ✓ .env created. Edit it with your settings.")
            return False
    
    print("  ✓ .env found")
    return True


def step2_check_packages():
    """Step 2: Check packages."""
    print("\n[Step 2/5] Checking packages...")
    
    try:
        import google.generativeai
        print("  ✓ google-generativeai installed")
    except ImportError:
        print("  ✗ google-generativeai not installed")
        print("  → Run: pip install -r requirements.txt")
        return False
    
    return True


def step3_validate_config():
    """Step 3: Validate configuration."""
    print("\n[Step 3/5] Validating configuration...")
    
    required = ['DISCORD_DUMP_PATH', 'DISCORD_PID', 'GEMINI_API_KEY']
    
    env_file = Path(__file__).parent / ".env"
    env_vars = {}
    
    with open(env_file) as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip()
    
    all_set = True
    for var in required:
        if var in env_vars and env_vars[var]:
            print(f"  ✓ {var}")
        else:
            print(f"  ✗ {var} - NOT SET")
            all_set = False
    
    return all_set


def step4_test_components():
    """Step 4: Test components."""
    print("\n[Step 4/5] Testing components...")
    
    try:
        from config import AMCConfig, LLMConfig
        from amc.pipeline import AdaptiveMemoryCarver
        from llm.client import GeminiClient
        
        print("  ✓ All components importable")
        return True
    except Exception as e:
        print(f"  ✗ Component test failed: {e}")
        return False


def step5_first_run():
    """Step 5: Prepare first run."""
    print("\n[Step 5/5] Ready for first run!")
    
    print("""
Next steps:

1. Edit .env with your settings:
   - DISCORD_DUMP_PATH=D:\\path\\to\\discord.raw
   - DISCORD_PID=352 (or your Discord PID)
   - GEMINI_API_KEY=your_api_key_here

2. Run analysis:
   ./run_pipeline.sh

3. Or try individual modes:
   # Restore corrupted messages
   ./run_pipeline.sh D:\\discord.raw 352 restore

   # Execute forensic query
   ./run_pipeline.sh D:\\discord.raw 352 query "Who sent the most messages?"

   # Interactive session
   ./run_pipeline.sh D:\\discord.raw 352 interactive

4. Check output in output_discord/ folder

For more info:
   cat README.md
   python diagnose.py    # Full diagnostics
   python test_components.py  # Component tests
    """)
    return True


def main():
    """Run quick start."""
    print_banner()
    
    steps = [
        ("Environment Setup", step1_check_env),
        ("Package Check", step2_check_packages),
        ("Configuration Validation", step3_validate_config),
        ("Component Testing", step4_test_components),
        ("First Run Setup", step5_first_run),
    ]
    
    failed = []
    
    for name, step_func in steps:
        try:
            if not step_func():
                failed.append(name)
        except Exception as e:
            print(f"  ✗ Error: {e}")
            failed.append(name)
    
    print("\n" + "=" * 70)
    
    if not failed:
        print("✓ Quick start complete! You're ready to use Discord-Weaver")
    else:
        print(f"✗ Some steps failed:")
        for fail in failed:
            print(f"  - {fail}")
        print("\nFix the issues and run this script again.")
    
    print()


if __name__ == "__main__":
    main()
