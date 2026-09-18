import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import palinodePlugin from "../index";

const sentinel = "FAKE_SECRET_capture_excluded_1458";
const workspace = process.cwd();
let allowed: boolean;
let requests: Array<{ path: string; body?: any }>;

function register(config: Record<string, unknown> = {}) {
  const hooks: Record<string, any> = {};
  const logger = { info: vi.fn(), warn: vi.fn(), error: vi.fn() };
  palinodePlugin.register({
    pluginConfig: { palinodeApiUrl: "http://fixture.test", autoRecall: true,
      recallProfile: "writing", ...config }, logger,
    on: (name: string, callback: any) => { hooks[name] = callback; },
    registerTool: vi.fn(), registerCli: vi.fn(), registerService: vi.fn(),
  } as any);
  return { hooks, logger };
}

beforeEach(() => {
  allowed = true;
  requests = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string, options?: RequestInit) => {
    const pathname = new URL(url).pathname;
    requests.push({ path: pathname, body: options?.body ? JSON.parse(String(options.body)) : undefined });
    if (pathname === "/controls/check") return Response.json({ allowed });
    if (pathname === "/list") return Response.json([{ file: "decisions/sample.md", core: true }]);
    if (pathname === "/read") return Response.json({ content: "Fictional decision" });
    return Response.json({ status: "ok" });
  }));
});

afterEach(() => vi.unstubAllGlobals());

describe("automatic capture controls", () => {
  it("requires explicit opt-in for agent end and reset", () => {
    const { hooks } = register();
    expect(hooks.agent_end).toBeUndefined();
    expect(hooks.before_reset).toBeUndefined();
  });

  it.each(["agent_end", "before_reset"])("keeps denied %s content out of requests and logs", async (name) => {
    allowed = false;
    const { hooks, logger } = register({ autoCapture: true });
    const event = { success: true, messages: [{ role: "user", content: sentinel }] };
    await hooks[name](event, { workspaceDir: workspace });
    expect(requests.map(r => r.path)).toEqual(["/controls/check"]);
    expect(JSON.stringify(requests)).not.toContain(sentinel);
    expect(JSON.stringify(logger.info.mock.calls.concat(logger.warn.mock.calls))).not.toContain(sentinel);
  });

  it("observes pause and resume on the same plugin instance", async () => {
    const { hooks } = register({ autoCapture: true });
    const event = { success: true, messages: [{ role: "user", content: "Fictional retention is 45 days" }] };
    allowed = false;
    await hooks.agent_end(event, { workspaceDir: workspace });
    allowed = true;
    await hooks.agent_end(event, { workspaceDir: workspace });
    const posts = requests.filter(r => r.path === "/session-end");
    expect(posts).toHaveLength(1);
    expect(posts[0].body).toMatchObject({ automatic: true, cwd: workspace, source: "openclaw-plugin" });
    expect(posts[0].body.summary).toContain("45 days");
  });

  it("fails closed for unavailable policy and unknown workspace", async () => {
    const { hooks, logger } = register({ autoCapture: true });
    const event = { success: true, messages: [{ role: "user", content: sentinel }] };
    await hooks.before_reset(event, {});
    expect(requests).toHaveLength(0);
    vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error(sentinel)));
    await hooks.before_reset(event, { workspaceDir: workspace });
    expect(JSON.stringify(logger.warn.mock.calls)).not.toContain(sentinel);
  });

  it("withholds recall if pause arrives while recall is fetching", async () => {
    const { hooks } = register();
    vi.stubGlobal("fetch", vi.fn(async (url: string) => {
      const pathname = new URL(url).pathname;
      if (pathname === "/controls/check") return Response.json({ allowed });
      if (pathname === "/list") return Response.json([{ file: "decisions/sample.md", core: true }]);
      allowed = false;
      return Response.json({ content: sentinel });
    }));
    expect(await hooks.before_prompt_build({ prompt: "Recall our fictional retention decision" },
      { workspaceDir: workspace })).toBeUndefined();
  });
});
