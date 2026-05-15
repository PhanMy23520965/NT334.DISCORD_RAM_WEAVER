#!/usr/bin/env python
"""CLI entry point for Stage 2 - LLM Query & Restoration (Discord).

Sub-commands:
    restore     – Task A: Restore partial/corrupted Discord messages
    query       – Task B: Execute forensic query on extracted data
    interactive – Task B: Interactive query REPL
    timeline    – Analyze message timeline
    users       – Analyze user behavior
    sentiment   – Analyze message sentiment

Usage:
    python llm_runner.py restore <chunks_file>
    python llm_runner.py query <chunks_file> "<question>"
    python llm_runner.py interactive <chunks_file>
    python llm_runner.py timeline <chunks_file>
"""

from __future__ import annotations

import logging
import os
import sys
import json
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config import LLMConfig
from llm.client import GeminiClient
from llm.restorer import DiscordMessageRestorer
from llm.query_engine import DiscordQueryEngine


def _load_dotenv(env_file: Path) -> None:
    """Load environment variables from .env file."""
    if not env_file.is_file():
        return
    for line in env_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ[key.strip()] = value.strip().strip('\'"')


def _setup_logging():
    """Setup logging."""
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
    )


def load_chunks(chunks_file: str) -> dict:
    """Load extracted chunks from file."""
    chunks_path = Path(chunks_file)
    
    if not chunks_path.exists():
        print(f"Error: Chunks file not found: {chunks_file}")
        sys.exit(1)
    
    try:
        if chunks_file.endswith('.json'):
            with open(chunks_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # Parse text format
            return _parse_text_chunks(chunks_path)
    except Exception as e:
        print(f"Error loading chunks: {e}")
        sys.exit(1)


def _parse_text_chunks(chunks_path: Path) -> dict:
    """Parse text-format chunks file."""
    chunks = {'messages': [], 'user_data': [], 'metadata': []}
    
    current_section = None
    
    with open(chunks_path, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            
            if 'Messages' in line:
                current_section = 'messages'
            elif 'User Data' in line:
                current_section = 'user_data'
            elif 'Metadata' in line:
                current_section = 'metadata'
            elif line.startswith('{') and current_section:
                try:
                    obj = json.loads(line)
                    chunks[current_section].append(obj)
                except json.JSONDecodeError:
                    pass
    
    return chunks


def cmd_restore(chunks_file: str):
    """Restore corrupted Discord messages."""
    print("=" * 70)
    print("Stage 2: Restore - Discord Message Restoration")
    print("=" * 70)
    
    config = LLMConfig()
    if not config.api_key:
        print("Error: GEMINI_API_KEY not set")
        sys.exit(1)
    
    print("[1/2] Loading extracted chunks...")
    chunks = load_chunks(chunks_file)
    print(f"      Loaded {len(chunks.get('messages', []))} messages")
    
    print("[2/2] Restoring messages...")
    client = GeminiClient(config.api_key, config.model_name, config.temperature, config.max_tokens)
    restorer = DiscordMessageRestorer(client)
    
    restored = restorer.restore_messages(chunks.get('messages', []))
    print(f"      Restored {len([m for m in restored if m.get('restored')])} messages")
    
    # Save results
    output_dir = Path("output_discord")
    output_dir.mkdir(parents=True, exist_ok=True)
    output_file = output_dir / "restored_messages.json"
    
    # Deduplicate final results for cleaner output
    unique_restored = []
    seen_keys = set()
    for m in restored:
        # Use content + nonce or content + id as a unique key
        content = m.get('content', '')
        nonce = m.get('nonce', '')
        msg_id = m.get('id', '')
        key = f"{content}_{nonce}_{msg_id}"
        if key not in seen_keys:
            seen_keys.add(key)
            unique_restored.append(m)
            
    with open(output_file, 'w', encoding='utf-8') as f:
        json.dump(unique_restored, f, ensure_ascii=False, indent=2)
    
    # Save a human-readable text version
    txt_output = output_dir / "restored_messages_readable.txt"
    with open(txt_output, 'w', encoding='utf-8') as f:
        f.write("=" * 80 + "\n")
        f.write("DISCORD FORENSIC REPORT: RESTORED MESSAGES\n")
        f.write("=" * 80 + "\n\n")
        
        for msg in unique_restored:
            author_data = msg.get('author', {})
            if isinstance(author_data, dict):
                author = author_data.get('global_name') or author_data.get('username') or "Unknown"
            else:
                author = author_data or "Unknown"
                
            timestamp = msg.get('timestamp', 'Unknown')
            content = msg.get('content', '')
            channel = msg.get('channel_id') or msg.get('channelId') or "Unknown"
            
            f.write(f"TIMESTAMP : {timestamp}\n")
            f.write(f"AUTHOR    : {author}\n")
            f.write(f"CHANNEL   : {channel}\n")
            f.write(f"CONTENT   :\n  {content}\n")
            f.write("-" * 80 + "\n")
            
    print(f"✓ Restoration complete. JSON: {output_file}, Text: {txt_output}")


def cmd_query(chunks_file: str, question: str):
    """Execute forensic query on Discord data."""
    print("=" * 70)
    print("Stage 2: Query - Discord Forensic Analysis")
    print("=" * 70)
    
    config = LLMConfig()
    if not config.api_key:
        print("Error: GEMINI_API_KEY not set")
        sys.exit(1)
    
    print("[1/2] Loading extracted chunks...")
    chunks = load_chunks(chunks_file)
    
    print("[2/2] Executing query...")
    client = GeminiClient(config.api_key, config.model_name, config.temperature, config.max_tokens)
    engine = DiscordQueryEngine(client)
    
    # Prepare context
    context = json.dumps(chunks, ensure_ascii=False, indent=2)[:10000]
    
    response = engine.query(context, question)
    
    print("\n" + "=" * 70)
    print("Query Response:")
    print("=" * 70)
    print(response)
    
    # Save results
    output_file = Path("output_discord") / "query_response.txt"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_file, 'w', encoding='utf-8') as f:
        f.write(f"Question: {question}\n\n")
        f.write(f"Response:\n{response}\n")


def cmd_interactive(chunks_file: str):
    """Interactive query REPL."""
    print("=" * 70)
    print("Stage 2: Interactive - Discord Forensic Query REPL")
    print("=" * 70)
    
    config = LLMConfig()
    if not config.api_key:
        print("Error: GEMINI_API_KEY not set")
        sys.exit(1)
    
    print("[1/2] Loading extracted chunks...")
    chunks = load_chunks(chunks_file)
    
    client = GeminiClient(config.api_key, config.model_name, config.temperature, config.max_tokens)
    engine = DiscordQueryEngine(client)
    context = json.dumps(chunks, ensure_ascii=False, indent=2)[:10000]
    
    print("[2/2] Starting interactive session...")
    print("Type 'exit' to quit, 'help' for commands\n")
    
    while True:
        try:
            question = input("Query> ").strip()
            
            if question.lower() == 'exit':
                break
            elif question.lower() == 'help':
                print("Available commands:")
                print("  timeline  - Analyze message timeline")
                print("  users     - Analyze user behavior")
                print("  sentiment - Analyze message sentiment")
                print("  exit      - Quit")
                continue
            elif question.lower() == 'timeline':
                response = engine.timeline_analysis(chunks.get('messages', []))
            elif question.lower() == 'users':
                response = engine.user_analysis(chunks.get('user_data', []), chunks.get('messages', []))
            elif question.lower() == 'sentiment':
                response = engine.sentiment_analysis(chunks.get('messages', []))
            else:
                response = engine.query(context, question)
            
            print(f"\nResponse:\n{response}\n")
        
        except KeyboardInterrupt:
            print("\nInterrupted")
            break
        except Exception as e:
            print(f"Error: {e}")


def main():
    """Main entry point."""
    _setup_logging()
    
    # Load .env if exists
    env_file = Path(__file__).parent.parent / ".env"
    _load_dotenv(env_file)
    
    if len(sys.argv) < 2:
        print("Usage: python llm_runner.py <command> [args]")
        print("Commands: restore, query, interactive, timeline, users, sentiment")
        sys.exit(1)
    
    command = sys.argv[1]
    
    if command == "restore":
        if len(sys.argv) < 3:
            print("Usage: python llm_runner.py restore <chunks_file>")
            sys.exit(1)
        cmd_restore(sys.argv[2])
    
    elif command == "query":
        if len(sys.argv) < 4:
            print("Usage: python llm_runner.py query <chunks_file> \"<question>\"")
            sys.exit(1)
        cmd_query(sys.argv[2], sys.argv[3])
    
    elif command == "interactive":
        if len(sys.argv) < 3:
            print("Usage: python llm_runner.py interactive <chunks_file>")
            sys.exit(1)
        cmd_interactive(sys.argv[2])
    
    else:
        print(f"Unknown command: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
