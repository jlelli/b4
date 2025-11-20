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

from b4.llm.gemini import GeminiProvider
from b4.mcp_client import SemcodeMCPClient
from b4.review_prompts import ReviewPromptsLoader
from b4.review import ReviewEngine
from b4.review_formatter import format_inline, format_markdown, format_json


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
    print("\n2. Initializing Gemini provider...")
    gemini = GeminiProvider({
        'model': 'gemini-2.5-flash',  # Stable Gemini 2.5 Flash
        'temperature': 0.1,
        'timeout': 300
    })
    print(f"   ✅ Provider: {gemini.name} / {gemini.model}")

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
    # Set logging to WARNING to reduce noise
    import logging
    logging.basicConfig(level=logging.WARNING, format='%(levelname)s: %(message)s')

    # Open file for streaming output (unbuffered)
    stream_file = open('review-stream.log', 'w', buffering=1)  # Line buffering

    engine = ReviewEngine(
        gemini, mcp, prompts,
        verbose=False,
        dump_conversation=False,
        stream=True,
        stream_output=stream_file
    )
    print(f"   ✅ Engine initialized with {len(engine.tools)} tools")
    print(f"   ℹ️  Streaming output will be written to review-stream.log")

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

    # Close stream file
    stream_file.close()

    # Display results
    print("\n" + "=" * 70)
    print("REVIEW RESULTS")
    print("=" * 70)

    print(f"\n📊 Statistics:")
    print(f"   - Regressions found: {result.regressions_found}")
    print(f"   - Patterns triggered: {', '.join(result.patterns_triggered) if result.patterns_triggered else 'none'}")
    print(f"   - Tokens used: {result.tokens_used:,}")
    print(f"   - Analysis time: {result.analysis_time:.1f}s")

    # Calculate tokens per second
    if result.analysis_time > 0:
        tokens_per_sec = result.tokens_used / result.analysis_time
        print(f"   - Throughput: {tokens_per_sec:.1f} tokens/sec")

    print(f"\n📝 Raw Review Text:")
    print("-" * 70)
    print(result.review_text)
    print("-" * 70)

    # Test all three output formatters
    print("\n" + "=" * 70)
    print("OUTPUT FORMATTERS TEST")
    print("=" * 70)

    print("\n8. Testing inline format (email-style)...")
    inline_output = format_inline(result)
    inline_file = 'review-inline.txt'
    with open(inline_file, 'w') as f:
        f.write(inline_output)
    print(f"   ✅ Generated {inline_file} ({len(inline_output):,} chars)")
    print(f"   Preview (first 500 chars):")
    print("   " + "\n   ".join(inline_output[:500].split('\n')))

    print("\n9. Testing markdown format...")
    markdown_output = format_markdown(result)
    markdown_file = 'review-report.md'
    with open(markdown_file, 'w') as f:
        f.write(markdown_output)
    print(f"   ✅ Generated {markdown_file} ({len(markdown_output):,} chars)")

    print("\n10. Testing JSON format...")
    json_output = format_json(result, pretty=True)
    json_file = 'review-result.json'
    with open(json_file, 'w') as f:
        f.write(json_output)
    print(f"   ✅ Generated {json_file} ({len(json_output):,} chars)")

    # Parse JSON to verify structure
    import json
    parsed = json.loads(json_output)
    print(f"   ✅ JSON validation: {len(parsed)} top-level keys")
    print(f"      - review.regressions_found: {parsed['review']['regressions_found']}")
    print(f"      - review.patterns_triggered: {len(parsed['review']['patterns_triggered'])} patterns")

    # Performance summary
    print("\n" + "=" * 70)
    print("PERFORMANCE BENCHMARK")
    print("=" * 70)
    print(f"\n📈 Review Performance:")
    print(f"   - Total time: {result.analysis_time:.1f}s ({result.analysis_time/60:.1f} minutes)")
    print(f"   - Total tokens: {result.tokens_used:,}")
    print(f"   - Throughput: {tokens_per_sec:.1f} tokens/sec")
    print(f"   - Context size: {len(system_prompt) + len(user_prompt):,} chars")

    print(f"\n📦 Output Files Generated:")
    print(f"   - review-stream.log - LLM streaming output")
    print(f"   - {inline_file} - Email-style review")
    print(f"   - {markdown_file} - Markdown report")
    print(f"   - {json_file} - JSON data")

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
