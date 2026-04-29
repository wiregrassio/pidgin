# Anthropic Prompt Caching — Technical Reference

_Fetched 2026-04-23 from https://platform.claude.com/docs/en/docs/build-with-claude/prompt-caching_

Load-bearing for the ensemble primitive: the `prompt` argument is the
cached prefix, the `content` argument is the variable suffix. Every
parallel call within a single ensemble invocation should hit the cache
on the prefix.

---

## Quick Start

Add `cache_control` to your request:

```json
{
  "model": "claude-opus-4-7",
  "max_tokens": 1024,
  "cache_control": { "type": "ephemeral" },
  "system": "Your system prompt",
  "messages": [...]
}
```

---

## 1. Enabling Caching: Syntax & Placement

### Automatic Caching (Recommended)

Place a single `cache_control` at the top level of your request. The
system automatically applies the breakpoint to the last cacheable block
and moves it forward as conversations grow.

```json
{
  "model": "claude-opus-4-7",
  "max_tokens": 1024,
  "cache_control": { "type": "ephemeral" },
  "system": "...",
  "messages": [...]
}
```

### Explicit Cache Breakpoints

Place `cache_control` directly on individual content blocks for
fine-grained control.

**Valid attachment locations:**
- `system[*].cache_control` — text blocks in system array
- `messages[*].content[*].cache_control` — text, image, document, tool use, and tool result blocks
- `tools[*].cache_control` — on the last tool (caches all tools up to and including that one)

```json
{
  "system": [
    {
      "type": "text",
      "text": "Static instructions...",
      "cache_control": { "type": "ephemeral" }
    }
  ],
  "messages": [
    {
      "role": "user",
      "content": [
        {
          "type": "text",
          "text": "User query...",
          "cache_control": { "type": "ephemeral" }
        }
      ]
    }
  ]
}
```

---

## 2. TTL Options

| Option | Syntax | Default | Cost Multiplier |
|--------|--------|---------|-----------------|
| 5-minute ephemeral | `{ "type": "ephemeral" }` | Yes | 1.25× write, 0.1× read |
| 1-hour ephemeral | `{ "type": "ephemeral", "ttl": "1h" }` | No | 2.0× write, 0.1× read |

```json
// 5-minute (default)
{ "cache_control": { "type": "ephemeral" } }

// 1-hour
{ "cache_control": { "type": "ephemeral", "ttl": "1h" } }
```

**Constraint:** When mixing TTLs in one request, longer TTLs must
appear before shorter ones (1h before 5m in prompt order).

---

## 3. Minimum Cacheable Token Length

| Model Family | Min Tokens |
|--------------|-----------|
| Claude Mythos, Opus 4.7, 4.6, 4.5 | 4,096 |
| Claude Sonnet 4.6 | 2,048 |
| Claude Sonnet 4.5, 4; Opus 4.1, 4 | 1,024 |
| Claude Haiku 4.5 | 4,096 |
| Claude Haiku 3.5 | 2,048 |

**Behavior:** Prompts shorter than the minimum are processed without
caching (no error, silent fallback). Check response `usage` fields —
if both `cache_creation_input_tokens` and `cache_read_input_tokens`
are 0, caching was skipped.

**Implication for the ensemble primitive:** cached prompts for the
Haiku 4.5 tier must be ≥4,096 tokens or caching is a no-op. The design
doc's "200-token function body" case will therefore NOT cache on Haiku
4.5 unless the instruction block alone is ≥4,096 tokens. Build the
instruction block with that floor in mind, or accept the cache will
silently no-op for small calls.

---

## 4. Maximum Cache Breakpoints Per Request

**Limit:** 4 explicit cache breakpoints per request.

When using automatic caching with explicit breakpoints already in
place: if 4 explicit breakpoints exist, automatic caching returns a
400 error (no slots available).

---

## 5. Pricing Structure

**Base input token cost = 1.0× base price**

| Operation | Multiplier | Formula |
|-----------|-----------|---------|
| Cache write (5m) | 1.25× | 1.25 × base_input_price |
| Cache write (1h) | 2.0× | 2.0 × base_input_price |
| Cache hit / refresh | 0.1× | 0.1 × base_input_price |
| Uncached input | 1.0× | 1.0 × base_input_price |

**Example (Claude Opus 4.7):**
- Base input: $5 / million tokens
- Cache write (5m): $6.25 / million tokens
- Cache write (1h): $10 / million tokens
- Cache hit: $0.50 / million tokens

**Total cost calculation:**

```
total_cost = (cache_read_tokens × 0.1 × base_price)
           + (cache_creation_tokens × multiplier × base_price)
           + (input_tokens × base_price)
           + (output_tokens × output_price)
```

---

## 6. Cache Scope & Invalidation

### Scope
- **Isolation:** Caches are isolated per workspace (as of Feb 5, 2026). Different workspaces in the same org do not share caches.
- **Exact matching:** 100% identical prompt segments required for cache hit (including all text and images up to the breakpoint).
- **Hierarchy:** Cache hierarchy is `tools` → `system` → `messages`. Changes at each level invalidate that level and all subsequent levels.

### What Invalidates Cache

| Change | Tools | System | Messages |
|--------|-------|--------|----------|
| Tool definitions | ✘ | ✘ | ✘ |
| Web search enable/disable | ✓ | ✘ | ✘ |
| Citations enable/disable | ✓ | ✘ | ✘ |
| Speed mode (fast ↔ standard) | ✓ | ✘ | ✘ |
| `tool_choice` parameter | ✓ | ✓ | ✘ |
| Images added/removed | ✓ | ✓ | ✘ |
| Thinking parameters (extended thinking) | ✓ | ✓ | ✘ |
| Non-tool-result user content (with thinking) | ✓ | ✓ | ✘ |

**Key insight:** Changes to content at or before a cache breakpoint
invalidate that breakpoint and all subsequent ones.

---

## 7. Usage Reporting

Response `usage` object fields:

```json
{
  "usage": {
    "input_tokens": 50,
    "cache_read_input_tokens": 10000,
    "cache_creation_input_tokens": 500,
    "output_tokens": 200
  }
}
```

| Field | Meaning |
|-------|---------|
| `cache_read_input_tokens` | Tokens retrieved from cache (already processed) |
| `cache_creation_input_tokens` | Tokens written to cache on this request |
| `input_tokens` | Tokens after the last cache breakpoint (not cached) |
| `output_tokens` | Generated tokens |

**Total input tokens processed:**

```
total = cache_read_input_tokens + cache_creation_input_tokens + input_tokens
```

For streaming, check the `message_start` event for initial usage;
final totals come with `message_stop`.

---

## 8. Interaction with Key Features

### Streaming
- Cache hits reduce time-to-first-token.
- Usage fields appear in initial `message_start` event.
- Cache behavior is transparent; use same `cache_control` markers.

### Tool Use
- Tool definitions can be cached by placing `cache_control` on the last tool in the `tools` array.
- Tool use blocks and tool result blocks in `messages.content` can be cached individually.
- Non-tool-result user blocks cause previous thinking blocks to be stripped from context (cache invalidation).

### System Prompt
- System blocks are cached in `system[*]` array.
- Each block can have its own `cache_control`.
- System content is always evaluated before messages in the cache hierarchy.

### Messages Array Structure
- **Message ordering:** `tools` → `system` → `messages` (in that order for cache prefix).
- **Content blocks:** Each `messages[i].content[j]` can be individually marked with `cache_control`.
- **Multi-turn:** With automatic caching, conversation grows and cache point moves forward automatically.

---

## 9. Common Pitfalls

### Placing breakpoint on changing content
Problem: `cache_control` on a block containing a timestamp or
per-request data. Each request has a different prefix hash; the 20-block
lookback window won't find the prior write.

Solution: Place the breakpoint on the last stable block before the
changing content.

```json
{
  "system": [
    { "type": "text", "text": "Static context...", "cache_control": { "type": "ephemeral" } }
  ],
  "messages": [
    { "role": "user", "content": "Timestamp: 2025-01-15T10:30Z\nUser question..." }
  ]
}
// Wrong: cache misses every request because the message timestamp changes
```

### Forgetting minimum token threshold
Problem: Prompt under minimum length for the model. Request succeeds
but both `cache_creation_input_tokens` and `cache_read_input_tokens`
are 0.

Solution: Verify prompt length with a tokenizer; expand cached content
if needed.

### Mismatched content across requests
Problem: Cache a tool definition, then slightly alter the tool name or
schema in the next request. Cache miss because hashes no longer match.

Solution: Ensure tool definitions, system blocks, and other cached
segments are byte-identical across all requests using the cache.

### Concurrent requests before first response
Problem: Fire N parallel requests with the same cache breakpoint. Only
the first gets a cache write; the other N-1 may miss because the cache
entry isn't available until the first response begins.

Solution: For ensemble dispatch, serialize the first call to warm the
cache, then fan out the remaining N-1 in parallel. Budget the first
call at cache-write pricing, the rest at cache-read pricing.

### Lookback window too large
Problem: 50-message conversation with one breakpoint at the end. The
21st message onward is never cached because the 20-block lookback
misses prior writes.

Solution: Use multiple breakpoints (up to 4) spaced closer together.

### Mixing TTLs incorrectly
Problem: 5-minute cache block placed before a 1-hour block.

Solution: Always order longer TTLs first (1h before 5m).

### Unstable JSON key ordering in tool inputs
Problem: Some languages (Go, Swift) randomize JSON object key order
during serialization. The hash changes between requests even though
content is logically identical.

Solution: Canonicalize JSON or manually construct tool use blocks with
stable key order.

---

## Model Support

Prompt caching is supported on all active Claude models:
- Claude Opus 4.7, 4.6, 4.5, 4.1, 4
- Claude Sonnet 4.6, 4.5, 4
- Claude Haiku 4.5, 3.5

Availability by platform:
- Claude API: supported
- Azure AI Foundry: preview
- Amazon Bedrock: coming
- Google Vertex AI: coming

---

## Example: Multi-Turn Conversation with Automatic Caching

```python
import anthropic

client = anthropic.Anthropic()

# First request: establish cache
response1 = client.messages.create(
    model="claude-opus-4-7",
    max_tokens=1024,
    cache_control={"type": "ephemeral"},
    system="You are a helpful assistant that remembers our conversation.",
    messages=[
        {"role": "user", "content": "My name is Alex. I work on ML."},
    ],
)
# cache_creation_input_tokens > 0, cache_read_input_tokens = 0

# Second request: cache hit on system + first message
response2 = client.messages.create(
    model="claude-opus-4-7",
    max_tokens=1024,
    cache_control={"type": "ephemeral"},
    system="You are a helpful assistant that remembers our conversation.",
    messages=[
        {"role": "user", "content": "My name is Alex. I work on ML."},
        {"role": "assistant", "content": "Nice to meet you, Alex!"},
        {"role": "user", "content": "What do I do?"},
    ],
)
# cache_read_input_tokens > 0 (system + first exchange)
# cache_creation_input_tokens > 0 (new assistant + user messages)
```
