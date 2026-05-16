#!/usr/bin/env python
"""Dump Inspector — Diagnostic tool to examine Discord JSON patterns in memory dumps.

Searches for known Discord strings and prints surrounding context to help
calibrate regex patterns for the AMC pipeline.

Usage:
    python -m amc.dump_inspector <dmp_file> [--search "custom string"]
"""

from __future__ import annotations

import os
import sys
import re
import json
from pathlib import Path
from typing import List, Tuple


# Known strings we expect to find in a Discord memory dump
SEARCH_TERMS = [
    b'"content"',
    b'"username"',
    b'"channel_id"',
    b'"global_name"',
    b'"author"',
    b'"nonce"',
    b'"timestamp"',
    b'"guild_id"',
]

# Specific message content we know exists (from previous output)
KNOWN_MESSAGES = [
    b'do you like dance',
    b'Bruce Lee',
    b'cha cha dancer',
    b'myphan4605',
    b'Asamai',
]


def scan_for_patterns(filepath: str, context_size: int = 1500) -> dict:
    """Scan a dump file for Discord-related patterns and print context."""
    
    file_size = os.path.getsize(filepath)
    print(f"\n{'='*70}")
    print(f"Dump Inspector — Analyzing: {filepath}")
    print(f"File size: {file_size:,} bytes ({file_size / (1024*1024):.1f} MB)")
    print(f"{'='*70}\n")
    
    results = {
        'file': filepath,
        'size': file_size,
        'keyword_counts': {},
        'message_samples': [],
        'json_patterns_found': [],
    }
    
    # Read file in chunks for keyword counting
    chunk_size = 10 * 1024 * 1024  # 10MB
    
    print("[1/3] Counting Discord keywords...")
    keyword_counts = {}
    with open(filepath, 'rb') as f:
        offset = 0
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            for term in SEARCH_TERMS:
                count = chunk.count(term)
                keyword_counts[term.decode('ascii', errors='ignore')] = \
                    keyword_counts.get(term.decode('ascii', errors='ignore'), 0) + count
            offset += len(chunk)
            pct = min(100, (offset * 100) // file_size)
            print(f"  {pct}% ({offset // (1024*1024)}/{file_size // (1024*1024)} MB)", end='\r')
    
    print(f"\n\nKeyword frequencies:")
    for kw, count in sorted(keyword_counts.items(), key=lambda x: -x[1]):
        print(f"  {kw:30s} : {count:,}")
    results['keyword_counts'] = keyword_counts
    
    # Search for known messages and print context
    print(f"\n[2/3] Searching for known message content...")
    with open(filepath, 'rb') as f:
        data = f.read()
    
    for term in KNOWN_MESSAGES:
        positions = []
        start = 0
        while True:
            pos = data.find(term, start)
            if pos == -1:
                break
            positions.append(pos)
            start = pos + 1
        
        print(f"\n  '{term.decode('utf-8', errors='ignore')}' found {len(positions)} times")
        
        # Show first 3 occurrences with context
        for i, pos in enumerate(positions[:3]):
            ctx_start = max(0, pos - context_size)
            ctx_end = min(len(data), pos + len(term) + context_size)
            context = data[ctx_start:ctx_end]
            
            # Decode for display
            text = context.decode('utf-8', errors='replace')
            # Clean up non-printable chars for display
            clean = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '·', text)
            
            print(f"\n  --- Occurrence {i+1} at offset 0x{pos:X} ---")
            safe_text = clean[:500].encode('ascii', errors='replace').decode('ascii')
            print(f"  {safe_text}")
            print(f"  [...{len(clean)} chars total...]")
            
            # Try to extract JSON around this position
            json_matches = extract_json_around(text)
            if json_matches:
                print(f"  → Found {len(json_matches)} JSON fragments:")
                for j, jm in enumerate(json_matches[:3]):
                    print(f"    JSON[{j}]: {jm[:200]}...")
                results['json_patterns_found'].extend(json_matches[:3])
    
    # Regex pattern analysis  
    print(f"\n[3/3] Testing regex patterns on dump...")
    text_full = data.decode('utf-8', errors='ignore')
    
    patterns = {
        'outbound_msg': r'"content"\s*:\s*"([^"]{1,500})".{0,200}?"nonce"\s*:\s*"(\d{15,25})"',
        'api_msg': r'"username"\s*:\s*"([^"]+)".{0,500}?"content"\s*:\s*"([^"]*)"',
        'reverse_msg': r'"content"\s*:\s*"([^"]+)".{0,500}?"username"\s*:\s*"([^"]+)"',
        'author_block': r'"author"\s*:\s*\{[^}]*"username"\s*:\s*"([^"]+)"[^}]*\}',
        'global_name': r'"global_name"\s*:\s*"([^"]+)"',
        'channel_id': r'"channel_id"\s*:\s*"(\d{15,25})"',
        'timestamp_iso': r'"timestamp"\s*:\s*"(\d{4}-\d{2}-\d{2}T[^"]+)"',
        'id_field': r'"id"\s*:\s*"(\d{15,25})"',
    }
    
    for name, pattern in patterns.items():
        matches = re.findall(pattern, text_full, re.DOTALL)
        unique = set(matches) if matches else set()
        print(f"  {name:20s}: {len(matches):5d} matches, {len(unique):4d} unique")
        
        if unique and len(list(unique)[0]) < 200:
            for sample in list(unique)[:5]:
                if isinstance(sample, tuple):
                    print(f"    → {' | '.join(str(s)[:80] for s in sample)}")
                else:
                    print(f"    → {str(sample)[:100]}")
    
    results['message_samples'] = list(set(
        re.findall(r'"content"\s*:\s*"([^"]{2,500})"', text_full)
    ))
    
    # Filter out noise content
    real_messages = [
        m for m in results['message_samples']
        if not any(noise in m for noise in [
            'preloaded using link preload',
            'ResizeObserver',
            'MessageQueue',
            'window.blur',
            'window.focus',
            'browser-window',
            'woff2',
            '.js:',
            'webpack',
        ])
        and len(m) > 1
        and len(m) < 500
    ]
    
    print(f"\n{'='*70}")
    print(f"SUMMARY")
    print(f"{'='*70}")
    print(f"Total 'content' values found: {len(results['message_samples'])}")
    print(f"After noise filtering:         {len(real_messages)}")
    print(f"\nReal message samples:")
    for msg in real_messages[:30]:
        print(f"  → {msg[:120]}")
    
    return results


def extract_json_around(text: str) -> List[str]:
    """Try to extract JSON objects from text around a position."""
    results = []
    for m in re.finditer(r'\{[^{}]{10,2000}\}', text):
        try:
            obj = json.loads(m.group())
            results.append(json.dumps(obj, ensure_ascii=False))
        except json.JSONDecodeError:
            pass
    return results


def main():
    if len(sys.argv) < 2:
        print("Usage: python -m amc.dump_inspector <dmp_file>")
        print("Example: python -m amc.dump_inspector vad_dumps/pid_6612/pid.6612.dmp")
        sys.exit(1)
    
    filepath = sys.argv[1]
    if not os.path.exists(filepath):
        print(f"Error: File not found: {filepath}")
        sys.exit(1)
    
    results = scan_for_patterns(filepath)
    
    # Save results
    output_file = Path("output_discord") / "dump_inspection_report.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    # Convert results to serializable format
    serializable = {
        'file': results['file'],
        'size': results['size'],
        'keyword_counts': results['keyword_counts'],
        'real_messages_found': len([
            m for m in results['message_samples']
            if not any(n in m for n in ['preloaded', 'ResizeObserver', 'MessageQueue', 'woff2'])
            and len(m) > 1
        ]),
        'message_samples': results['message_samples'][:50],
    }
    
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(serializable, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Report saved: {output_file}")


if __name__ == "__main__":
    main()
