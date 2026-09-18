# First-use participant script

**Status: NOT RUN — zero participants.** This is the self-contained script
for the fictional Harbor Notes first-use study. You run it alone, at your own
pace, on your own machine, and report what the run left behind. There is no
observer and no time limit. Scoring, expected outcomes, and answer keys live
with the maintainer and are deliberately not here; the
[protocol](FIRST-USE-STUDY.md) explains what is recorded and why.

**Before you start.** Note the current time in UTC; it is the one timestamp
you record by hand. Everything else is read back from files Palinode writes.
Use only fictional Harbor Notes material throughout: no real source, secrets,
prompts, or memories. The [Quickstart](QUICKSTART.md) **and the documents it
links to** in the checkout's `docs/` folder are the intended resources; you
may read all of them, as many times as you like, and following a link the
Quickstart gives you is not "assistance". If you use anything else — a web
search, a person, the source code, **or the coding client itself** — that is
fine, but say so in the report; it changes how the run is recorded, not
whether it counts. Asking
Claude Code or Codex to explain an error or suggest the next step is the
natural thing to do while you are inside it; do it if you want to, and
declare it. A partial report is welcome: if you stop, say at which step and
why, and submit that. It is the most useful report we can get.

Install the v0.21 checkout named in the recruitment issue, not a default
clone. Keep that code directory separate from your memory store.

## 1. Setup and early controls

Using the Quickstart and the named checkout, set up Palinode for the
fictional Harbor Notes project. Complete the guide's early controls
walkthrough. Note when the walkthrough is complete; nothing is timed to the
second.

## 2. Save the first decision

Save this decision, as the Quickstart shows: “Use SQLite for the local
prototype because it runs as a single-user desktop app.”

## 3. Connect the client

Continue the Quickstart by connecting and restarting your coding client
(Claude Code or Codex CLI). Stop when it is ready for a new session.

## 4. Fresh recall and inspection

Start a genuinely new chat or session. Ask, in your own words: for Harbor
Notes, what storage choice fits the local prototype? Find the evidence and
have the client show the source it used. Write down, in one line, what the
client answered and whether it showed the source.

Then show yourself where that record is stored and how to inspect its change
history, using the Quickstart's inspect step.

## 5. Supporting requirement and correction

First save this independent decision and leave it unchanged: “Store event
timestamps in UTC.” Before recording a replacement, save this separate
requirement: “The shared hosted service requires transactional coordination
for concurrent writers.” Then record this replacement: “Use PostgreSQL for
the shared hosted service because concurrent writers need transactional
coordination.” Keep a way to inspect the earlier decision, make the
replacement the current answer, and, in a new session, verify that the UTC
decision is unchanged. Write down, in one line, what the client answered
when you asked for the current shared-service storage decision.

## 6. Missing information and conflict (optional)

Ask the client what the stored evidence says about underwater-telemetry
licensing for Harbor Notes. Then save these two fixture records: “Deploy the
Harbor Notes shared service in the north region.” and “Deploy the Harbor Notes
shared service in the south region.” Ask which region the shared service
should deploy in, and what can be concluded from the stored evidence. Note
both answers briefly.

## 7. Controls (optional, but the questions below draw on it)

Show what Palinode is configured to capture and where content may go. Pause
future capture and recall, try a harmless fictional save and recall, inspect
the existing record and its history, then resume.

## 8. Linked worktree (optional)

From a linked Git worktree of the Harbor Notes project, start a fresh session
and recover the current storage decision and its source. Note which project
scope the client reported.

## 9. Report

Open the first-use report form linked from the recruitment issue and fill it
in. It asks for the following; each command is copy-paste and prints nothing
private when you have used fictional material only. Look over every block
before you submit and remove anything that is not Harbor Notes.

```bash
"$PALINODE_BIN/palinode" --version
python3 --version
git -C "$PALINODE_DIR" log --format='%ci %s' --reverse
python3 - "$PALINODE_DIR/.audit/retrievals.jsonl" <<'PY'
import json, os, sys
path = sys.argv[1]
if not os.path.exists(path):
    print("NO RETRIEVAL LOG — no search delivered anything before this point (a normal early stop)")
    sys.exit(0)
base = os.path.dirname(os.path.dirname(path))   # PALINODE_DIR
seen = set()
for line in open(path, encoding="utf-8"):
    try:
        d = json.loads(line)
    except ValueError:
        continue
    fp = str(d.get("file_path") or "")
    ref = os.path.relpath(fp, base) if os.path.isabs(fp) else fp
    if ref.startswith(".."):
        ref = os.path.basename(fp)
    ref = os.path.splitext(ref)[0]
    key = (d.get("timestamp"), d.get("source"), d.get("query"), ref)
    if key in seen:
        continue
    seen.add(key)
    scope = ",".join(d.get("scope") or []) or "-"
    print(d.get("timestamp"), d.get("source"), ref, d.get("disposition") or "-", scope, repr(d.get("query"))[:80])
PY
```

The form also asks, in your own words:

1. What is Palinode configured to capture on your machine?
2. Where can captured content go?
3. What did pausing capture and recall stop, and what did it not stop?
4. After a correction, what remains stored, and who could still read it?

And finally: what was confusing, where did you expect something different,
and whether you would like an optional check-in after two weeks. Declining
is fine.
