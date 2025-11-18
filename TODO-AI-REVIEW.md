# AI Review Implementation TODO

This document tracks the implementation progress of the AI review feature for b4.
See DESIGN-AI-REVIEW.md for architecture and design details.

## Phase 1: Core Infrastructure (2-3 weeks)

### Week 1: Foundation

#### 1.1 Project Structure Setup
- [x] Create feature branch `ai-review`
- [x] Write design document (DESIGN-AI-REVIEW.md)
- [x] Create TODO tracking document
- [ ] Create module directories
  - [ ] `src/b4/llm/` - LLM provider implementations
  - [ ] `tests/test_review/` - Review-specific tests
- [ ] Update `pyproject.toml` with new dependencies
  - [ ] Add `mcp>=1.0.0` to dependencies
  - [ ] Add `httpx>=0.24.0` to dependencies
  - [ ] Add optional dependencies: `anthropic`, `google-generativeai`, `prompt_toolkit`

#### 1.2 LLM Provider Base (src/b4/llm/base.py)
- [ ] Define `LLMProvider` abstract base class
  - [ ] Method: `__init__(config: dict)`
  - [ ] Method: `generate(messages: list, tools: list) -> dict`
  - [ ] Method: `stream_generate(messages: list, tools: list) -> Iterator`
  - [ ] Method: `supports_tools() -> bool`
  - [ ] Property: `name: str`
  - [ ] Property: `model: str`
- [ ] Define message format dataclasses
  - [ ] `Message(role: str, content: str)`
  - [ ] `ToolCall(id: str, name: str, arguments: dict)`
  - [ ] `ToolResult(id: str, result: str)`
- [ ] Define response format
  - [ ] `LLMResponse(content: str, tool_calls: list, finish_reason: str)`
- [ ] Write unit tests for base classes

#### 1.3 Ollama Provider (src/b4/llm/ollama.py)
- [ ] Implement `OllamaProvider(LLMProvider)`
- [ ] HTTP client setup (using httpx)
  - [ ] Configure base URL from config (default: http://localhost:11434)
  - [ ] Set timeouts (default: 300s for generation)
  - [ ] Implement retry logic with exponential backoff
- [ ] Implement `generate()` method
  - [ ] Format messages for Ollama API
  - [ ] Convert MCP tools to Ollama function calling format
  - [ ] POST to `/api/chat` endpoint
  - [ ] Parse response and extract tool calls
  - [ ] Handle errors (connection, timeout, model not found)
- [ ] Implement `stream_generate()` method
  - [ ] Stream responses from Ollama
  - [ ] Yield chunks as they arrive
  - [ ] Handle streaming errors
- [ ] Configuration loading
  - [ ] Read `b4-review-ollama.*` from git config
  - [ ] Support environment variables (OLLAMA_URL, OLLAMA_MODEL)
  - [ ] Default model: qwen2.5-coder:7b
- [ ] Write unit tests
  - [ ] Test connection to Ollama
  - [ ] Test message formatting
  - [ ] Test tool call parsing
  - [ ] Test error handling
  - [ ] Mock Ollama API for tests

#### 1.4 Command Registration (src/b4/command.py)
- [ ] Import review module: `from . import review`
- [ ] Add `review` subparser
  - [ ] Add positional argument: `msgid_or_commit`
  - [ ] Add `--provider` option (choices: ollama, anthropic, gemini)
  - [ ] Add `--interactive/-i` flag
  - [ ] Add `--prompts-dir` option
  - [ ] Add `--subsystems` option
  - [ ] Add `--patterns` option
  - [ ] Add `--output` option (choices: inline, markdown, json)
  - [ ] Add `-o/--output-file` option
  - [ ] Add `--batch` flag
  - [ ] Add `--debug` flag
  - [ ] Add `--no-cache` flag
- [ ] Set defaults function: `sp_review.set_defaults(func=review.cmd_review)`
- [ ] Test basic command parsing

#### 1.5 Review Module Skeleton (src/b4/review.py)
- [ ] Create module structure
- [ ] Import dependencies
  - [ ] `import b4` - existing b4 functionality
  - [ ] `from . import llm` - LLM providers
  - [ ] Standard library imports
- [ ] Define `cmd_review(cmdargs)` entry point
  - [ ] Parse arguments
  - [ ] Determine input type (msgid, commit, range, mbox)
  - [ ] Call appropriate handler
  - [ ] Handle errors and logging
- [ ] Define basic workflow functions (stubs for now)
  - [ ] `review_from_msgid(msgid, config) -> ReviewResult`
  - [ ] `review_from_commit(commit, config) -> ReviewResult`
  - [ ] `review_from_range(commit_range, config) -> list[ReviewResult]`
  - [ ] `review_interactive(patch, config) -> None`
- [ ] Define `ReviewResult` dataclass
  - [ ] `patch_info: dict` - patch metadata
  - [ ] `regressions_found: int`
  - [ ] `patterns_triggered: list[str]`
  - [ ] `review_text: str`
  - [ ] `tokens_used: int`
  - [ ] `analysis_time: float`
- [ ] Write basic integration test
  - [ ] Test `b4 review --help` works
  - [ ] Test command routing to review module

### Week 2: MCP Integration

#### 2.1 MCP Client Implementation (src/b4/mcp_client.py)
- [ ] Install Python MCP SDK
  - [ ] Add to requirements: `mcp>=1.0.0`
  - [ ] Test basic MCP SDK functionality
- [ ] Implement `SemcodeMCPClient` class
  - [ ] Method: `__init__(semcode_binary: str, kernel_dir: str)`
  - [ ] Method: `connect() -> None` - Start semcode-mcp subprocess
  - [ ] Method: `disconnect() -> None` - Clean shutdown
  - [ ] Method: `discover_tools() -> list[ToolSchema]` - Get available tools
  - [ ] Method: `invoke_tool(name: str, args: dict) -> dict` - Call a tool
  - [ ] Context manager support (`__enter__`, `__exit__`)
- [ ] Tool schema parsing
  - [ ] Parse MCP tool definitions from semcode-mcp
  - [ ] Convert to standardized format
  - [ ] Cache tool schemas
- [ ] Subprocess management
  - [ ] Start semcode-mcp with stdio transport
  - [ ] Handle process lifecycle
  - [ ] Capture stderr for debugging
  - [ ] Graceful shutdown on errors
- [ ] Error handling
  - [ ] Connection failures
  - [ ] Tool invocation errors
  - [ ] Timeout handling
  - [ ] Process crashes
- [ ] Write unit tests
  - [ ] Test connection to semcode-mcp
  - [ ] Test tool discovery
  - [ ] Test tool invocation
  - [ ] Test error scenarios
  - [ ] Mock semcode-mcp for tests

#### 2.2 Tool Bridge (src/b4/tool_bridge.py)
- [ ] Implement `convert_mcp_to_provider_tools(mcp_tools, provider_type)`
  - [ ] Convert MCP schemas to Ollama function format
  - [ ] Convert MCP schemas to Anthropic tool format (future)
  - [ ] Convert MCP schemas to Gemini function format (future)
- [ ] Implement `execute_tool_call(tool_call, mcp_client) -> ToolResult`
  - [ ] Parse tool call from LLM
  - [ ] Invoke via MCP client
  - [ ] Format result for LLM
  - [ ] Handle errors
- [ ] Write unit tests
  - [ ] Test schema conversion for each provider
  - [ ] Test tool execution
  - [ ] Test error handling

#### 2.3 Integration Testing
- [ ] Create integration test with real semcode-mcp
  - [ ] Start semcode-mcp subprocess
  - [ ] Discover tools
  - [ ] Invoke `find_function` tool
  - [ ] Verify result format
  - [ ] Clean shutdown
- [ ] Test LLM + MCP workflow
  - [ ] Initialize Ollama provider
  - [ ] Initialize MCP client
  - [ ] Convert MCP tools to Ollama format
  - [ ] Send prompt with tools to LLM
  - [ ] Execute tool calls
  - [ ] Return results to LLM
  - [ ] Verify end-to-end flow

### Week 3: Review Protocol

#### 3.1 Review Prompts Loader (src/b4/review_prompts.py)
- [ ] Implement `ReviewPromptsLoader` class
  - [ ] Method: `__init__(prompts_dir: str)`
  - [ ] Method: `load_core_protocol() -> str`
  - [ ] Method: `load_technical_patterns() -> str`
  - [ ] Method: `detect_subsystems(patch_diff: str) -> list[str]`
  - [ ] Method: `load_subsystem_prompts(subsystems: list) -> dict`
  - [ ] Method: `load_patterns(pattern_ids: list) -> dict`
- [ ] Configuration handling
  - [ ] Check `b4.review-prompts-dir` config
  - [ ] Check `REVIEW_PROMPTS_DIR` environment variable
  - [ ] Default to `~/Work/kernel/review-prompts`
  - [ ] Validate directory exists
- [ ] Subsystem detection logic
  - [ ] Parse review-core.md subsystem mapping
  - [ ] Match file paths in diff
  - [ ] Match function names in diff
  - [ ] Return list of detected subsystems
- [ ] File loading
  - [ ] Read markdown files
  - [ ] Handle missing files gracefully
  - [ ] Cache loaded prompts
- [ ] Write unit tests
  - [ ] Test file loading
  - [ ] Test subsystem detection
  - [ ] Test error handling for missing files

#### 3.2 Review Engine Core (src/b4/review.py - expand)
- [ ] Implement `ReviewEngine` class
  - [ ] Method: `__init__(provider, mcp_client, prompts_loader)`
  - [ ] Method: `review_patch(patch_diff, metadata) -> ReviewResult`
  - [ ] Method: `build_system_prompt() -> str`
  - [ ] Method: `build_user_prompt(patch_diff) -> str`
  - [ ] Method: `execute_review_protocol() -> ReviewResult`
  - [ ] Method: `parse_review_response(llm_response) -> ReviewResult`
- [ ] System prompt construction
  - [ ] Load review-core.md
  - [ ] Load technical-patterns.md
  - [ ] Detect and load subsystem context
  - [ ] Combine into system prompt
- [ ] Review execution
  - [ ] Initialize conversation with system + user prompts
  - [ ] Execute LLM with MCP tools available
  - [ ] Handle tool calls in loop (LLM → tools → LLM → ...)
  - [ ] Detect protocol completion
  - [ ] Validate protocol requirements met
- [ ] Response parsing
  - [ ] Extract regressions count
  - [ ] Extract patterns triggered
  - [ ] Extract tokens used
  - [ ] Validate output format
- [ ] Write unit tests
  - [ ] Test prompt construction
  - [ ] Test review execution flow
  - [ ] Test response parsing

#### 3.3 Output Formatter (src/b4/review_formatter.py)
- [ ] Implement `format_inline(review_result, patch_metadata) -> str`
  - [ ] Generate email-style review (review-inline.txt format)
  - [ ] Include patch metadata
  - [ ] Include regression details
  - [ ] Format for easy email reply
- [ ] Implement `format_markdown(review_result) -> str`
  - [ ] Generate markdown report
  - [ ] Include summary section
  - [ ] Include detailed findings
  - [ ] Include pattern references
- [ ] Implement `format_json(review_result) -> str`
  - [ ] Generate JSON output
  - [ ] Machine-readable format
  - [ ] For CI/automation
- [ ] Write unit tests for each formatter

#### 3.4 End-to-End Test
- [ ] Create real patch test case
  - [ ] Use actual kernel patch
  - [ ] Known regression if possible
- [ ] Full workflow test
  - [ ] Fetch patch via b4
  - [ ] Load review prompts
  - [ ] Initialize Ollama + semcode
  - [ ] Execute review
  - [ ] Verify output format
  - [ ] Check for expected patterns
- [ ] Performance benchmark
  - [ ] Measure review time
  - [ ] Measure token usage
  - [ ] Measure accuracy (if known regression)

## Phase 2: Features & Polish (2-3 weeks)

### Week 4: Additional Providers

#### 4.1 Anthropic Provider (src/b4/llm/anthropic.py)
- [ ] Implement `AnthropicProvider(LLMProvider)`
- [ ] Install Anthropic SDK
  - [ ] Add to optional deps: `anthropic>=0.18.0`
- [ ] Implement `generate()` method
  - [ ] Use Anthropic Messages API
  - [ ] Convert MCP tools to Anthropic tool format
  - [ ] Handle tool use blocks
  - [ ] Parse responses
- [ ] Implement `stream_generate()` method
- [ ] API key management
  - [ ] Load from `ANTHROPIC_API_KEY` env var
  - [ ] Error if key missing
  - [ ] Warn about API costs
- [ ] Configuration
  - [ ] Read `b4-review-anthropic.*` config
  - [ ] Default model: claude-3-5-sonnet-20241022
  - [ ] Configure max tokens, timeout
- [ ] Write unit tests (with mocked API)

#### 4.2 Gemini Provider (src/b4/llm/gemini.py)
- [ ] Implement `GeminiProvider(LLMProvider)`
- [ ] Install Gemini SDK
  - [ ] Add to optional deps: `google-generativeai`
- [ ] Implement `generate()` method
  - [ ] Use Google Generative AI API
  - [ ] Convert MCP tools to Gemini function format
  - [ ] Parse responses
- [ ] Implement `stream_generate()` method
- [ ] API key management
  - [ ] Load from `GEMINI_API_KEY` env var
- [ ] Configuration
  - [ ] Read `b4-review-gemini.*` config
  - [ ] Default model: gemini-2.0-flash-exp
- [ ] Write unit tests

#### 4.3 Provider Factory
- [ ] Implement `get_provider(provider_name: str, config: dict) -> LLMProvider`
  - [ ] Route to Ollama, Anthropic, or Gemini
  - [ ] Load provider-specific config
  - [ ] Validate requirements (API keys, etc.)
  - [ ] Return configured provider
- [ ] Write tests for provider selection

### Week 5: Interactive Mode

#### 5.1 Basic Interactive Support
- [ ] Implement `review_interactive_simple(review_result, provider, mcp_client)`
  - [ ] Show review results
  - [ ] Prompt: "Continue with follow-up questions? [y/N]"
  - [ ] Accept user questions
  - [ ] Continue LLM conversation with MCP tools
  - [ ] Exit on "exit" or Ctrl-D
- [ ] Conversation history management
  - [ ] Maintain message history
  - [ ] Add user questions
  - [ ] Add LLM responses
  - [ ] Add tool calls and results
- [ ] Write integration test

#### 5.2 Full Interactive Session (Optional - Phase 2.5)
- [ ] Install prompt_toolkit
  - [ ] Add to optional deps
- [ ] Implement REPL with commands
  - [ ] `analyze` - Run full review protocol
  - [ ] `question <text>` - Ask follow-up
  - [ ] `focus <file>` - Narrow context
  - [ ] `checklist <category>` - Run specific patterns
  - [ ] `report [--format] [--output]` - Generate report
  - [ ] `help` - Show commands
  - [ ] `exit` - Exit session
- [ ] Implement command parser
- [ ] Implement context management
  - [ ] Track focused files
  - [ ] Filter patterns
- [ ] Add readline features
  - [ ] Command history
  - [ ] Tab completion
  - [ ] Syntax highlighting
- [ ] Write integration tests

### Week 6: Output & Configuration

#### 6.1 Configuration System
- [ ] Implement `ReviewConfig` class
  - [ ] Load from git config (`b4.*`, `b4-review.*`, `b4-review-<provider>.*`)
  - [ ] Load from environment variables
  - [ ] Load from CLI arguments
  - [ ] Merge with precedence: CLI > env > git config > defaults
- [ ] Configuration validation
  - [ ] Validate required fields
  - [ ] Validate paths exist
  - [ ] Validate provider settings
- [ ] Write unit tests

#### 6.2 Response Caching
- [ ] Implement `ReviewCache` class
  - [ ] Cache key: hash(patch_diff + provider + model + prompts_version)
  - [ ] Cache location: `.git/b4-review-cache/`
  - [ ] TTL support (default: 24 hours)
  - [ ] Size limits
- [ ] Cache operations
  - [ ] `get(key) -> ReviewResult | None`
  - [ ] `set(key, result, ttl)`
  - [ ] `invalidate(key)`
  - [ ] `clear_expired()`
- [ ] Respect `--no-cache` flag
- [ ] Write unit tests

#### 6.3 Batch Processing
- [ ] Implement `review_batch(commit_range, config)`
  - [ ] Parse commit range
  - [ ] Iterate over commits
  - [ ] Review each commit
  - [ ] Aggregate results
  - [ ] Generate summary report
- [ ] Parallel processing (optional)
  - [ ] Review multiple patches in parallel
  - [ ] Thread pool or process pool
  - [ ] Resource limits
- [ ] Progress indicators
  - [ ] Show current patch being reviewed
  - [ ] Show completion percentage
  - [ ] Estimated time remaining
- [ ] Write integration test

#### 6.4 Documentation
- [ ] User documentation
  - [ ] Installation instructions
  - [ ] Quick start guide
  - [ ] Configuration reference
  - [ ] Command reference
  - [ ] Examples
- [ ] Developer documentation
  - [ ] Architecture overview
  - [ ] Adding new providers
  - [ ] Testing guide
  - [ ] Contributing guide
- [ ] Update README.rst with review feature
- [ ] Create man page for `b4-review`

## Phase 3: Testing & Refinement (1-2 weeks)

### Week 7: Comprehensive Testing

#### 7.1 Unit Test Coverage
- [ ] Achieve >80% code coverage
- [ ] Review all modules:
  - [ ] `llm/base.py`
  - [ ] `llm/ollama.py`
  - [ ] `llm/anthropic.py`
  - [ ] `llm/gemini.py`
  - [ ] `mcp_client.py`
  - [ ] `tool_bridge.py`
  - [ ] `review_prompts.py`
  - [ ] `review.py`
  - [ ] `review_formatter.py`
- [ ] Add missing tests
- [ ] Fix failing tests

#### 7.2 Integration Testing
- [ ] Test with review-prompts dataset
  - [ ] Clone review-prompts repo
  - [ ] Test against known regressions
  - [ ] Measure detection rate
  - [ ] Document false positives
  - [ ] Document false negatives
- [ ] Test different providers
  - [ ] Ollama with qwen2.5-coder:7b
  - [ ] Anthropic with claude-3-5-sonnet
  - [ ] Gemini with gemini-2.0-flash
  - [ ] Compare results
- [ ] Test different patch types
  - [ ] Simple bug fixes
  - [ ] Complex refactoring
  - [ ] New features
  - [ ] Multiple files
  - [ ] Different subsystems

#### 7.3 Performance Testing
- [ ] Benchmark review times
  - [ ] Small patches (<100 lines)
  - [ ] Medium patches (100-500 lines)
  - [ ] Large patches (>500 lines)
  - [ ] Patch series
- [ ] Benchmark token usage
  - [ ] Track tokens per patch
  - [ ] Estimate costs for commercial APIs
- [ ] Memory usage profiling
- [ ] Optimize bottlenecks

### Week 8: Refinement & Documentation

#### 8.1 Error Handling Review
- [ ] Audit all error paths
- [ ] Improve error messages
  - [ ] Clear, actionable messages
  - [ ] Suggest fixes when possible
- [ ] Add recovery strategies
  - [ ] Retry with backoff
  - [ ] Graceful degradation
  - [ ] Fallback options
- [ ] Test error scenarios
  - [ ] Network failures
  - [ ] API rate limits
  - [ ] Invalid patches
  - [ ] Missing dependencies

#### 8.2 User Experience Polish
- [ ] Improve progress indicators
  - [ ] Show what the LLM is doing
  - [ ] Show tool calls in progress
  - [ ] Spinner/progress bar
- [ ] Better logging
  - [ ] Debug mode shows all details
  - [ ] Normal mode shows progress
  - [ ] Quiet mode shows only results
- [ ] Color output (optional)
  - [ ] Highlight regressions
  - [ ] Color-code severity
  - [ ] Respect NO_COLOR env var

#### 8.3 Final Documentation Pass
- [ ] Review all documentation
- [ ] Add screenshots/examples
- [ ] Test all examples
- [ ] Proofread and polish
- [ ] Generate final man pages

#### 8.4 Upstream Preparation (if desired)
- [ ] Review b4 contribution guidelines
- [ ] Ensure code style matches b4
- [ ] Prepare patch series
  - [ ] Logical commit structure
  - [ ] Detailed commit messages
  - [ ] Signed-off-by
- [ ] Draft RFC email for tools@kernel.org
- [ ] Address initial feedback

## Stretch Goals (Post-Phase 3)

### Additional Features
- [ ] Incremental review (only changed functions)
- [ ] Multi-model routing (different models for different tasks)
- [ ] Learning from false positives
- [ ] CI integration examples (GitHub Actions, GitLab CI)
- [ ] Web UI prototype
- [ ] Patch suggestion generation

### Additional Providers
- [ ] OpenAI provider (gpt-4, gpt-4-turbo)
- [ ] Local model via llama.cpp
- [ ] Local model via vLLM

### Advanced MCP Features
- [ ] Multiple MCP servers
- [ ] Custom MCP servers
- [ ] MCP server discovery

## Current Status

**Branch**: `ai-review`
**Latest Commit**: `c5d2208` - docs: Add AI review feature design document
**Phase**: 1 (Foundation)
**Started**: 2025-11-18

## Notes

- Update this document as tasks are completed
- Mark completed items with `[x]`
- Add notes on blockers or issues
- Track time estimates vs actuals
- Document decisions and changes

## Testing Checklist

Before each phase completion:
- [ ] All unit tests passing
- [ ] All integration tests passing
- [ ] Manual testing completed
- [ ] Documentation updated
- [ ] Code review completed (if collaborative)
- [ ] Commit and push to branch

## Definition of Done

Each task is considered done when:
1. Code is written and working
2. Unit tests are written and passing
3. Integration tests pass (if applicable)
4. Documentation is updated
5. Code is committed to branch
