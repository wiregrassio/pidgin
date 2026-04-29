# Anthropic Strict Tool Use — Technical Reference

_Fetched 2026-04-23 from https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use and /define-tools_

Load-bearing for the ensemble primitive's convergence-check feature:
forcing Claude to emit a single JSON object that exactly matches a
schema is how we get `{valid: bool, token_count: int, reason: string}`
and `{description: string, token_count: int}` out of Haiku/nano and
majority-vote across parallel runs.

**The mechanism:** define one tool (e.g. `answer`), set `strict: true`,
set `tool_choice` to force that tool. The response's `tool_use.input`
is the schema-conformant JSON.

---

## Why Strict Tool Use Matters for Ensembles

Without strict mode, Claude might return incompatible types (`"2"` instead of
`2`) or missing required fields. The ensemble primitive majority-votes on
structured fields; type drift across N parallel runs poisons the vote.

With `strict: true`:
- Tool `input` strictly follows the declared `input_schema`.
- Tool `name` is always valid.
- Grammar-constrained sampling produces schema-conformant output with
  no retry loops.

---

## Defining a Tool

Each tool definition has four top-level fields:

| Parameter | Description |
|-----------|-------------|
| `name` | Must match regex `^[a-zA-Z0-9_-]{1,64}$` |
| `description` | Plaintext description of what the tool does, when to use it, how it behaves |
| `input_schema` | JSON Schema object defining the expected parameters |
| `input_examples` | (Optional) Array of example input objects, each valid against `input_schema` |

Optional properties: `cache_control`, `strict`, `defer_loading`,
`allowed_callers`.

### Minimal tool

```json
{
  "name": "get_weather",
  "description": "Get the current weather in a given location",
  "input_schema": {
    "type": "object",
    "properties": {
      "location": {
        "type": "string",
        "description": "The city and state, e.g. San Francisco, CA"
      },
      "unit": {
        "type": "string",
        "enum": ["celsius", "fahrenheit"],
        "description": "The unit of temperature"
      }
    },
    "required": ["location"]
  }
}
```

### Best practices for tool definitions

- Provide detailed descriptions (at least 3-4 sentences). This is by
  far the most important factor in tool performance.
- For complex schemas, add `input_examples` to show Claude concrete
  well-formed inputs (~20-200 tokens each).
- Consolidate related operations into fewer tools with an `action`
  parameter rather than many narrow tools.
- Use meaningful name prefixes when tools span multiple services.

---

## `tool_choice` — Forcing a Specific Tool

Four options:

| Option | Effect |
|--------|--------|
| `{"type": "auto"}` | Claude decides whether to call any tool (default when `tools` is provided) |
| `{"type": "any"}` | Claude must call some tool, its choice |
| `{"type": "tool", "name": "answer"}` | Claude must call this specific tool |
| `{"type": "none"}` | Claude cannot call any tool (default when `tools` is absent) |

When `tool_choice` is `any` or `tool`, the API prefills the assistant
message to force a tool call. The model will not emit natural language
before the `tool_use` block even if asked to.

**Critical for ensembles:** combine `tool_choice: {"type": "tool", "name": "..."}`
with `strict: true` to guarantee both that the tool is called AND that
inputs match the schema. This is the primary mechanism for structured
output.

**Prompt-caching interaction:** changes to `tool_choice` invalidate
cached message blocks (tools and system remain cached).

**Incompatibility:** `tool_choice: {"type": "any"}` and
`{"type": "tool", ...}` are NOT supported with extended thinking — only
`auto` and `none` work there. Claude Mythos Preview also does not
support forced tool use.

---

## Strict Mode — `strict: true`

### Enabling

Set `"strict": true` as a top-level property on the tool definition,
alongside `name`, `description`, and `input_schema`.

### Quick example

```python
import anthropic

client = anthropic.Anthropic()

response = client.messages.create(
    model="claude-opus-4-7",
    max_tokens=1024,
    messages=[{"role": "user", "content": "What's the weather like in San Francisco?"}],
    tools=[
        {
            "name": "get_weather",
            "description": "Get the current weather in a given location",
            "strict": True,
            "input_schema": {
                "type": "object",
                "properties": {
                    "location": {
                        "type": "string",
                        "description": "The city and state, e.g. San Francisco, CA",
                    },
                    "unit": {
                        "type": "string",
                        "enum": ["celsius", "fahrenheit"],
                    },
                },
                "required": ["location"],
                "additionalProperties": False,
            },
        }
    ],
)
print(response.content)
```

### Required schema idioms for strict mode

- `"additionalProperties": false` — must be present on every object
  schema
- `"required": [...]` — list fields that must appear
- `enum` — restricts string/integer to a finite set
- `format` — supported for string (e.g. `"format": "date"`)

### Response shape

```json
{
  "type": "tool_use",
  "id": "toolu_01A09q90qw90lq917835lq9",
  "name": "get_weather",
  "input": {
    "location": "San Francisco, CA"
  }
}
```

The `input` field is guaranteed to conform to `input_schema`.

### Guarantees

- Tool `input` strictly follows `input_schema`.
- Tool `name` is always valid (from provided tools or server tools).

---

## Data Retention & HIPAA

Strict tool use compiles `input_schema` into grammars using the same
pipeline as structured outputs. Compiled tool schemas are temporarily
cached for up to 24 hours since last use. Prompts and responses are not
retained beyond the API response.

Strict tool use is HIPAA eligible, but **PHI must not be included in
tool schema definitions**. Compiled schemas are cached separately from
message content and do not receive the same PHI protections.

Do not include PHI in:
- `input_schema` property names
- `enum` values
- `const` values
- `pattern` regular expressions

PHI may appear in message content (prompts and responses), which is
protected under HIPAA safeguards.

---

## Response Parsing (Python)

```python
response = client.messages.create(...)

# Find the tool_use block
for block in response.content:
    if block.type == "tool_use":
        answer = block.input  # dict, schema-conformant
        # e.g. answer == {"valid": True, "token_count": 14, "reason": "single imperative"}
        break
```

If `tool_choice: {"type": "tool", "name": "..."}` was set, there will
be exactly one `tool_use` block and no text blocks preceding it (the
assistant message is prefilled).

---

## Ensemble Pattern: `answer` Tool for Convergence Check

The design doc specifies two convergence-check prompts:
- describe: `{description: string, token_count: int}`
- audit: `{valid: bool, token_count: int, reason: string}`

Shape for the `answer` tool used in ensemble dispatch:

```python
ANSWER_TOOL = {
    "name": "answer",
    "description": "Emit the structured answer. Call this tool exactly once with your final response.",
    "strict": True,
    "input_schema": {
        "type": "object",
        "properties": {
            "description": {
                "type": "string",
                "description": "Single imperative sentence, 8-32 tokens, understandable by a non-engineer in under two seconds."
            },
            "token_count": {
                "type": "integer",
                "description": "Number of tokens in `description`."
            }
        },
        "required": ["description", "token_count"],
        "additionalProperties": False
    }
}

response = client.messages.create(
    model="claude-haiku-4-5",
    max_tokens=512,
    temperature=0.8,
    system=[
        {
            "type": "text",
            "text": DESCRIBE_PROMPT,
            "cache_control": {"type": "ephemeral"}
        }
    ],
    messages=[
        {"role": "user", "content": function_body}
    ],
    tools=[ANSWER_TOOL],
    tool_choice={"type": "tool", "name": "answer"}
)

# Parse
for block in response.content:
    if block.type == "tool_use":
        result = block.input  # {"description": "...", "token_count": N}
        break
```

Run this N times in parallel with different seeds/temperatures.
Majority-vote on a canonicalized form of `description` (or on the
tuple `(description, token_count)`). If k-of-N agree, return consensus.
Else escalate to Sonnet with the N candidates.
