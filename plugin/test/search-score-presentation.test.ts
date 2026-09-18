import * as path from "path";
import { afterEach, describe, expect, it } from "vitest";

import palinodePlugin from "../index";

type Execute = (id: string, params: Record<string, unknown>) => Promise<any>;

const originalFetch = global.fetch;

afterEach(() => {
  global.fetch = originalFetch;
});

function captureSearchExecute(): Execute {
  let execute: Execute | undefined;
  const api: any = {
    pluginConfig: {
      palinodeDir: path.join(process.cwd(), "test-memory"),
      promptsDir: "specs/prompts",
      autoRecall: false,
      autoCapture: false,
      midTurnMode: "none",
    },
    logger: { info: () => undefined, warn: () => undefined, error: () => undefined },
    registerTool: (tool: { name: string; execute: Execute }) => {
      if (tool.name === "palinode_search") execute = tool.execute;
    },
    on: () => undefined,
    registerCli: () => undefined,
    registerService: () => undefined,
  };
  palinodePlugin.register(api);
  if (!execute) throw new Error("palinode_search was not registered");
  return execute;
}

describe("palinode_search score presentation", () => {
  it("distinguishes cosine, keyword-only, and legacy results", async () => {
    global.fetch = async () =>
      new Response(
        JSON.stringify([
          { category: "decisions", content: "vector", file_path: "/memory/vector.md", score: 1.0, raw_score: 0.421 },
          { category: "insights", content: "keyword", file_path: "/memory/keyword.md", score: 1.0, raw_score: null },
          { category: "research", content: "legacy", file_path: "/memory/legacy.md", score: 0.75 },
        ]),
        { status: 200 },
      );

    const result = await captureSearchExecute()("call-1", { query: "rollback" });
    const text = result.content[0].text as string;

    expect(text).toContain("[decisions] vector (42% match, file: vector.md)");
    expect(text).toContain("[insights] keyword (keyword match, rank 1.00, file: keyword.md)");
    expect(text).toContain("[research] legacy (rank 0.75, file: legacy.md)");
    expect(text).not.toContain("score: 100%");
    expect(text).not.toContain("score: 75%");
  });
});

describe("lexical retrieval diagnostics", () => {
  for (const outcome of ["matched", "no_match", "not_indexed"]) {
    it(`renders ${outcome} from the API receipt`, async () => {
      global.fetch = async (_url, init) => {
        expect(JSON.parse(String(init?.body)).receipt).toBe(true);
        return new Response(JSON.stringify({
          results: outcome === "matched" ? [{ category: "decisions", content: "orionledger", file_path: "/memory/decision.md", score: 1, raw_score: null, retrieval_mode: "lexical" }] : [],
          receipt: { retrieval: { active_mode: "lexical", index_state: outcome === "not_indexed" ? "not_indexed" : "ready", outcome } },
        }), { status: 200 });
      };
      const result = await captureSearchExecute()("lexical", { query: "orionledger" });
      expect(result.content[0].text).toContain("Retrieval: lexical");
      expect(result.content[0].text).toContain(outcome);
      expect(result.content[0].text).not.toContain("% match");
    });
  }

  it("keeps a backend failure distinct from no match", async () => {
    global.fetch = async () => new Response("Embedding backend unavailable", { status: 503 });
    const result = await captureSearchExecute()("outage", { query: "orionledger" });
    expect(result.content[0].text).toContain("search failed");
    expect(result.content[0].text).not.toContain("No relevant memories");
  });
});
