# Roadmap

**Status:** usable, actively developed, pre-1.0.
See the [latest release](https://github.com/phasespace-labs/palinode/releases/latest)
and [changelog](docs/CHANGELOG.md) for shipped behavior.
**Direction reviewed:** September 2026.

This is a sequence of planned outcomes. The features and targets below are not
claims about the currently installed version, and no delivery dates are promised.

## The developer outcome

**Project memory you can inspect, correct, and carry between coding agents.**

The initial audience is developers returning to the same repositories over many
sessions, often using different agents and git worktrees. Palinode should preserve
the reason behind a decision, help an agent avoid an approach that already failed,
and carry a confirmed correction into the next session.

Developer usefulness and adoption guide the sequence. The ambition to be a
reference implementation of auditable memory supports that goal: readable records,
explicit evidence, validated changes and recoverable history make memory easier
to trust and improve.

## User trust across every release

Developers should understand what Palinode remembers, where it sends content,
what an agent received, and how to stop or correct future use. These are planned
acceptance requirements alongside usefulness:

| Release | What users must be able to understand and control |
|---|---|
| v0.21 | See active capture, project scope and configured data destinations; pause capture and disable future recall; understand the actual privacy/access boundary. The promoted inspector must honor that boundary. |
| v0.22 | Correct or stop using a memory, inspect retained copies and recover from mistakes. Distinguish source integrity, factual certainty and agent behavior; test resistance to poisoned memory and report limitations. |
| v0.23 | Review exactly what is shared, inspect an import before accepting it, and understand that copying memory gives the recipient an independent copy. Imported content grants no instruction authority. |
| v0.24 | Preview changes to defaults, authority and retention; verify migration, rollback and rebuild without silently widening capture or access. |

The first-use and follow-up studies will observe whether people can operate these
controls and explain their limits. Unexpected capture, unwanted recall, wrong scope,
confusing certainty and inability to recover become named failures to address.
Known unauthorized disclosure or mutation in an advertised path must be fixed or
that path disabled or removed before release or promotion.

Archive/forget controls and physical erasure have different effects on retained
history. The [data lifecycle guide](docs/DATA-LIFECYCLE.md) describes the current
operations and limits; the planned work will verify that workflow and make it
understandable from first use. Auditability alone cannot establish that a claim is
true or that every copy can be erased.

## v0.21 — Successful first use

Make the complete journey dependable:

1. Install through one canonical guide and connect a supported editor with
   configuration that resolves the executable actually installed.
2. Resolve the intended repository/project consistently from a main checkout,
   worktree or subdirectory, and expose an uncertain identity.
3. Save a harmless project decision with its rationale and retrieve it in a fresh
   session.
4. Open the existing inspector, find its source and history, explicitly correct
   the decision, and verify the replacement in another fresh session.

Explicit lexical retrieval now lets the first saved decision be found before
configuring an embedding service. Semantic retrieval and consolidation retain
their documented prerequisites.

Verify two flagship experiences deeply: Claude Code with hooks and MCP, and
Codex CLI with MCP and project instructions. Record actual client versions and
what happens automatically versus what needs an explicit tool instruction.
Broader MCP compatibility remains available with an honest capability matrix.

**Acceptance target:** recruit five unfamiliar developers for the self-run
first-use study, with at least four reporting that they completed the journey
without maintainer intervention. Record setup time, failures, declared
assistance, platform coverage and any unmet target. This is a planned study,
not an observed result or a measured conversion rate. Contributor CI and
release smoke checks must provide meaningful, reproducible feedback.

## v0.22 — Corrections that stick and useful recall

Prioritize the quality of the memory loop:

- Capture explicit corrections and rejected approaches with their rationale,
  source and project scope. Transcript access is opt-in and bounded.
- Review ambiguous replacement candidates; a later observation or repeated
  summary cannot silently overrule a decision.
- Shorten the path from inspecting a memory to previewing a correction,
  applying it through the existing validated write path, and recovering an
  earlier state when needed.
- Explain the context supplied to an agent using available delivery receipts,
  including sources, revisions, scope, conflict and coverage. Supplied context
  does not prove that an agent acted on it.
- Measure relevance, redundant or irrelevant injections, excerpt usefulness and
  abstention on realistic project questions. Preserve useful answers while
  reducing noise.
- Establish a bounded coexistence contract with native client memory, including
  conflicting records and duplicate capture.

**Evidence:** evaluate actual coding agents against simple project-memory files
and supported native-memory baselines. Report task outcomes, corrections followed,
old-decision reuse, source accuracy, token overhead, latency and failures
separately from the existing mechanical benchmarks.

Follow the consenting onboarding cohort for two weeks. Report continued use,
concrete useful-recall examples, reasons for disabling the tool and missing
follow-up. Use interviews and optional local diagnostics; a telemetry service is
not required. Review this evidence before broader promotion.

## v0.23 — Project handoffs and demonstrated adoption

Make selected project knowledge useful to another developer or agent:

- Preview and export reviewed project decisions, failed approaches and their
  evidence. Personal memory and the entire store are not the default selection.
- Import through validation with destination-scope mapping, lineage,
  collision handling and preserved corrections/conflicts.
- Demonstrate a recipient using the transferred decision in a real coding task.
- Prepare a short, reproducible demonstration of a correction carrying from one
  coding agent into a fresh session in another, with inspectable source/history.
- Use that evidence for a small number of relevant distribution channels, keeping
  listings and support claims aligned with the tested product.

Entry depends on the first-use and usefulness results. A successful demo is
evidence for its demonstrated behavior; it does not establish broad retention
or guarantee viral growth.

## v0.24 — Schema capabilities, gated by demonstrated need

Bi-temporal claim validity, an actionability axis, and a persistent queryable
injection ledger remain planned together for a coordinated design decision.

Each must first identify a concrete developer failure that existing records or
receipts cannot adequately solve. Compare a simpler solution, then decide the
incremental user benefit, defaults, legacy behavior, migration, rebuild,
rollback, retention and interface compatibility.

Only the approved bounded capabilities proceed. An explicit defer/no-go outcome
is valid; this version is a conditional planning bucket. Existing uncertainty,
scope and authority safeguards remain obligations throughout the earlier releases.

## Focus and pruning

Keep the first screen centered on a useful example and one setup path. Put record
schemas, search algorithms, transport inventories and advanced deployments in
supporting documentation.

The following do not belong to this release sequence without evidence that they
solve an observed developer need:

- broad knowledge-base/vault imports and browser capture;
- multimodal ingestion and additional native adapters;
- a new documentation platform or a replacement inspector;
- hosted services and fleet-scale infrastructure;
- new leaderboard campaigns or speculative abstractions.

Existing compatibility fixes and research can retain their own scope. A feature
does not become a release requirement merely because another memory product has it.

## Principles and stability

Markdown and git remain authoritative; the search index is rebuildable. Records
remain readable when services are unavailable, and changes remain inspectable and
recoverable.

Palinode stays local-first and editor-neutral. No mandatory Postgres, Redis,
message broker or hosted memory service is planned.

The record format is treated as the most stable surface. MCP semantics remain
stable while optional parameters may grow; Python internals are not a public API.
Breaking changes and required operator actions belong in the
[changelog](docs/CHANGELOG.md).

A portable specification for auditable records remains a longer-term direction,
supported by implementation evidence. The 1.0 decision depends on stable contracts
and a dependable developer experience.

## Influencing the sequence

Concrete experiences move this roadmap: what you attempted, what Palinode
remembered, what the agent did, and where you needed to intervene. Voluntary
reports of continued use or abandonment are especially useful.

See [CONTRIBUTING.md](CONTRIBUTING.md) for scoped ways to help.
