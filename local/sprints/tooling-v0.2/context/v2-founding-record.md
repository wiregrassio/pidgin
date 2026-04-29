# V2 Founding Record

Tooling V2 ran 16 missions (plus 4 surgical patches: 3a, 5b, 9a, 11b) across one sprint day. Total API spend across all missions: under $0.50. The sprint validated the production MLD pipeline, built the external documentation store, stood up four operator-facing skills, and processed Origami through its own compression algorithm.

## What V2 Proved

**Soft budgets work.** Replacing hard max_tokens caps with a generous ceiling (500 tokens) and conciseness instructions eliminated every truncation artifact V1 documented. The `apply()` function — which V1 compressed to the truncated fragment "Merge delta into a copy of state," — converged in V2 at "Merge delta into a copy of state, remove keys with None values, and return the new state." The model found its natural stopping point at the length where the description is lossless. 4/4 probes converged at confidence 1.00.

**Three-draft generation works.** A single Nano call producing three drafts at increasing refinement yields 15 candidates from 5 calls. Natural variation across draft tiers eliminates the degenerate-cloud problem V1 observed with single-draft generation at tight budgets.

**LLM validation gates work.** The Nano gate call ("is this description complete?") returned valid on all four V2 probes. The mechanical grammar filter was removed entirely — it rejected 0/140 candidates across all V1 runs. V2 replaced zero empirical value with a gate that makes semantic judgments.

**Structured outputs eliminate parse failures.** Response_format with JSON schemas replaced free-form JSON generation. The class of error where truncation produced partial JSON — documented in V1 — cannot occur when the API enforces the schema.

**ChromaDB as sole store works.** Amendment 2 dropped SQLite. All metadata lives as ChromaDB document metadata. Roundtrip, idempotency, version increment, metadata query — all verified. The sync bug class (WARNING 1 from the original self-review) was eliminated by having one store instead of two.

**Skills built in dependency order catch errors earlier.** /embed validated the vector store, /digest validated the MLD pipeline end-to-end, /dissect validated structured outputs and the store, /technologic was built on proven components. V1's mistake of building /technologic first — and discovering every pipeline flaw through a 937-line orchestration script — was not repeated.

**Origami compresses.** 19/19 principles converged. 16 at confidence 1.00, 3 at 0.80. Total cost: $0.0004. The MLD descriptions are semantically lossless — they preserve the constraint while stripping pedagogy, metaphor, and implementation examples. The operator validated specific compressions and confirmed the algorithm correctly distinguished principle from practice.

**GPT-4.1 nano is the correct generation tier.** Re-validated in V2 at 4/4 convergences, $0.006/probe. The model does not overthink pattern completion tasks.

## What V2 Disproved

**GPT-5 nano is wrong for MLD generation.** Amendment 3 switched to GPT-5 nano for its lower cached-input pricing ($0.005 vs $0.025/MTok). M5 produced zero candidates across all four probes — the reasoning model consumed ~1,472 tokens of internal deliberation before emitting any output, exhausting the 500-token max_tokens budget entirely. The model never entered the output phase. Root cause: reasoning models deliberate and respond from the same token budget. Pattern completion tasks don't benefit from deliberation. GPT-5 nano was dispatching a PhD to mop a floor. Reverted to GPT-4.1 nano. GPT-5 nano is not banned — it's wrong for this workload. Other workloads (coordinator planning, Marionette reasoning) may use it.

**CRISPR for everything is wrong.** M14 (Origami reprocessing) routed document generation through crispr_write — the hash-verified, git-bracketed surgical edit function. This produced 660 lines of Python to build a markdown file line-by-line, a seed-empty workaround for new files (crispr_write assumes files exist), and three git commits per new file instead of two. CRISPR is correct for surgical edits to existing files where you preserve surrounding content. It is wrong for creating new files from generated content, wrong for wholesale file replacement, and wrong for text compression output. The write model needs multiple modes.

**Operation-level git commits are too granular.** The git bracket (pre-write commit, post-write commit) wrapping each individual edit operation produces excessive commit noise. Stripping and rewriting comments on a single file might require 10-20 slice operations. The bracket should wrap the file, not each operation. One pre-write commit, all edits applied in memory, one post-write commit, one audit entry listing all operations.

**Voyage AI integration was unnecessary.** Amendment 1 killed Voyage before any mission touched it. The rationale for Voyage (MongoDB Atlas automatic embedding for Base Camp compatibility) solved a problem that doesn't exist — Base Camp has one operator. One embedding provider (OpenAI text-embedding-3-small, 256 dimensions) is simpler, validated, and sufficient.

**The legacy compatibility shim was wrong.** M6 preserved `_legacy_file_get` for V1 XML-tagged source files. M7 deleted it under Wildebeest Mode. Five indexed files, one operator, v0.1. There is no backwards. sections.py went from 176 to 48 lines (73% reduction) after the cleanup.

## What Outgrew V2

The following decisions and architectural insights emerged during V2 execution but were not in the sprint plan. They are the primary design inputs for v0.2.

**Pidgin as an identity.** The name, the tagline ("RISC for LLMs"), the verb vocabulary, the CLI shape, the `.pidgin/nest/` convention, the permission model (--read-only, --write-db, --write-source), the open source framing — all emerged during execution. Pidgin is not a module in tools/. It is the system that the V2 tools become when packaged.

**Four write modes.** Index (nest only, no source touch), Update (CRISPR surgical edits), New (create files from generated content), Compress (MLD-compress text to new artifact). Each mode has different commit semantics, different permission requirements, and different audit patterns.

**XML prompt format.** All Pidgin prompts and artifacts should be XML-tagged documents, not markdown files. Anthropic's official guidance confirms XML tags are the preferred structuring mechanism for Claude. The cached preamble, the variable payload, the output schema, the source annotations — all XML. Markdown can exist inside XML tags. The tags are the structure.

**Batch API dispatch.** OpenAI's Batch API offers 50% cost discount and separate, higher rate limits. MLD's workload — N identical preambles with varying payloads — is the ideal batch workload. Two-round-trip pattern: generation batch, then embedding batch. Auto-threshold: under 10 tasks synchronous, over 10 batch. Eliminates rate limiting entirely.

**Bidirectional MLD.** The convergence geometry doesn't know what it's converging on. Code→description (the V1/V2 use case) and description→code (sprint code generation) use the same algorithm. Non-convergence on the description→code direction means the spec is ambiguous. The Pidgin verb isn't describe or implement — it's converge.

**Origami compression as audience adaptation.** MLD applied to Origami principles strips pedagogy and preserves requirements. An LLM doesn't need metaphors, motivation, or "why" framing — it needs the constraint stated directly. The 0.80 confidence signals on three principles correctly identified cases where the boundary between principle and implementation guidance was ambiguous. The operator resolved all three in favor of the compression.

**Adaptive candidate counts.** If convergence is 4/5, accept. If 3/5, run 5 more candidates and retest against the full 10. Below 3/5, flag as non-convergent. Cheap insurance against false convergence.

**Nested nest discovery.** A parent repo containing sub-repos (fe-toolkit containing watchtower, switchboard, marionette) can discover nested `.pidgin/nest/` directories. `pidgin init` at the top level registers child nests as pointers. A query with namespace `.` searches all nests.

**Sprint plan as multi-pass Pidgin artifact.** A sprint plan is written in natural language, compressed with Pidgin, then has code generated from the compressed descriptions, then validated by the sprint writer. Each pass reads and writes specific XML-tagged regions. The document accumulates state across passes.

## Disposition

V2 is closed after M16 (integration validation). The sprint was honorable. The pipeline works, the store works, the skills work, Origami is compressed. The design outgrew the sprint at the write model, the prompt format, the batch dispatch, and the Pidgin identity. Those belong to v0.2.
