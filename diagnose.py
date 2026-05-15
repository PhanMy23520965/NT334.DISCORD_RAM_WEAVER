#!/usr/bin/env python
"""Diagnostic script for Discord-Weaver environment setup.

Checks:
- Python version
- Required packages
- .env configuration
- API key validity
- Dump file accessibility
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

def check_python_version():
    """Check Python version."""
    print("📌 Python Version Check")
    version = f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}"
    print(f"   Python: {version}")
    if sys.version_info >= (3, 8):
        print("   ✓ Python version OK\n")
        return True
    else:
        print("   ✗ Python 3.8+ required\n")
        return False


def check_packages():
    """Check required packages."""
    print("📌 Package Check")
    required = ['google.generativeai', 'dotenv']
    failed = []
    
    for package in required:
        try:
            __import__(package)
            print(f"   ✓ {package}")
        except ImportError:
            print(f"   ✗ {package} - NOT INSTALLED")
            failed.append(package)
    
    if failed:
        print(f"\n   Install with: pip install {' '.join(failed)}\n")
        return False
    print()
    return True


def check_env_file():
    """Check .env file."""
    print("📌 Environment File Check")
    env_file = Path(__file__).parent / ".env"
    
    if not env_file.exists():
        print(f"   ✗ .env not found at {env_file}")
        print(f"   → Create from template: cp .env.template .env\n")
        return False
    
    print(f"   ✓ .env found")
    
    # Check required variables
    required_vars = [
        'DISCORD_DUMP_PATH',
        'DISCORD_PID',
        'GEMINI_API_KEY',
    ]
    
    env_vars = {}
    with open(env_file, 'r') as f:
        for line in f:
            if '=' in line and not line.startswith('#'):
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip()
    
    all_set = True
    for var in required_vars:
        if var in env_vars and env_vars[var]:
            value = env_vars[var]
            if 'KEY' in var or 'API' in var:
                value = value[:10] + '***'
            print(f"   ✓ {var} = {value}")
        else:
            print(f"   ✗ {var} - NOT SET")
            all_set = False
    
    print()
    return all_set


def check_dump_file():
    """Check dump file accessibility."""
    print("📌 Dump File Check")
    
    try:
        dump_path = os.environ.get('DISCORD_DUMP_PATH')
        if not dump_path:
            print("   ✗ DISCORD_DUMP_PATH not set\n")
            return False
        
        dump_file = Path(dump_path)
        if not dump_file.exists():
            print(f"   ✗ File not found: {dump_path}\n")
            return False
        
        size_gb = dump_file.stat().st_size / (1024**3)
        print(f"   ✓ Dump file found")
        print(f"   ✓ Size: {size_gb:.2f} GB")
        print(f"   ✓ Path: {dump_path}\n")
        return True
    except Exception as e:
        print(f"   ✗ Error: {e}\n")
        return False


def check_output_dir():
    """Check output directory."""
    print("📌 Output Directory Check")
    
    output_dir = Path(__file__).parent / "output_discord"
    if not output_dir.exists():
        print(f"   Creating: {output_dir}")
        output_dir.mkdir(parents=True, exist_ok=True)
    
    print(f"   ✓ Output directory: {output_dir}\n")
    return True


def check_api_key():
    """Check API key validity (basic check)."""
    print("📌 API Key Check")
    
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("   ✗ GEMINI_API_KEY not set\n")
        return False
    
    if len(api_key) < 20:
        print("   ✗ API key seems too short\n")
        return False
    
    print(f"   ✓ API key format OK (length: {len(api_key)})")
    print(f"   → Actual validation happens during first API call\n")
    return True


def main():
    """Run all diagnostics."""
    print("\n")
    print("╔════════════════════════════════════════════════════════════════╗")
    print("║  Discord-Weaver Environment Diagnostic                         ║")
    print("╚════════════════════════════════════════════════════════════════╝")
    print()
    
    # Load .env
    env_file = Path(__file__).parent / ".env"
    if env_file.exists():
        with open(env_file) as f:
            for line in f:
                if not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    os.environ[key.strip()] = value.strip()
    
    results = {
        'Python': check_python_version(),
        'Packages': check_packages(),
        'Env File': check_env_file(),
        'API Key': check_api_key(),
        'Dump File': check_dump_file(),
        'Output Dir': check_output_dir(),
    }
    
    # Summary
    print("╔════════════════════════════════════════════════════════════════╗")
    print("║  Summary                                                       ║")
    print("╚════════════════════════════════════════════════════════════════╝")
    print()
    
    for check, result in results.items():
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"  {check:20} {status}")
    
    print()
    
    all_pass = all(results.values())
    if all_pass:
        print("✓ All checks passed! Ready to run Discord-Weaver")
        print()
        print("Next steps:")
        print("  1. ./run_pipeline.sh D:\\discord.raw 352 restore")
        print("  2. Check output_discord/ for results")
    else:
        print("✗ Some checks failed. Fix issues above and try again.")
    
    print()
    return 0 if all_pass else 1


if __name__ == "__main__":
    sys.exit(main())
