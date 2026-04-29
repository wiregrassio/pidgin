# XML Prompt Format

All Pidgin prompts and stored artifacts should be XML-tagged documents, not markdown files. This is not a style preference — it is a structural decision grounded in how Claude (and LLMs generally) process input.

## Anthropic's Guidance

From the official Claude prompting documentation: "Claude was trained specifically to recognize XML tags as a prompt organizing mechanism." XML tags help Claude "parse prompts more accurately, leading to higher-quality outputs" especially when prompts involve multiple components like context, instructions, examples, and variable inputs.

Best practices from Anthropic:
- Use consistent, descriptive tag names across prompts
- Nest tags for hierarchical content
- Combine XML tags with multishot prompting and chain-of-thought
- For long-context prompts (20k+ tokens), put longform data at the top inside document tags, with the query at the end — queries at the end improve response quality by up to 30%

Source: https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-prompting-best-practices

## What Changes

### 1. Prompt Templates

V2's `generate.md` is 960 lines of markdown. v0.2 rewrites it as an XML document. The structure:

```xml
<pidgin_prompt verb="converge" doc_type="function_description">
  <role>...</role>
  <principles>
    <principle id="1">MLD-compressed principle text</principle>
  </principles>
  <rules>
    <rule id="1">Begin with an imperative verb</rule>
  </rules>
  <examples>
    <example type="positive">
      <input>...</input>
      <output>...</output>
    </example>
    <anti_example source="v1_validation">
      <output>...</output>
      <reason>...</reason>
    </anti_example>
  </examples>
  <payload>
    <function file="..." name="..." line_start="...">
      <!-- function body -->
    </function>
  </payload>
  <output_schema>
    <field name="draft_1" type="string"/>
    <field name="draft_2" type="string"/>
    <field name="draft_3" type="string"/>
  </output_schema>
</pidgin_prompt>
```

The cached preamble is everything above `<payload>`. It is identical for every function description compression call. The payload varies per call. The caching boundary is explicit in the document structure.

### 2. Stored Artifacts

Documents in the nest should be XML strings, not markdown. When `section_get` returns a `function_description`, it returns an XML fragment. When `preamble.assemble()` builds a sprint runner's context, it assembles XML blocks.

### 3. Sprint Plans

A sprint plan section becomes:

```xml
<mission index="4" tier="reason">
  <goal>...</goal>
  <description>Natural language description</description>
  <compressed>Pidgin-compressed description (pass 2)</compressed>
  <implementation>Generated code (pass 3)</implementation>
  <validation>Sprint writer validation notes (pass 4)</validation>
</mission>
```

Each Pidgin pass knows which tag to read and which to write. No markdown header parsing. No regex.

### 4. Source Code Annotations

Source files get XML boundary markers in comment blocks:

```python
# </function_body>
# <mld target="extract_ast" confidence="1.0" budget="16">
# Parse the source file into an AST and return all public function nodes.
# </mld>
# <function_body file="parser.py" name="extract_ast" line="47">
def extract_ast(source: str) -> list[ast.FunctionDef]:
    ...
```

Not deeply nested. Boundary markers only. The LLM reading the file sees clean structure: this is the description, this is the code, these are the metadata attributes. Pidgin's update verb knows which tags to read and write.

## Why Not Markdown

Markdown headers are visual formatting that LLMs must infer structure from. XML tags are explicit structure that LLMs parse directly. In a crowded context window — a sprint preamble with six principles, a mission spec, function bodies, output schemas — XML tags create unambiguous boundaries. Markdown's `##` headers create ambiguous boundaries: is "## Rules" a section header or the title of a rule about headers?

Markdown can exist inside XML tags. The content of a `<description>` tag can contain markdown formatting. The structure is XML; the prose is whatever serves the content.

## Migration Path

V2's existing markdown prompts and artifacts work. The migration is:
- Rewrite `generate.md` as an XML prompt template
- Update `section_put` to store XML-formatted documents
- Update source annotation logic to use XML tags instead of V1's bare XML tags
- Update sprint plan templates to use XML structure

This is a prompt engineering sprint that touches every template but no pipeline logic.
