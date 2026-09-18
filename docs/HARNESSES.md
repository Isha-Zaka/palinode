# Using Palinode from any harness

Palinode is one memory backend with several ways in. Your memories live in one
place — markdown files, git-versioned, indexed by one API server — and every
agent harness you use connects to that same store. Switch editors, run three at
once, move between machines: the memory follows you, not the tool.

This page is the map: what each harness gets, how deep the integration goes,
and where to start.

## Three integration tiers

Every integration is a thin client of the same REST API — no harness gets a
private fork of the capability set. What differs is how much of the memory
loop runs automatically:

| Tier | What runs without you asking | Where |
|------|------------------------------|-------|
| **Native hooks** | Session starts primed with core memories, relevant memory recalled before each prompt, and an eligible session-end floor can be submitted | Claude Code |
| **Native plugin** | The same full loop, wired into the harness's own extension API | Pi, Cline, OpenClaw |
| **MCP** | Explicit tools — the agent searches and saves when it decides to | Everything that speaks MCP |

The tiers stack. Claude Code users typically run hooks **and** MCP: hooks make
memory ambient, MCP tools let the agent dig deeper on demand.

## What each harness gets

| Harness | Tier | Setup |
|---------|------|-------|
| **Claude Code (CLI)** | Hooks + MCP | `palinode init` in your project — scaffolds everything below |
| **Claude Desktop** | MCP | `palinode mcp-config --stdio` → paste into its config |
| **Pi** | Native extension | [plugins/pi/README.md](../plugins/pi/README.md) — per-turn recall, priming, capture |
| **Cline (CLI / SDK)** | Native plugin | [plugins/cline/README.md](../plugins/cline/README.md) — per-turn recall, priming, capture; `cline plugin install` |
| **OpenClaw** | Native plugin + MCP | see the plugin's install guide ([plugin/INSTALL.md](../plugin/INSTALL.md)) |
| **Cursor** | MCP + rules file | `palinode mcp-config --stdio`; `palinode init` also writes `.cursor/rules/palinode.md` |
| **Windsurf** | MCP | `palinode mcp-config --stdio` (or `--http` for a remote server) |
| **Zed** | MCP | `palinode mcp-config --http` |
| **VS Code (Cline / Continue)** | MCP | [MCP-INSTALL-RECIPES.md](MCP-INSTALL-RECIPES.md) — the Cline VS Code extension does not load `AgentPlugin`s yet |
| **Codex CLI** | MCP + AGENTS.md | `~/.codex/config.toml`; `palinode init` appends a memory block to `AGENTS.md` |
| **Antigravity** | MCP + AGENTS.md | native MCP menu; same `AGENTS.md` block |
| **JetBrains (AI Assistant)** | MCP | [MCP-INSTALL-RECIPES.md](MCP-INSTALL-RECIPES.md) |

Per-client config file locations: [MCP-CONFIG-HOMES.md](MCP-CONFIG-HOMES.md).
If a setup misbehaves, `palinode mcp-config --diagnose` shows every config file
your clients actually read.

## Flagship first-session proof

The two supported first-use paths are deliberately different. They share one
memory store and one sample, but only the Claude Code path has lifecycle hooks.
Do not treat an installed MCP server as a hook.

| Path | Start | During a prompt | Exit | Required setup |
|------|-------|-----------------|------|----------------|
| **Claude Code — hooks + MCP** | `SessionStart` provides its bounded digest automatically. | `UserPromptSubmit` can inject relevant trigger/search context; use MCP tools for a focused lookup or save. | `SessionEnd` attempts a minimal snapshot automatically when its floor applies; an agent-authored `palinode_session_end` is the richer explicit path. | First run `palinode controls status`, then run `palinode init --hook` in the project and approve the generated `.mcp.json` and `.claude/settings.json` hooks. |
| **Codex CLI — MCP + project instructions** | MCP connects, but it does not recall a decision on its own. | The project `AGENTS.md` must tell the agent to call `palinode_session_init`, then `palinode_search` when it needs an answer. | The agent must explicitly call `palinode_session_end`. | Add the MCP server through Codex's normal configuration and run `palinode init --agents` in the project. |

Client-owned memory may remain enabled in either client. Palinode is a separate,
auditable markdown store; it neither reads nor disables the client's own memory.
The release trial records whether both were enabled and what was observed. A
transport check alone cannot establish model behavior or coexistence.

### Shared harmless sample

Use project **`harbor-notes`** in a disposable project and store. The sample
contains no real user memory.

1. In session A, save this decision with its rationale: **“Use SQLite for the
   local prototype because it runs as a single-user desktop app.”**
2. Start a genuinely fresh session. Do not paste the answer into the prompt.
   Ask which storage choice fits the local prototype; retrieve the decision and
   read its source.
3. Save the explicit correction: **“Use PostgreSQL for the shared hosted
   service because concurrent writers need transactional coordination.”** Link
   it to the initial record, then supersede the initial record.
4. Start another fresh session and ask about the shared hosted service. It must
   retrieve PostgreSQL and show the linked source rather than silently choosing
   between records.

Also save **“Store event timestamps in UTC.”** and confirm it remains current.
For the conflict demonstration, save both a north-region and a south-region
deployment decision as contradictory records. Leave the conflict unresolved:
the client must report the disagreement, not invent a winner.

For the smallest reliable path, configure the store for lexical retrieval and
ask the agent to use `palinode_search` with the distinctive wording from the
decision. Lexical mode is an explicit configuration, not an automatic fallback
when hybrid embedding is unavailable. Embedding, chat, and consolidation are
optional and are not prerequisites for this proof.

### Prompts for the two paths

Claude Code's hooks make the first digest and prompt-time recall automatic
after setup. Use a fresh-session prompt such as: “For Harbor Notes, what
storage choice applies to the shared hosted service? Search Palinode and cite
the record you use.” This asks for an auditable lookup without supplying the
answer.

Codex CLI needs the same instruction explicitly in `AGENTS.md`: “At session
start call `palinode_session_init`; before answering a Harbor Notes storage
question call `palinode_search`; read the selected record for its source; at
the end call `palinode_session_end`.” The equivalent fresh-session prompt is:
“For Harbor Notes, determine the storage choice for the shared hosted service
from Palinode. Use the evidence you retrieve.”

The proof must be run once from the primary checkout and once from a linked
worktree after restarting the Palinode service. A linked worktree should resolve
to the same project; if it does not, stop and diagnose scope rather than adding
an arbitrary project override. Observe the `SessionEnd` floor separately: it
uses the basename of its `cwd`, so it can name the linked-worktree directory
rather than the primary checkout's project. Restarting a service is an
operational action, not a claim made by this guide.

### What a failure means

| Observation | Check first | Next safe action |
|-------------|-------------|------------------|
| Save fails | tool response and path validation | Correct the request; do not claim a file was saved. |
| Save succeeds but search misses it | `indexed`, `indexed_vec`, and `indexed_fts` in the save receipt | Wait for/re-run normal indexing; use the supported lexical query only after FTS is healthy. |
| Tools are absent or disconnected | the client's normal MCP listing/health view | Repair that client's configuration; do not edit another client's global config. |
| Fresh session has no project scope | session-init/prime output | Check the checkout or linked-worktree resolver before asking broader recall. |
| Search says no relevant memory | query the exact sample wording | Record the abstention; do not paste an answer or call it a recall success. |
| Embeddings are unavailable | search mode/receipt | Record the hybrid-mode failure. Only describe a lexical result when lexical mode was configured explicitly; it is separate from a semantic or model-session result. |

## Capture controls and what they cover

Before enabling automatic capture, run `palinode controls status`. It asks the
server for the effective policy and makes a content-free capture preflight; its
JSON form is suitable for a setup checklist. It reports observed generated hook
files/configuration separately from running-client state, which remains unknown
unless the client itself reports it. It also distinguishes Palinode-managed API
traffic from model/provider traffic managed by the client.

`palinode controls pause` pauses both future capture and recall requests routed
through the Palinode API. Use `pause --no-recall` for capture only, or
`pause --no-capture` for recall only; `resume` accepts the same selectors. Pauses do not stop background indexing,
enrichment, or consolidation; direct-file legacy clients; in-flight requests;
context already delivered to a client; or client-native memory and model
traffic.

`palinode controls exclude-project PROJECT` and `exclude-path PATH` exclude one
bounded project/path from automatic capture and recall; use `--remove` to undo
either. Exclusions intentionally do not refuse explicit saves or recalls, and
their tested scope does not constitute a general secret detector. A
failed/old/malformed policy preflight should make an automatic hook or client
decline capture or recall rather than fall through to a legacy path.

For the Claude Code fixture, transcript-derived floor capture is opt-in through
the selected hook setup, requires an eligible SessionEnd transcript, and stores
only a message count plus a truncated first-prompt topic hint—not a full
transcript import. Codex CLI MCP and `AGENTS.md` instructions do not turn on
transcript capture. Native plugins have their own lifecycle APIs, so the CLI can
only report their configuration if exposed; it cannot certify they are running.

Use the harmless sequence `controls pause` → inspect the local
[UI](UI.md)/`history` → attempt a new capture or recall and observe the policy
denial → `controls resume`. The fictional Harbor Notes walkthrough above remains
the recall proof; it is not a human-trial claim about pause or exclusion success.

## The full loop, on Claude Code

Claude Code is the deepest integration today because its hook system covers
the whole session lifecycle. After `palinode init`:

1. **Session start** — the `SessionStart` hook injects a bounded digest of
   your `core: true` memories, so the session begins already knowing your
   standing context.
2. **Every prompt** — the `UserPromptSubmit` hook checks your prospective
   triggers (`palinode_trigger`) and runs a strict-threshold search over the
   prompt, injecting compact snippets *before the model answers*. Nothing
   relevant → it says nothing.
3. **On demand** — the MCP tools (`palinode_search`, `palinode_read`,
   `palinode_save`, …) are there when the agent wants more than the ambient
   layer surfaced.
4. **Session end** — the `SessionEnd` hook can submit a minimal floor snapshot
   on its configured end reasons. It requires a transcript, at least three user
   messages, and no existing `palinode_session_end` call; it uses the checkout
   basename as the project and only the first prompt's topic/count. It is not a
   guarantee that every session is captured, and the explicit tool call remains
   the richer record.

Tuning knobs for all three hooks: [examples/hooks/](../examples/hooks/).

### Why injected memory lands in the conversation, not the system prompt

Model providers cache your prompt as a strict prefix: tools, then system
prompt, then messages. Change one byte early in that prefix and everything
after it is re-processed — and re-billed — from scratch. Per-turn memory
injected into the *system prompt* would do exactly that, every turn.

Palinode's hooks inject into the **conversation** instead, after the cached
prefix. The recall arrives fresh each turn; the expensive stable prefix stays
cached. Every native plugin follows the same rule — the Pi and Cline plugins
share one core (`plugins/core`) whose only injection output is a message
body, and each plugin's test suite pins that it never lands in the system
prompt.

## Same contract everywhere

Whatever the tier, the memory contract is identical, because everything calls
the same API:

- **Save with rationale** — decisions carry their why (`palinode_save`).
- **Recall is search, not scrollback** — hybrid keyword + semantic search
  over everything you've ever saved (`palinode_search`).
- **Sessions end captured** — `palinode_session_end` (or the Claude Code
  floor hook) writes the session's outcomes where the next session will find
  them.
- **Everything is auditable** — files + git means `diff`, `blame`, and
  `rollback` work on your agent's memory like on your code.

A memory saved from Cursor is findable from Claude Code, from a cron job via
the CLI, from OpenClaw — the harness is a doorway, not a silo.

## More native integrations

The plugin architecture is deliberately thin — a native integration is an
adapter over the REST API, not a reimplementation — so support for more
harnesses with lifecycle hooks is planned. If your harness of choice exposes a
pre-prompt hook and you want Palinode wired into it, open an issue.
