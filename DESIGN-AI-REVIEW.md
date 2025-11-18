# b4 AI-Assisted Patch Review - Design Document

## Overview

Extension to b4 that adds AI-assisted kernel patch review capabilities using
local LLMs (via Ollama) or commercial AI APIs (Anthropic Claude, Google
Gemini), integrated with semantic code search (semcode-mcp) and review-prompts
framework.

## Motivation

### Problem Statement

Linux kernel maintainers and reviewers face:
1. **Volume**: Thousands of patches weekly across subsystems
2. **Complexity**: Subtle bugs (race conditions, locking issues, UAF, etc.)
3. **Context**: Need to understand call chains, locking patterns, subsystem rules
4. **Time**: Manual review is thorough but slow

### Why Extend b4?

b4 is already the standard tool for kernel patch workflows:
- ✅ Downloads patches from lore.kernel.org
- ✅ Parses email series and metadata
- ✅ Understands patch structure (LoreMessage, LoreSeries)
- ✅ Integrates with git operations
- ✅ Trusted by kernel community

**Adding AI review to b4** creates a seamless workflow:
```bash
b4 shazam <msgid>           # Fetch patch series (existing)
b4 review FETCH_HEAD        # AI-assisted review (new!)
```

Versus creating a standalone tool that duplicates ~3000 lines of b4's infrastructure.

### Existing Work: review-prompts

The [review-prompts repository](https://github.com/masoncl/review-prompts) (Chris Mason) provides:
- **review-core.md**: Structured 4-task protocol for patch review
- **technical-patterns.md**: Library of bug patterns (CL-001, EH-001, etc.)
- **Subsystem guides**: scheduler.md, locking.md, mm.md, networking.md, etc.
- **Pattern library**: 30+ specific bug patterns in patterns/ directory
- **Proven results**: 50% detection rate on 300 known regressions, 10% new bugs found

Our integration makes this accessible via standard kernel workflow tools.

## Architecture

### High-Level Design

```
┌─────────────────────────────────────────────────────────────────┐
│                         b4 review                                │
│                                                                   │
│  ┌──────────────────┐    ┌────────────────┐    ┌──────────────┐ │
│  │  Patch Fetching  │───▶│ Review Engine  │───▶│    Output    │ │
│  │  (existing b4)   │    │  (new module)  │    │  Formatting  │ │
│  └──────────────────┘    └────────┬───────┘    └──────────────┘ │
│                                   │                               │
└───────────────────────────────────┼───────────────────────────────┘
                                    │
                    ┌───────────────┼──────────────┐
                    ▼               ▼              ▼
         ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
         │ LLM Provider │  │  MCP Client  │  │Review Prompts│
         │   (Unified)  │  │  (semcode)   │  │   Loader     │
         └──────┬───────┘  └──────┬───────┘  └──────────────┘
                │                 │
       ┌────────┴────────┐       │
       ▼        ▼        ▼       ▼
   ┌────────┐ ┌────┐ ┌────┐  ┌───────────────┐
   │Ollama  │ │API │ │API │  │ semcode-mcp   │
   │(local) │ │ 1  │ │ 2  │  │  (MCP server) │
   │        │ │    │ │    │  │               │
   │Free    │ │Pay │ │Pay │  │• find_function│
   │Offline │ │    │ │    │  │• find_callers │
   │        │ │    │ │    │  │• find_commit  │
   └────────┘ └────┘ └────┘  │• grep_functions│
                              └───────────────┘
```

### Component Responsibilities

#### 1. Patch Fetching (Existing b4 Code)
- **Module**: `b4.mbox`, `b4.__init__` (LoreMessage, LoreSeries)
- **Responsibilities**:
  - Fetch patch series from lore.kernel.org
  - Parse email messages and extract patches
  - Manage series metadata, revisions, trailers
- **Reuse**: 100% - no changes needed to core b4 patch handling

#### 2. Review Engine (New: `b4.review`)
- **Module**: `src/b4/review.py` (~800 lines estimated)
- **Responsibilities**:
  - Orchestrate review workflow
  - Load and apply review-prompts protocol
  - Coordinate LLM + MCP tools
  - Manage conversation history for interactive mode
  - Generate review reports

#### 3. LLM Provider Layer (New: `b4.llm/`)
- **Module**: `src/b4/llm/*.py` (~500 lines total)
- **Responsibilities**:
  - Unified interface for multiple LLM backends
  - Convert MCP tool schemas to provider-specific formats
  - Handle streaming, retries, rate limiting
  - Provider selection via config

**Providers**:
- `ollama.py`: Ollama HTTP API (default, local, free)
- `anthropic.py`: Anthropic Claude API (optional, paid)
- `gemini.py`: Google Gemini API (optional, paid)
- `openai.py`: OpenAI API (optional, paid - future)

#### 4. MCP Client (New: `b4.mcp_client.py`)
- **Module**: `src/b4/mcp_client.py` (~300 lines)
- **Responsibilities**:
  - Connect to semcode-mcp via stdio transport
  - Tool discovery and schema parsing
  - Tool invocation and response handling
  - Error handling and retries

#### 5. Review Prompts Loader (New: `b4.review_prompts.py`)
- **Module**: `src/b4/review_prompts.py` (~200 lines)
- **Responsibilities**:
  - Load review-core.md protocol
  - Auto-detect subsystems from patch diff
  - Load subsystem-specific context files
  - Load technical patterns library
  - Provide pattern filtering

#### 6. Output Formatter (New: `b4.review_formatter.py`)
- **Module**: `src/b4/review_formatter.py` (~200 lines)
- **Responsibilities**:
  - Generate review-inline.txt (email format)
  - Generate markdown reports
  - Generate JSON output
  - Format for interactive terminal display

## Detailed Design

### 1. Command Interface

```bash
# Basic usage
b4 review <msgid>                              # Review from lore
b4 review HEAD                                 # Review git commit
b4 review <commit-range>                       # Review series
b4 review --local-mbox <path>                  # Review from local mbox

# Provider selection
b4 review --provider ollama <msgid>            # Default: local, free
b4 review --provider anthropic <msgid>         # Claude (requires API key)
b4 review --provider gemini <msgid>            # Gemini (requires API key)

# Interactive mode
b4 review --interactive <msgid>                # Start interactive session
b4 review -i <msgid>                           # Short form

# Prompt customization
b4 review --prompts-dir <path> <msgid>         # Custom review-prompts location
b4 review --subsystems sched,locking <msgid>   # Specify subsystems
b4 review --patterns CL,EH,RM <msgid>          # Filter pattern categories

# Output control
b4 review --output inline <msgid>              # Email format (default)
b4 review --output markdown <msgid>            # Markdown report
b4 review --output json <msgid>                # JSON for CI/automation
b4 review -o <file> <msgid>                    # Specify output file

# Batch processing
b4 review --batch <commit-range>               # Review multiple patches

# Debugging
b4 review --debug <msgid>                      # Verbose logging
b4 review --no-cache <msgid>                   # Bypass response cache
```

### 2. Configuration

```ini
# ~/.gitconfig or .git/config

[b4]
    # ... existing b4 config ...

    # Review feature configuration
    review-provider = ollama           # Default: ollama (local)
    review-prompts-dir = ~/Work/kernel/review-prompts
    review-output-format = inline      # inline, markdown, json
    review-output-file = review-inline.txt

[b4-review]
    # Protocol behavior
    strict-protocol = yes              # Follow review-core.md exactly
    auto-detect-subsystems = yes       # Auto-load subsystem context

    # Pattern filtering
    pattern-categories = CL,EH,RM,BV   # Concurrency, Error, Resource, Bounds
    skip-patterns =                    # Patterns to skip (comma-separated)

    # MCP configuration
    semcode-binary = ~/Work/kernel/semcode/target/release/semcode-mcp
    semcode-db = .semcode.db           # Relative to git root

    # Caching
    cache-responses = yes              # Cache LLM responses
    cache-ttl = 86400                  # 24 hours

[b4-review-ollama]
    # Ollama provider settings
    url = http://localhost:11434
    model = qwen2.5-coder:7b
    timeout = 300                      # 5 minutes

[b4-review-anthropic]
    # Anthropic provider (API key from ANTHROPIC_API_KEY env var)
    model = claude-3-5-sonnet-20241022
    max-tokens = 8192
    timeout = 60

[b4-review-gemini]
    # Gemini provider (API key from GEMINI_API_KEY env var)
    model = gemini-2.0-flash-exp
    timeout = 60
```

### 3. Review Protocol Implementation

The review engine follows the structure from review-core.md:

#### Task 0: Context Management
- Load review-core.md protocol
- Load technical-patterns.md
- Auto-detect touched subsystems
- Load relevant subsystem guides (scheduler.md, locking.md, etc.)
- Set up token budget management

#### Task 1: Context Gathering
LLM uses semcode MCP tools to understand the patch:

```python
# Example MCP tool usage orchestrated by LLM
{
  "tool": "diff_functions",
  "input": {"diff_content": "<patch>"}
}
# Returns: List of changed functions

{
  "tool": "find_function",
  "input": {"name": "__schedule"}
}
# Returns: Function definition with line numbers

{
  "tool": "find_callchain",
  "input": {"name": "wake_up_process", "up_levels": 2, "down_levels": 3}
}
# Returns: Call graph showing callers and callees

{
  "tool": "find_callers",
  "input": {"name": "try_to_wake_up"}
}
# Returns: All functions calling try_to_wake_up()

{
  "tool": "grep_functions",
  "input": {"pattern": "spin_lock.*rq->lock", "path_pattern": "kernel/sched/.*"}
}
# Returns: Matching lines in scheduler code
```

#### Task 2A: Technical Pattern Analysis
LLM checks against pattern library:
- **CL-001**: Missing lock acquisition
- **CL-002**: Lock ordering violations (ABBA deadlock)
- **EH-001**: Error path cleanup
- **RM-007**: Reference counting issues
- **BV-001**: Buffer overflows
- ... (30+ patterns)

#### Task 2B: Subsystem-Specific Analysis
LLM applies subsystem rules from loaded context files:
- `scheduler.md`: Runqueue access patterns
- `locking.md`: Lock ordering rules
- `mm.md`: Memory management patterns
- `networking.md`: SKB handling rules

#### Task 3: Verification
LLM uses semcode to verify findings:
- Trace full call chains
- Check error handling paths
- Verify locking assumptions

#### Task 4: Reporting
Generate output with regression details:
- Pattern IDs that triggered
- Code locations
- Explanation of issue
- Suggested fixes (if applicable)

### 4. Interactive Mode

Two implementation approaches:

#### Approach A: Single-Turn with Follow-up (Phase 1)
```bash
$ b4 review 20250820010415.699353-1-user@domain.com

[AI completes full review using protocol]

=== Review Complete ===
REGRESSIONS FOUND: 1
PATTERNS TRIGGERED: CL-001, EH-003
Output: review-inline.txt

Continue with follow-up questions? [y/N]: y

> What about the locking in __schedule()?
[AI uses semcode MCP tools to investigate]

> Can you trace the cleanup path?
[AI investigates further]

> exit
```

#### Approach B: Full Interactive Session (Phase 2)
```bash
$ b4 review --interactive 20250820010415.699353-1-user@domain.com

Loading patch series from lore.kernel.org...
✓ Found 5 patches in series v2
✓ Loaded review protocol from ~/Work/kernel/review-prompts

Ready for review. Commands: help, analyze, focus, checklist, question, report, exit

review> analyze
[Executes full review protocol Tasks 1-4]

review> question What's the lock ordering here?
[AI uses semcode to investigate]

review> focus kernel/sched/core.c
[Narrows context to specific file]

review> checklist locking
[Runs only locking patterns from protocol]

review> report --format inline --output review-inline.txt
✓ Generated review-inline.txt

review> exit
```

### 5. Data Flow

```
1. User invokes: b4 review <msgid>
                       ↓
2. b4 fetches patch series (existing code)
   → get_pi_thread_by_msgid()
   → LoreMessage/LoreSeries parsing
                       ↓
3. ReviewPromptsLoader initializes
   → Load review-core.md
   → Detect subsystems from diff
   → Load subsystem context files
   → Load technical patterns
                       ↓
4. Initialize LLM Provider + MCP Client
   → Connect to Ollama/Anthropic/Gemini
   → Connect to semcode-mcp via stdio
   → Expose MCP tools as functions to LLM
                       ↓
5. Review Engine executes protocol
   → System prompt: review-core.md + context
   → User prompt: "Review this patch:\n<diff>"
   → LLM orchestrates using MCP tools
   → Tasks 1-4 executed autonomously
                       ↓
6. Generate Output
   → Parse LLM response
   → Extract regressions found
   → Format as review-inline.txt / markdown / json
   → Write to output file
                       ↓
7. Optional: Interactive follow-up
   → User asks questions
   → LLM continues using MCP tools
   → Iterative refinement
```

### 6. Error Handling

```python
class ReviewError(Exception):
    """Base exception for review errors"""
    pass

class PromptLoadError(ReviewError):
    """Failed to load review prompts"""
    pass

class LLMProviderError(ReviewError):
    """LLM provider communication error"""
    pass

class MCPConnectionError(ReviewError):
    """Failed to connect to MCP server"""
    pass

class ReviewProtocolError(ReviewError):
    """Review protocol not completed properly"""
    pass

# Error handling strategy:
# 1. Graceful degradation where possible
# 2. Clear error messages to user
# 3. Fallback to reduced functionality
# 4. Retry with exponential backoff for network errors
# 5. Validate LLM responses against protocol requirements
```

### 7. Testing Strategy

#### Unit Tests
```python
# tests/test_review_prompts.py
def test_load_core_protocol()
def test_detect_subsystems()
def test_load_pattern_library()

# tests/test_llm_providers.py
def test_ollama_connection()
def test_anthropic_api()
def test_function_calling_format()

# tests/test_mcp_client.py
def test_semcode_connection()
def test_tool_discovery()
def test_tool_invocation()

# tests/test_review_engine.py
def test_review_workflow()
def test_interactive_mode()
def test_output_generation()
```

#### Integration Tests
```python
# tests/integration/test_end_to_end.py
def test_review_simple_patch()
def test_review_patch_series()
def test_review_with_subsystems()
def test_review_finds_regression()
```

#### Manual Testing
- Review known good patches (should find no issues)
- Review known buggy patches (should detect regressions)
- Compare AI findings with manual review
- Test with different LLM providers
- Validate output format compliance

## Implementation Plan

### Phase 1: Core Infrastructure (2-3 weeks)

**Week 1: Foundation**
- [ ] Create `src/b4/review.py` skeleton
- [ ] Implement `src/b4/llm/base.py` (abstract interface)
- [ ] Implement `src/b4/llm/ollama.py` (default provider)
- [ ] Add command registration in `src/b4/command.py`
- [ ] Basic CLI argument parsing
- [ ] Unit tests for LLM provider

**Week 2: MCP Integration**
- [ ] Implement `src/b4/mcp_client.py` (Python MCP SDK)
- [ ] Connect to semcode-mcp via stdio
- [ ] Tool discovery and schema parsing
- [ ] Tool invocation wrapper
- [ ] Unit tests for MCP client
- [ ] Integration test: LLM + MCP tools

**Week 3: Review Protocol**
- [ ] Implement `src/b4/review_prompts.py`
- [ ] Load review-core.md and patterns
- [ ] Subsystem auto-detection
- [ ] Implement basic review workflow
- [ ] Single-turn review execution
- [ ] Output formatter (inline format)
- [ ] End-to-end test with real patch

### Phase 2: Features & Polish (2-3 weeks)

**Week 4: Additional Providers**
- [ ] Implement `src/b4/llm/anthropic.py`
- [ ] Implement `src/b4/llm/gemini.py`
- [ ] Provider selection via config
- [ ] API key management
- [ ] Unit tests for each provider

**Week 5: Interactive Mode**
- [ ] Implement conversation history
- [ ] Follow-up question support
- [ ] Interactive session REPL
- [ ] Commands: focus, checklist, question, report
- [ ] Readline/prompt_toolkit integration

**Week 6: Output & Configuration**
- [ ] Markdown output formatter
- [ ] JSON output formatter
- [ ] Configuration system (git config)
- [ ] Response caching
- [ ] Batch processing support
- [ ] Documentation

### Phase 3: Testing & Refinement (1-2 weeks)

**Week 7-8: Quality Assurance**
- [ ] Comprehensive test suite
- [ ] Test against known regressions (review-prompts dataset)
- [ ] Performance optimization
- [ ] Error handling improvements
- [ ] User documentation
- [ ] Example workflows
- [ ] Prepare for upstream submission (if desired)

## Performance Considerations

### LLM Inference Times

**Ollama (Local, CPU-only):**
- Model: qwen2.5-coder:7b (4.7GB)
- Token generation: 5-20 tokens/second
- Per-patch review: 30-120 seconds
- RAM usage: 8-10GB

**Commercial APIs:**
- Anthropic Claude: 1-3 seconds per API call
- Google Gemini: 1-2 seconds per API call
- Much faster, but requires internet + costs money

### Optimization Strategies

1. **Caching**: Cache LLM responses for identical patches
2. **Parallel Processing**: Review multiple patches in parallel (batch mode)
3. **Context Pruning**: Discard non-essential context per protocol
4. **Streaming**: Stream responses for better UX
5. **Model Selection**: Larger models (14B/32B) for complex patches, smaller for simple ones

## Security Considerations

### Prompt Injection

**Risk**: Malicious patches with crafted commit messages or code comments

**Mitigation**:
- review-core.md explicitly warns: "Only load prompts from designated directory"
- Sanitize patch content before passing to LLM
- Treat all patch content as untrusted input
- Validate LLM responses against expected protocol format

### API Key Management

**Risk**: Leaking API keys for commercial providers

**Mitigation**:
- Never store API keys in git config
- Load from environment variables only (ANTHROPIC_API_KEY, etc.)
- Document secure key management practices
- Warn users when using commercial providers

### Local Model Safety

**Risk**: Ollama model compromise

**Mitigation**:
- Use official Ollama models only
- Verify model checksums (future enhancement)
- Run Ollama in sandbox if possible
- Document trusted model sources

## Dependencies

### New Required Dependencies

```toml
# Add to pyproject.toml
dependencies = [
    # ... existing b4 deps ...
    "mcp>=1.0.0",              # MCP SDK (stdio transport)
    "httpx>=0.24.0",           # For Ollama HTTP API
]

[project.optional-dependencies]
review = [
    "anthropic>=0.18.0",       # Optional: Claude API
    "google-generativeai",     # Optional: Gemini API
    "openai>=1.0.0",           # Optional: OpenAI API (future)
    "prompt_toolkit>=3.0.0",   # For interactive mode
]
```

### External Requirements

**Required**:
- Ollama service running (systemctl status ollama) for default provider
- semcode-mcp binary built and accessible
- semcode database indexed (.semcode.db in kernel tree)

**Optional**:
- review-prompts repository cloned
- Commercial API keys (for Anthropic/Gemini providers)

## Success Criteria

The feature will be considered successful when:

1. ✅ Can review a patch using only open-source, offline components (Ollama + semcode)
2. ✅ Follows review-core.md protocol exactly (Tasks 1-4)
3. ✅ Auto-loads subsystem context and patterns
4. ✅ LLM autonomously uses semcode MCP tools
5. ✅ Generates review-inline.txt matching expected format
6. ✅ Integrates seamlessly with existing b4 workflow
7. ✅ Supports both local (free) and commercial (paid) providers
8. ✅ Achieves comparable detection rate to manual review-prompts testing (>40%)
9. ✅ Completes review in reasonable time (<5 minutes per patch on local hardware)
10. ✅ User documentation and examples complete

## Future Enhancements

### Post-MVP Features

1. **Incremental Review**: Only review changed functions, not entire patch
2. **Multi-Model**: Route different tasks to different models (small for simple, large for complex)
3. **Learning Mode**: Learn from false positives to improve prompts
4. **CI Integration**: Run as GitHub Action / GitLab CI
5. **Web UI**: Optional web interface for review visualization
6. **Collaborative Review**: Multi-reviewer consensus mode
7. **Patch Suggestion**: Auto-generate fix suggestions
8. **Historical Analysis**: Learn from past reviews of similar code

## Open Questions

1. **Upstream Integration**: Should this be submitted to b4 upstream, or maintained separately?
   - **Recommendation**: Start as fork, submit RFC to b4 mailing list after Phase 2

2. **Model Recommendations**: Which models work best for kernel review?
   - **Testing needed**: Qwen2.5-Coder vs DeepSeek-Coder vs Llama-3

3. **Pattern Evolution**: How to keep patterns in sync with review-prompts repo?
   - **Recommendation**: Document review-prompts commit hash in config, allow updates

4. **Commercial API Costs**: How to warn users about costs?
   - **Recommendation**: Estimate tokens and cost before review, require confirmation

## References

- **b4 documentation**: https://b4.docs.kernel.org/
- **review-prompts**: https://github.com/masoncl/review-prompts (Chris Mason)
- **semcode**: https://github.com/facebookexperimental/semcode (Meta)
- **MCP Protocol**: https://modelcontextprotocol.io/
- **Ollama**: https://ollama.com/
- **Qwen2.5-Coder**: https://huggingface.co/Qwen/Qwen2.5-Coder-7B

## Authors

- Design: Claude (Anthropic) + Juri Lelli
- Integration with: b4 (Konstantin Ryabitsev), review-prompts (Chris Mason), semcode (Meta)

## License

GPL-2.0-or-later (matching b4's license)
