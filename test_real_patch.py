#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Real patch test for ReviewEngine.

Tests with actual kernel commit e0367ffa5955 from Juri's tree.
"""
import subprocess
import sys
import os

# Add src to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from b4.llm.ollama import OllamaProvider
from b4.mcp_client import SemcodeMCPClient
from b4.review_prompts import ReviewPromptsLoader
from b4.review import ReviewEngine


def get_commit_info(commit_hash: str, kernel_dir: str) -> tuple[str, dict]:
    """Get commit diff and metadata from git."""
    # Get diff
    diff_result = subprocess.run(
        ['git', 'show', '--format=', commit_hash],
        cwd=kernel_dir,
        capture_output=True,
        text=True
    )
    if diff_result.returncode != 0:
        raise RuntimeError(f"Failed to get diff: {diff_result.stderr}")

    # Get commit message
    msg_result = subprocess.run(
        ['git', 'show', '--format=%s%n%n%b', '--no-patch', commit_hash],
        cwd=kernel_dir,
        capture_output=True,
        text=True
    )
    if msg_result.returncode != 0:
        raise RuntimeError(f"Failed to get commit message: {msg_result.stderr}")

    # Parse metadata
    lines = msg_result.stdout.split('\n')
    subject = lines[0] if lines else 'Unknown'
    commit_message = msg_result.stdout

    metadata = {
        'subject': subject,
        'commit_message': commit_message,
        'commit': commit_hash[:12]
    }

    return diff_result.stdout, metadata


def main():
    print("=" * 70)
    print("REAL PATCH REVIEW TEST")
    print("=" * 70)

    # Configuration
    commit_hash = 'e0367ffa5955'
    kernel_dir = '/home/jlelli/Work/kernel/linux'
    semcode_binary = '/home/jlelli/Work/kernel/semcode/target/release/semcode-mcp'
    prompts_dir = os.path.expanduser('~/Work/kernel/review-prompts')

    print(f"\nCommit: {commit_hash}")
    print(f"Kernel: {kernel_dir}")
    print(f"Prompts: {prompts_dir}")

    # Change to kernel directory so semcode can find .semcode.db
    print(f"\n⚙️  Changing to kernel directory...")
    original_dir = os.getcwd()
    os.chdir(kernel_dir)
    print(f"   ✅ Now in: {os.getcwd()}")

    # Get patch
    print("\n1. Fetching commit from git...")
    diff, metadata = get_commit_info(commit_hash, kernel_dir)
    print(f"   ✅ Subject: {metadata['subject']}")
    print(f"   ✅ Diff size: {len(diff)} chars")

    # Initialize components
    print("\n2. Initializing Ollama provider...")
    ollama = OllamaProvider({
        'url': 'http://localhost:11434',
        'model': 'qwen2.5-coder:1.5b',  # Smaller/faster model for testing
        'timeout': 300,  # Should be much faster
        'num_ctx': 16384  # Increase context window to avoid truncation
    })
    print(f"   ✅ Provider: {ollama.name} / {ollama.model}")
    print(f"   ✅ Context window: 16384 tokens")

    print("\n3. Initializing MCP client...")
    mcp = SemcodeMCPClient(
        semcode_binary=semcode_binary,
        kernel_dir=kernel_dir
    )
    mcp.connect()
    tools = mcp.get_tools()
    print(f"   ✅ Connected with {len(tools)} tools available")

    print("\n4. Loading review prompts...")
    prompts = ReviewPromptsLoader(prompts_dir)
    print(f"   ✅ Loaded from: {prompts.prompts_dir}")

    # Detect subsystems
    subsystems = prompts.detect_subsystems(diff)
    print(f"   ✅ Detected subsystems: {subsystems}")

    print("\n5. Creating ReviewEngine...")
    # Enable debug logging to see everything
    import logging
    logging.basicConfig(level=logging.INFO, format='%(levelname)s: %(message)s')

    engine = ReviewEngine(ollama, mcp, prompts, verbose=True, dump_conversation=True, stream=True)
    print(f"   ✅ Engine initialized with {len(engine.tools)} tools")
    print(f"   ℹ️  Verbose mode: ON + Full conversation logging + Streaming enabled")

    # Build prompts (just to see sizes)
    system_prompt = engine.build_system_prompt(diff)
    user_prompt = engine.build_user_prompt(diff, metadata)
    print(f"\n6. Prompt statistics:")
    print(f"   - System prompt: {len(system_prompt):,} chars")
    print(f"   - User prompt: {len(user_prompt):,} chars")
    print(f"   - Total context: {len(system_prompt) + len(user_prompt):,} chars")

    # Run the review!
    print("\n7. Starting autonomous review...")
    print("   (This may take several minutes - LLM will call tools as needed)")
    print("   " + "-" * 66)

    result = engine.review_patch(diff, metadata)

    # Display results
    print("\n" + "=" * 70)
    print("REVIEW RESULTS")
    print("=" * 70)

    print(f"\n📊 Statistics:")
    print(f"   - Regressions found: {result.regressions_found}")
    print(f"   - Patterns triggered: {', '.join(result.patterns_triggered) if result.patterns_triggered else 'none'}")
    print(f"   - Tokens used: {result.tokens_used:,}")
    print(f"   - Analysis time: {result.analysis_time:.1f}s")

    print(f"\n📝 Full Review Text:")
    print("-" * 70)
    print(result.review_text)
    print("-" * 70)

    # Cleanup
    mcp.disconnect()

    # Restore original directory
    os.chdir(original_dir)

    print("\n✅ Test complete!")


if __name__ == '__main__':
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
