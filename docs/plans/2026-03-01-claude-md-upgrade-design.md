# Design: CLAUDE.md v2 Upgrade
**Date**: 2026-03-01
**Status**: Complete

## Problem
The existing CLAUDE.md covered craft principles (SOLID, DRY, Clean Code, DDD) well but lacked:
- Explicit context management strategies
- Structured planning protocol
- Subagent usage patterns
- Gated debugging (anti-blind-spot) protocol
- Verification gate before claiming completion
- Self-hygiene rules to keep the file lean

## Sources Consulted
- Anthropic official Claude Code best practices docs
- claude.com blog on CLAUDE.md file techniques
- Context engineering research (01.me/en/2025/12/context-engineering-from-claude)
- PubNub subagent pipeline best practices
- awesome-claude-code community patterns (hesreallyhim/awesome-claude-code)
- ykdojo/claude-code-tips (45 community-sourced tips)

## What Changed

### Added (New Sections)
| Section | Content |
|---------|---------|
| §2 Context Management | Context rot taxonomy, /compact instructions, HANDOFF.md pattern, session naming |
| §3 Planning Protocol | Explore→Plan→Implement→Commit cycle, spec-first interview pattern |
| §4 Subagent Strategy | When/how to use, Writer/Reviewer, permission hygiene, hook-based chaining |
| §5 Debugging — Gated Analysis | 5-gate protocol replacing the old §1.1 hint, blind-spots checklist |
| §7 Verification Before Ship | Required evidence per task type |
| §8 CLAUDE.md Self-Hygiene | Line budget, prune triggers, skills-over-prose rule |
| Quick Reference | Decision tree at a glance |

### Kept (Condensed)
- §0 Digest-First Rule — extended with HANDOFF.md check
- §1 Meta-Behavior — added verification gate
- §6 Core Craft — SOLID, DRY/KISS/YAGNI, Clean Code, DDD condensed ~40%

### Removed
- Verbose sub-bullet explanations for each SOLID principle (now single-line each)
- Redundant "How to apply" headers (folded into the bullet)

## Key Design Decisions
1. **Sections 2-5 are the power upgrade** — they address the user's four stated gaps
2. **§5 Debugging is now a formal protocol** not a "posture" hint — gates prevent blind patches
3. **Context management is placed before planning** — it's the fundamental constraint
4. **Quick Reference tree at end** — gives Claude an instant decision path without re-reading everything
5. **Line count ~251** — slightly over the ideal 200 but every line is load-bearing; candidate for @import offload next iteration
