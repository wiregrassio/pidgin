# [Sprint Name] — Design

## Goal

One paragraph. What this sprint produces and why. The problem it solves
or the capability it adds. No implementation detail.

## Current State

What exists today. What works, what does not, what is missing. Cite
files and modules where relevant. This is the "before" picture.

## Target State

What the repo looks like after this sprint completes. New files, new
modules, new capabilities. The "after" picture. An agent reading this
alone should understand what success means.

## Decisions

Numbered list of the architectural decisions the sprint commits to.
Each decision: one heading, a few sentences of rationale, and (if
relevant) what alternatives were considered and rejected.

### Decision 1: <title>
<rationale>

### Decision 2: <title>
<rationale>

---

Place reference material (principles, style guides, API specs, external
docs the sprint must conform to) under `context/`. The sprint writer
reads from `context/`, not from external paths. This is the structural
fix for the co-location problem — a sprint package is self-contained.
