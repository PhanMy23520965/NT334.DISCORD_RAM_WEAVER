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
        dump_path = os.environ.get('DISCORD_DUMP_PATH') or os.environ.get('RAM_WEAVER_DUMP_PATH')
        if not dump_path:
            print("   ✗ Dump path not set (checked DISCORD_DUMP_PATH and RAM_WEAVER_DUMP_PATH)\n")
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


def check_volatility():
    """Check Volatility 3 path."""
    print("📌 Volatility Check")
    vol_path = os.environ.get('DISCORD_VOL_PATH') or os.environ.get('RAM_WEAVER_VOL_PATH')
    
    if not vol_path:
        print("   ✗ Volatility path not set\n")
        return False
    
    vol_file = Path(vol_path)
    if vol_file.exists():
        print(f"   ✓ Volatility found: {vol_path}")
        try:
            # Simple version check
            process = subprocess.run([vol_path, "--version"], capture_output=True, text=True)
            if process.returncode == 0:
                print(f"   ✓ {process.stdout.strip()}")
            return True
        except Exception:
            print("   ⚠ Found but failed to execute (check permissions)")
            return True
    else:
        print(f"   ✗ Volatility NOT found at: {vol_path}\n")
        return False


def check_api_key():
    """Check API key validity (basic check)."""
    print("API Key Check")
    
    api_key = os.environ.get('GEMINI_API_KEY')
    if not api_key:
        print("   - GEMINI_API_KEY not set\n")
        return False
    
    if len(api_key) < 20:
        print("   - API key seems too short\n")
        return False
    
    print(f"   + API key format OK")
    return True


def main():
    """Run all diagnostics."""
    print("\n")
    print("+" + "-"*64 + "+")
    print("|  Discord-Weaver Environment Diagnostic                         |")
    print("+" + "-"*64 + "+")
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
        'Volatility': check_volatility(),
        'API Key': check_api_key(),
        'Dump File': check_dump_file(),
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
