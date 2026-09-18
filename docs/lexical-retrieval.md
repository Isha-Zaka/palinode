# Recall without an embedding service

Set the **server and watcher** to lexical mode before starting them:

```yaml
# PALINODE_DIR/palinode.config.yaml
search:
  retrieval_mode: lexical
```

Or set `PALINODE_RETRIEVAL_MODE=lexical` in their environment. Environment wins
over YAML; invalid values fail startup. Restart running processes after a
change. Clients use the API's mode, so setting this only in an MCP client or
CLI process does not change an already-running API.

Lexical mode indexes and searches current text with SQLite FTS5. It needs no
embedding endpoint, model download, cloud key, or chat service. The existing
Python package and its SQLite/FTS5/sqlite-vec dependencies are still required.
Saving indexes synchronously; the watcher indexes subsequent filesystem edits.
Automatic description/summary scheduling and write-time model checks are
skipped in this mode. Explicit optional model tools (consolidation, semantic
neighbors, trigger matching, and similar operations) still require their
configured services; they are not part of the first-use path.

With an initialized git-backed memory directory and the API running:

```sh
palinode save 'Use SQLite for the Orionledger decision.' --type Decision --slug orionledger
palinode read decisions/orionledger.md
palinode search Orionledger --score
palinode search Orionledger --format json --diagnostics
```

The save receipt reports `retrieval_mode: lexical`, `indexed: true`,
`indexed_fts: true`, and `embedded: false`. Embeddings are intentionally skipped,
not deferred retries. If indexing actually fails, the file remains saved and
versioned and the receipt reports `indexed: false` with `index_error`.

## Search and diagnostics across surfaces

| Surface | Contract |
| --- | --- |
| REST `POST /search` | Existing results array by default. Hits add `retrieval_mode`; lexical hits have `raw_score: null`. Send `receipt: true` for the envelope, including diagnostics on empty results. |
| MCP `palinode_search` | Uses the same REST path; displays mode, readiness, and outcome from the receipt. Save/read use the shipped tools. |
| CLI `palinode search` | Text shows retrieval diagnostics. JSON stays an array by default; `--diagnostics` returns `{results, receipt}`. |
| Inspector `/ui/memory?q=Orionledger` | Same search handler and qualifiers; shows mode/readiness, labeled keyword rank, and a distinct backend-failure banner. |
| OpenClaw `palinode_search` | Same API mode; displays receipt diagnostics, including empty outcomes. Plugin CLI JSON search preserves the REST array. Automatic recall uses the same search endpoint; embedding-dependent trigger/associative channels remain optional. |
| Pi/Cline shared recall | Their `/search` channel inherits the server mode and already renders `raw_score: null` as keyword rank. Their resolve channel keeps its explicit keyword-only coverage qualifier. |

`receipt.retrieval` contains `configured_mode`, `active_mode`, `index_state`,
`outcome`, and `coverage: visible_indexed_corpus_only`. There are no store-wide
counts in search receipts. Readiness uses the same live visibility gate as
recall; a corpus containing only hidden files is indistinguishable from an
empty visible corpus. It checks indexed file visibility, not every source file
for outstanding edits, so `ready` does **not** promise the watcher has caught up.
Readiness stops at the first visible indexed file; delivered hits already
prove readiness. Hybrid then checks only vectorless files through the live
visibility gate, with no per-file vector query. The existing `/status` administration surface also
reports store-wide chunk/vector counts and skips embedding probes in lexical
mode (`embed_functional` and `ollama_reachable` are `null`, meaning unprobed).

| State | Meaning |
| --- | --- |
| `matched` | Visible indexed text matched; freshness/currency/evidence still qualify its use. |
| `no_match` | No result from the visible indexed corpus. It does not prove no answer exists in unindexed files. |
| `not_indexed` | No indexed file is visible to this caller, including an empty store. Save or reindex visible source files. |
| `embeddings_pending` (index state) | Hybrid is configured but some visible indexed files lack vectors. Run full reindex and check again. |
| HTTP 503 / search failure | Unexpected embedding backend outage in hybrid mode; no empty-success substitution. |
| HTTP 500 / search failure | An index or other unexpected search failure; no empty-success substitution. |

A lexical score is a rank, **not semantic similarity or confidence**. The vector
`threshold` and `hybrid=false` request switch do not enable embeddings or apply
a cosine floor in lexical mode. FTS tokenization, keyword expansion, the shared
ranker, date/type/priority filters, deduplication, live visibility, current-text
projection, freshness/currency, and optional `resolve` evidence remain in use.

## Unexpected outages are a separate contract

The default is `search.retrieval_mode: hybrid`. A connectivity, timeout, or
service failure during ordinary search stays `EmbeddingUnavailable` / HTTP
503, including in MCP, CLI, and plugin error presentation. Search does not
silently switch modes. Fix the service or explicitly configure lexical mode.
A deterministic rejection of one input by a healthy embedder retains the
existing `keyword-fallback` behavior, now using the shared qualifier pipeline.
Resolve retains its pre-existing keyword-only degraded-coverage behavior and
also skips embedding entirely in explicit lexical mode.

The indexer's existing hybrid outage behavior is unchanged: cold startup may
write FTS-only rows after a bounded failed probe; a subsequent unexpected
outage during a warm reconcile rolls the transaction back and leaves an
observable retry condition. These are distinct from deliberate lexical indexing.

## Enable embeddings later

1. Configure `embeddings.primary` for the desired endpoint/model/dimensions.
2. Set `search.retrieval_mode: hybrid` (and remove any lexical environment
   override), then restart the API and watcher.
3. Run **`palinode reindex` without `--since`**. Unchanged lexical rows have no
   vector and are therefore re-embedded; no source rewrite is needed to trigger it.
4. Check `/status` retrieval readiness and run a search. Pending vectors mean
   reindex is not complete; a nominal reindex response alone is insufficient.

The fixture verifies byte-identical memory files and unchanged git HEAD while
adding vectors with the same 1024 dimensions. Optional mechanical cross-reference
or summary enrichment can make their usual provenance commits during a normal
reindex. Existing history is preserved. Use the same configured dimensions for this reindex path. Changing model
dimensionality requires a separate rebuild of the derived vector index; this
mode switch does not resize an existing vector table.

## Contract fixture behavior

`tests/test_lexical_retrieval.py` pins the public lexical-mode contract against
real SQLite/FTS storage without requiring an embedding or chat service. The
broader release validation also exercises REST, CLI, MCP stdio, inspector, and
plugin callers. Synthetic embedding fixtures use hand-authored mappings; they
are contract tests, not a real-model semantic-quality study.

For “Use SQLite for the Orionledger decision.”, lexical finds “Orionledger”,
misses the no-overlap paraphrase “Which embedded relational engine did we
choose?”, and returns no hits for “volcanic telescope”. The synthetic hybrid
fixture finds the first two and misses the third. Keyword recall can also
return irrelevant hits that share words; a result is not proof that a question
has an answer. Real-model quality, human first-use timing, and flagship adoption
studies remain separate acceptance work.
