---
title: Agentic Infrastructure Manifesto
created: 2026-04-17
updated: 2026-04-17
status: active
tags: [architecture, doctrine, agentic-infrastructure, design-principles]
---

# Agentic Infrastructure Manifesto

This document defines the architectural doctrine for building infrastructure that is operated by AI agents as a first-class concern — not as an afterthought bolted onto human-oriented systems. It captures the durable principles and design patterns that govern how we build, document, expose, and evolve edge infrastructure.

These principles are technology-agnostic. They apply whether the agent is a 4B parameter model running on a Jetson, a cloud LLM connecting over MCP, or a Claude Code session executing a mission in a container. They apply whether the infrastructure is a metrics collector, a data pipeline, or a camera capture system. The principles came from building and operating production systems; they are descriptive of what works, not prescriptive of what sounds good.

RF-Edge is the reference implementation. When this document describes a principle in the abstract, RF-Edge is where that principle takes concrete form. The architecture specification (`ARCHITECTURE.md`) defines the implementation; this manifesto defines the doctrine that governs it.

---

## Part I: Foundational Principles

### 1. Architectural Incapacity, Not Behavioral Restriction

Every security and safety system in computing history is behavioral restriction. Firewalls inspect and decide. RLHF trains a model to prefer not doing dangerous things. Every one of them CAN do the bad thing but has been told not to.

An agent operating infrastructure should be unable to perform actions outside its scope because those actions are not representable in its vocabulary. A calculator cannot write poetry — not because it refuses, but because it has buttons for numbers and operators and nothing else.

Implementation: each agent definition is a file on disk containing a system prompt and a list of tools it is allowed to call. The tool set IS the permission model. The diagnostic agent cannot restart a container because the restart tool is not in its list. Not because it was told not to — because the tool does not exist in its universe.

No API keys stored on device. The key travels with the request from the operator's session and dies when the session ends. If the device is compromised, there is no key to steal. This is the same principle applied to credentials: the absence of a thing is more secure than the restriction of a thing.

This is the RISC principle applied to agent operations. A reduced vocabulary and strict scoping don't limit capability — they expand the semantic distance between any two valid actions. In a sparse vocabulary space, the gap between actions is large enough that the model cannot accidentally drift from one to another. Hallucination requires proximity. Remove the adjacency and you remove the failure mode.

### 2. The Daft Punk Principle

Every service, every operation, every tool must be expressible as a single imperative verb understood in under two seconds. Descriptions fall in the 8–32 token range. No system exceeds 32 composable operations.

This is not a style preference. It is a hard constraint derived from LLM context economics and validated by an unexpected source. Daft Punk's "Technologic" is a complete API for computer ownership: buy it, use it, break it, fix it, trash it, change it, mail, upgrade it. Thirty-two imperative verbs. Each one unambiguous. Together they are Turing complete for the problem space.

A data transport SDK does the same thing: create it, load it, ship it, store it, attach it, observe it, dump it. Twelve verbs. The entire pipeline for a medical device inspection system — three cameras at 5000 Hz, 36000-pixel line scans, tiled inference — can be written in ten lines using those verbs. The complete SDK surface fits in 100 lines. Every method, every parameter, every default. If an agent reads those 100 lines, it knows everything. It cannot hallucinate a method that doesn't exist because the list is exhaustive. It cannot call an operation outside its scope because the vocabulary doesn't contain the words for it.

The test: if you can't explain what a tool does to a colleague in the time it takes to walk past their desk, the tool is too complex or too poorly named. Rename it, split it, or remove it.

### 3. The Pit of Success

When the correct path and the easy path are the same, engineers don't need discipline to take it. They fall into it.

This applies to infrastructure defaults, documentation conventions, config file structure, and agent design patterns. The golden repo ships with the right GigE kernel tuning, the right Docker network mode, the right TRT engine caching, the right atomic write patterns. A new deployment forks from these defaults. Deviating from the default requires effort; following it requires none.

The same principle applies to agent operations. The diagnostic cron runs the SOP checklist in order because that's the only thing the mission file tells it to do. It doesn't skip steps because there is no "skip" in its vocabulary. It doesn't improvise because improvisation requires tools it doesn't have. The correct execution path is the only representable execution path.

### 4. Pouring Concrete

Infrastructure matures through three phases: hacking through grass (ad-hoc solutions to immediate problems), worn paths (patterns that emerge from repeated use), and poured concrete (standardized infrastructure that encodes those patterns permanently).

The goal is not to pour concrete prematurely — that creates bureaucracy without value. The goal is to recognize when a path is worn enough that standardization serves everyone. The signal: when two or more deployments have independently solved the same problem, that solution belongs in the golden repo.

Every field problem solved once is tribal knowledge. Solved twice is a pattern. Solved three times and not codified is a failure of infrastructure.

### 5. Open Core, Paid Services

The platform layer is open source. It provides infrastructure composition, deployment topology, and an application framework that works without any licensed components. A customer who doesn't want to pay for licensed services can still deploy the platform — they just wire up their own metrics, their own data transport, their own image storage. There is no vendor lock-in at the platform layer.

Licensed services make it fast and easy. They are not load-bearing walls. Each licensed service is independently deployable. A customer can run telemetry without data transport, or data transport without telemetry. The platform composes them but does not require any of them. Removing a licensed service is deleting a stanza from the compose file — no submodules to decouple, no source code to extract.

The litmus test: `git clone` the platform repo, `docker compose up`, and you get a running stack with infrastructure and a control plane. No licensed services required. Adding one is a one-line change to the compose file and a `pip install` of its SDK.

This matters for agents because agent-native infrastructure must be inspectable. An agent (or the engineer configuring it) needs to understand the full system from platform through services to application. An open platform layer means the agent can read the composition, trace the wiring, and understand the topology. Black boxes at the platform layer make the whole system opaque to agents operating on it.

### 6. Single Ownership

Every database table, every Redis keyspace, every shared memory region, every storage bucket has exactly one owner. Other services may read or write through the owner's SDK, but schema and lifecycle belong to one service.

This is how you prevent the distributed monolith. If two services write to the same table, schema changes require coordinating both services. If one service owns the table and exposes a query contract, schema changes are internal. The owner updates the contract; consumers call the contract. The coupling is at the interface, not the implementation.

For agents, single ownership means every piece of state has exactly one service responsible for explaining it. When an agent queries a metric, the telemetry service owns the explanation of what that metric means, how it's aggregated, and what its normal range is. There is no ambiguity about who to ask.

---

## Part II: Design Patterns

### 7. Config as Control Surface

A configuration file is not a startup artifact that gets parsed once and forgotten. It is a live control surface — an API exposed as a file on disk.

Every service watches its config file via inotify. When the file changes, the service re-reads it, diffs against its running state, and propagates changes to affected subsystems without restarting. This makes every service an oscilloscope: an agent or operator can crank collection frequency up during debugging and dial it back down, all by editing a bind-mounted file.

Config files are bind-mounted from the project directory into containers. They live in `config/` in the project tree, tracked by git, visible to every tool that can read files. A remote agent reads them through MCP tools. A local agent reads them directly from the filesystem. A human reads them over SSH. Same file, same path, same content.

Not all fields are hot-reloadable. Timing parameters (sample rates, aggregation windows, thresholds) reload without restart. Connection parameters (database host, Redis URL) require a restart. Identity parameters (device ID) require a restart. The config file documents which fields are hot-reloadable and which are not, because the agent reading the file needs to know whether editing a value will take effect immediately or require a follow-up `restart_service` call.

### 8. Config as Diagnostic Manual

The config file is the first document an agent reads. If the diagnostic guidance lives in the config comments, the agent doesn't need a separate SOP document for basic troubleshooting — the config IS the SOP.

Every configurable section carries a structured comment block:

**What it monitors.** One sentence. The data source and mechanism.

**What normal looks like.** Expected ranges specific to the target hardware.

**What abnormal looks like.** Failure signatures this section can reveal.

**How to investigate.** What to turn and where to look.

**Cross-references.** Related config sections or system artifacts.

The config file simultaneously serves as parameter reference, tuning interface, and diagnostic runbook. When an agent reads the config, it learns the system's vocabulary, its expected behavior, its failure modes, and the investigation procedure — all from one file it was going to read anyway.

### 9. Three-Tier Diagnostic Model

Every deployment runs three tiers of diagnostic intelligence, escalating in capability and cost:

**Tier 1 — Passive.** A lightweight classifier runs continuously on the CPU, consuming metrics produced by the telemetry layer. Its job is pattern recognition: convert time-series data into a classifiable representation (e.g., Gramian Angular Difference Fields for CNN classification, convex hull boundary monitoring for geometric anomaly detection), evaluate it against known-good baselines, and flag anomalies. Tier 1 runs 24/7 at negligible compute cost.

**Tier 2 — Active.** A small local model performs multi-step diagnostic reasoning. It receives an anomaly flag from Tier 1 (or runs on a cron schedule), calls scoped MCP tools to investigate, and returns a structured verdict. No cloud dependency. No API key. No network requirement.

**Tier 3 — Intervention.** A cloud model handles complex investigations that exceed Tier 2's reasoning capacity and any operation that changes device state.

**The self-training loop.** Every Tier 3 diagnostic produces a structured trace. That trace is simultaneously an operational result, a training example for Tier 2, and institutional knowledge that persists when engineers move on. The more missions Tier 3 runs, the better Tier 2 gets.

### 10. Three Classes of Agent

**Remote sessions.** A cloud LLM connecting via MCP to the control plane. Tier 3 agent. Sees the system through the MCP tool surface only.

**Containerized agents on-device.** A code execution environment running ephemerally on the edge device. Can read configs, inspect logs, run shell commands within container scope.

**Local model agents.** A small LLM running permanently on-device as the Tier 2 diagnostic engine. Most constrained: smallest context window, weakest reasoning. Design for this agent; the stronger ones benefit for free.

### 11. Disruptive vs. Destructive

The trust boundary for agent operations is not read vs. write. It is disruptive vs. destructive.

**Disruptive** operations can interrupt service but the system self-heals on restart. Recoverable.

**Destructive** operations cause permanent state loss. Not recoverable without backups.

Any agent can perform disruptive operations through MCP. Destructive operations are absent from the vocabulary.

### 12. Ephemeral Execution, Persistent Artifacts

Agent sessions are ephemeral. Each mission starts clean, executes, produces a result, and terminates. What persists are the artifacts: files written, configs applied, traces captured, logs committed. The agent's memory is external — it lives in files, not in conversation history.

### 13. Documentation Is the API

For an agent, documentation is not supplementary. It is the primary interface.

**The 100-line rule.** The complete operational surface of any service fits in 100 lines.

**INDEX files at every level.** Every directory has an INDEX that describes what it contains.

**Token-efficient formatting.** Tables for parameters. No prose where a table suffices.

**Self-documenting artifacts.** Config files contain diagnostic guidance. SOPs map to tool calls. Sprint plans are executable mission files.

### 14. Thin SDKs, Fat Services

Python SDKs are thin clients. All lifecycle management runs in Rust containers. The SDK's job is to hand data to the service and get out of the way.

### 15. Birth/Data/Death Lifecycle

All SDK-to-service communication follows three phases with background heartbeats: Birth (announce, allocate), Data (emit, non-blocking), Death (flush, reclaim). Crash recovery via heartbeat timeout.

---

## Part III: System Architecture

### 16. The MCP Surface

Every service exposes capabilities through a single MCP server. Closed vocabulary. Structured returns. Idempotent reads. Scoped by service. Dynamic discovery via health keys.

### 17. The Config Volume

All service configuration lives in `config/`. Flat structure. Services mount read-only. Control plane mounts read-write.

### 18. Specification-Driven Development

Components are defined by behavioral contracts before implementation. The sprint system formalizes this: strategy → design → missions → execution → artifacts. Knowledge flows through documents on disk.

### 19. Ecosystem Position

Agentic infrastructure occupies the layer between hardware and application. The hardware vendor builds the brain. The application developer builds the senses. The agentic infrastructure is the nervous system.

---

## Part IV: Existence Proof

Validated on production hardware: NVIDIA Jetson AGX Orin (64GB), three Lucid Triton2 GigE cameras at 5000 Hz, medical device inspection, $600/minute downtime cost.

NemoTron Nano 4B: 3.5B active params, 2.8 GB VRAM, 25.7s end-to-end diagnostic, 31.5 tok/s. Handles six of eight troubleshooting scenarios in under 15 seconds.

NemoTron Nano 30B: diagnoses cascading failures. Identified Redis outage, traced DNS resolution cascade, recommended recovery autonomously. Fully on-device. No cloud.

---

## Part V: What This Is Not

Not a monitoring platform. Not a chatbot. Not a replacement for human judgment. Not cloud-dependent. Not technology-specific.
