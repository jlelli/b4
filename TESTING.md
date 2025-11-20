# Testing Guide for b4 AI Review Feature

This guide explains how to test the Phase 1 implementation (Weeks 1-2) of the AI review feature.

## Current Implementation Status

**What's Implemented:**
- ✅ LLM provider base classes and Ollama provider
- ✅ MCP client for semcode-mcp integration
- ✅ Tool schema conversion (Ollama, Anthropic, Gemini)
- ✅ Command registration (`b4 review`)
- ✅ Basic review module structure
- ✅ Unit and integration tests

**What's NOT Yet Implemented:**
- ❌ Review prompts loader (Week 3)
- ❌ Review engine orchestration (Week 3)
- ❌ Output formatters (Week 3)
- ❌ End-to-end review workflow (Week 3)

## Prerequisites

### 1. Install b4 in Development Mode

```bash
cd /home/jlelli/Work/kernel/b4
pip install -e .
```

This installs b4 with the new review dependencies (mcp, httpx).

### 2. Set Up Ollama (Local LLM)

```bash
# Install Ollama (if not already installed)
curl -fsSL https://ollama.com/install.sh | sh

# Start Ollama service
ollama serve

# Pull the default model (in another terminal)
ollama pull qwen2.5-coder:7b
```

Verify Ollama is running:
```bash
curl http://localhost:11434/api/version
```

Should return: `{"version":"..."}`

### 3. Set Up semcode-mcp

You need the semcode-mcp binary and an indexed kernel tree.

**Build semcode-mcp:**
```bash
cd /home/jlelli/Work/kernel/semcode
cargo build --release
```

Binary will be at: `target/release/semcode-mcp`

**Index your kernel tree:**
```bash
cd /home/jlelli/Work/kernel/linux  # or wherever your kernel source is

# Create semcode index
/home/jlelli/Work/kernel/semcode/target/release/semcode index

# This creates .semcode.db directory with the index
```

## Testing Components

### Test 1: Unit Tests

Run the test suite to verify all components:

```bash
cd /home/jlelli/Work/kernel/b4

# Activate venv if using one
source venv-ai-review/bin/activate

# Run all review tests (PYTHONPATH is required even with pip install -e)
PYTHONPATH=src pytest tests/test_review/ -v

# Run specific test files
PYTHONPATH=src pytest tests/test_review/test_mcp_client.py -v
PYTHONPATH=src pytest tests/test_review/test_tool_bridge.py -v
PYTHONPATH=src pytest tests/test_review/test_integration.py -v
```

**Expected output:** All tests should pass (except the skipped integration test).

### Test 2: MCP Client Connection

Test that the MCP client can connect to semcode-mcp:

```bash
cd /home/jlelli/Work/kernel/b4

# Activate venv if using one
source venv-ai-review/bin/activate

PYTHONPATH=src python3 << 'EOF'
from b4.mcp_client import SemcodeMCPClient

# Connect to semcode-mcp
with SemcodeMCPClient(
    semcode_binary='/home/jlelli/Work/kernel/semcode/target/release/semcode-mcp',
    kernel_dir='/home/jlelli/Work/kernel/linux'
) as client:
    # Discover available tools
    tools = client.get_tools()
    print(f"Discovered {len(tools)} tools:")
    for name in tools.keys():
        print(f"  - {name}")

    # Test a simple tool call
    print("\nTesting find_function tool...")
    result = client.invoke_tool('find_function', {'name': '__schedule'})

    if not result.get('isError'):
        print("✅ Tool call successful!")
        content = result.get('content', [])
        if content:
            text = content[0].get('text', '')
            print(f"Result preview: {text[:200]}...")
    else:
        print("❌ Tool call failed")
EOF
```

**Expected output:**
```
Discovered 10 tools:
  - find_function
  - find_type
  - find_callers
  - find_calls
  - find_callchain
  - diff_functions
  - grep_functions
  - vgrep_functions
  - find_commit
  - vcommit_similar_commits

Testing find_function tool...
✅ Tool call successful!
Result preview: static void __schedule(void)
{
    struct task_struct *prev, *next;
    ...
```

### Test 3: Ollama Provider

Test that the Ollama provider can connect and generate:

```bash
cd /home/jlelli/Work/kernel/b4

# Activate venv if using one
source venv-ai-review/bin/activate

PYTHONPATH=src python3 << 'EOF'
from b4.llm.ollama import OllamaProvider
from b4.llm.base import Message

# Initialize Ollama
ollama = OllamaProvider({
    'url': 'http://localhost:11434',
    'model': 'qwen2.5-coder:7b',
    'timeout': 60
})

print(f"✅ Connected to Ollama")
print(f"   Provider: {ollama.name}")
print(f"   Model: {ollama.model}")

# Test basic generation
messages = [
    Message(role='user', content='What is the purpose of the __schedule function in the Linux kernel?')
]

print("\nGenerating response...")
response = ollama.generate(messages)

print(f"✅ Generation successful!")
print(f"   Finish reason: {response.finish_reason}")
print(f"   Response: {response.content[:300]}...")
EOF
```

**Expected output:**
```
✅ Connected to Ollama
   Provider: ollama
   Model: qwen2.5-coder:7b

Generating response...
✅ Generation successful!
   Finish reason: stop
   Response: The __schedule() function is the core scheduler function in the Linux kernel...
```

### Test 4: Full Integration (LLM + MCP)

Test the complete workflow of LLM calling MCP tools:

```bash
cd /home/jlelli/Work/kernel/b4

# Activate venv if using one
source venv-ai-review/bin/activate

PYTHONPATH=src python3 << 'EOF'
from b4.llm.ollama import OllamaProvider
from b4.llm.base import Message
from b4.mcp_client import SemcodeMCPClient
from b4.tool_bridge import convert_mcp_to_ollama_tools, execute_tool_calls

# Initialize both components
ollama = OllamaProvider({
    'url': 'http://localhost:11434',
    'model': 'qwen2.5-coder:7b',
    'timeout': 120
})

with SemcodeMCPClient(
    semcode_binary='/home/jlelli/Work/kernel/semcode/target/release/semcode-mcp',
    kernel_dir='/home/jlelli/Work/kernel/linux'
) as mcp:
    # Get MCP tools and convert to Ollama format
    mcp_tools = mcp.get_tools()
    ollama_tools = convert_mcp_to_ollama_tools(mcp_tools)

    print(f"✅ Loaded {len(ollama_tools)} tools for LLM")

    # Ask LLM a question that should trigger tool use
    messages = [
        Message(
            role='user',
            content='Find the definition of the __schedule function and tell me what it does.'
        )
    ]

    print("\n🤖 Asking LLM (with tools available)...")
    response = ollama.generate(messages, tools=ollama_tools)

    # Check if LLM used tools
    if response.has_tool_calls:
        print(f"✅ LLM made {len(response.tool_calls)} tool call(s):")
        for tc in response.tool_calls:
            print(f"   - {tc.name}({tc.arguments})")

        # Execute tool calls
        print("\n🔧 Executing tool calls...")
        tool_results = execute_tool_calls(response.tool_calls, mcp)

        for i, result in enumerate(tool_results):
            if result.is_error:
                print(f"❌ Tool {i+1} failed: {result.result}")
            else:
                print(f"✅ Tool {i+1} succeeded ({len(result.result)} chars)")

        # Send results back to LLM
        messages.append(Message(role='assistant', content=response.content or '', tool_calls=response.tool_calls))
        for result in tool_results:
            messages.append(Message(role='tool', content=result.result, tool_call_id=result.tool_call_id))

        print("\n🤖 Asking LLM to synthesize results...")
        final_response = ollama.generate(messages)
        print(f"\n📝 Final answer:\n{final_response.content}")
    else:
        print(f"ℹ️  LLM answered directly without tools:")
        print(f"{response.content}")
EOF
```

**Expected output:**
```
✅ Loaded 10 tools for LLM

🤖 Asking LLM (with tools available)...
✅ LLM made 1 tool call(s):
   - find_function({'name': '__schedule'})

🔧 Executing tool calls...
✅ Tool 1 succeeded (2547 chars)

🤖 Asking LLM to synthesize results...

📝 Final answer:
The __schedule() function is the core scheduler in the Linux kernel. Based on the code,
it performs the following key tasks:
1. Disables preemption and prepares for context switch
2. Selects the next task to run using pick_next_task()
3. Performs the actual context switch if needed
...
```

### Test 5: Command Help

Test that the `b4 review` command is registered:

```bash
# Show b4 review help
b4 review --help

# Or if not installed globally:
cd /home/jlelli/Work/kernel/b4
PYTHONPATH=src python3 -m b4.command review --help
```

**Expected output:**
```
usage: b4 review [-h] [--provider {ollama,anthropic,gemini}] [-i]
                 [--prompts-dir PROMPTS_DIR] [--subsystems SUBSYSTEMS]
                 [--patterns PATTERNS] [--output {inline,markdown,json}]
                 [-o OUTPUT_FILE] [--batch] [--debug] [--no-cache]
                 [msgid_or_commit]

AI-assisted patch review

positional arguments:
  msgid_or_commit       Message-ID, commit SHA, or commit range

optional arguments:
  --provider {ollama,anthropic,gemini}
                        LLM provider to use (default: ollama)
  -i, --interactive     Interactive review mode
  ...
```

## What You CAN'T Test Yet

The following won't work until Week 3 implementation:

❌ **Actual patch review:** `b4 review HEAD` will fail because the review engine isn't implemented yet.

❌ **Review prompts loading:** The prompts loader isn't implemented.

❌ **Output formatting:** Formatters for inline/markdown/json aren't implemented.

The current code will successfully:
- Parse arguments
- Detect input type (msgid, commit, range)
- Call stub functions
- But won't produce actual review output

## Troubleshooting

### Ollama Connection Failed

```bash
# Check if Ollama is running
ps aux | grep ollama
curl http://localhost:11434/api/version

# Restart Ollama
pkill ollama
ollama serve
```

### semcode-mcp Not Found

```bash
# Verify binary exists
ls -l /home/jlelli/Work/kernel/semcode/target/release/semcode-mcp

# If not found, rebuild
cd /home/jlelli/Work/kernel/semcode
cargo build --release
```

### Kernel Index Not Found

```bash
# Check if .semcode.db exists
ls -la /home/jlelli/Work/kernel/linux/.semcode.db

# If not, create index
cd /home/jlelli/Work/kernel/linux
/home/jlelli/Work/kernel/semcode/target/release/semcode index
```

### Python Import Errors

```bash
# Reinstall b4 in development mode
cd /home/jlelli/Work/kernel/b4
pip install -e .

# Or set PYTHONPATH
export PYTHONPATH=/home/jlelli/Work/kernel/b4/src:$PYTHONPATH
```

## Next Steps

Once these tests pass, we'll be ready to implement Week 3:
- Review Prompts Loader (integrates with review-prompts repo)
- Review Engine Core (orchestrates LLM + MCP for actual reviews)
- Output Formatters (generate inline/markdown/json reports)

This will enable end-to-end patch review functionality!
