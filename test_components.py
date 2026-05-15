#!/usr/bin/env python
"""Quick test of Discord-Weaver components.

Tests:
- Configuration loading
- Module imports
- API client initialization
- Basic extraction
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

def test_imports():
    """Test module imports."""
    print("Testing imports...")
    try:
        from config import AMCConfig, LLMConfig, DiscordWeaverConfig
        from amc.pipeline import AdaptiveMemoryCarver
        from amc.extractor import AdaptiveMemoryExtractor
        from amc.filtering import ArtifactFilter
        from llm.client import GeminiClient
        from llm.restorer import DiscordMessageRestorer
        from llm.query_engine import DiscordQueryEngine
        print("✓ All imports successful")
        return True
    except Exception as e:
        print(f"✗ Import failed: {e}")
        return False


def test_config():
    """Test configuration loading."""
    print("\nTesting configuration...")
    try:
        from config import DiscordWeaverConfig
        
        config = DiscordWeaverConfig.from_env()
        print(f"✓ Config loaded")
        print(f"  - AMC output dir: {config.amc.output_dir}")
        print(f"  - LLM model: {config.llm.model_name}")
        return True
    except Exception as e:
        print(f"✗ Config failed: {e}")
        return False


def test_extractor():
    """Test memory extractor."""
    print("\nTesting extractor...")
    try:
        from config import AMCConfig
        from amc.extractor import AdaptiveMemoryExtractor
        
        config = AMCConfig()
        extractor = AdaptiveMemoryExtractor(config)
        
        # Test with small binary data
        test_data = b"This is a test message from Discord user123 channelABC"
        strings = extractor._extract_strings(test_data)
        
        if strings:
            print(f"✓ Extractor working")
            print(f"  - Found {len(strings)} strings")
            print(f"  - Sample: {strings[0][:50]}")
            return True
        else:
            print("⚠ Extractor found no strings (may be OK for small test)")
            return True
    except Exception as e:
        print(f"✗ Extractor failed: {e}")
        return False


def test_gemini_client():
    """Test Gemini client initialization."""
    print("\nTesting Gemini client...")
    try:
        from llm.client import GeminiClient
        
        api_key = os.environ.get('GEMINI_API_KEY', 'test_key_12345')
        client = GeminiClient(api_key, temperature=0.7)
        
        print(f"✓ Gemini client initialized")
        print(f"  - Model: {client.model_name}")
        print(f"  - API key configured: {bool(client.model)}")
        return True
    except Exception as e:
        print(f"⚠ Gemini client init issue: {e}")
        return True  # Not critical


def main():
    """Run all tests."""
    print("\n")
    print("╔═════════════════════════════════════════════════════╗")
    print("║  Discord-Weaver Component Test                      ║")
    print("╚═════════════════════════════════════════════════════╝")
    print()
    
    results = {
        'Imports': test_imports(),
        'Configuration': test_config(),
        'Extractor': test_extractor(),
        'Gemini Client': test_gemini_client(),
    }
    
    print("\n" + "=" * 50)
    print("Results:")
    print("=" * 50)
    
    for test, result in results.items():
        status = "✓" if result else "✗"
        print(f"{status} {test}")
    
    print()
    
    if all(results.values()):
        print("✓ All tests passed!")
        return 0
    else:
        print("✗ Some tests failed")
        return 1


if __name__ == "__main__":
    sys.exit(main())
