import { describe, expect, it } from "vitest";
import { runCli } from "../src/program.js";
import { FakeDaemon, FakeFs, getFile, makeDeps, pluginStatus } from "./helpers/fakes.js";

function ledgerDoc(orders: unknown[]): unknown {
  return { orders: { _meta: { rev: 1, lock: null }, orders } };
}

const DRAFT = {
  id: "order:draft_lcsc",
  vendor: "lcsc",
  kind: "parts",
  status: "draft",
  total_minor: 1234,
  currency: "USD",
  external_id: null,
  tracking: [{ carrier: "mock", number: "MOCK-TRACK-1001" }],
  history: [],
};

const SHIPPED = {
  id: "order:draft_jlcpcb",
  vendor: "jlcpcb",
  kind: "pcb",
  status: "shipped",
  total_minor: 500000,
  currency: "USD",
  external_id: "JL-77",
  tracking: [],
  history: [],
};

function cartDaemon(
  options: { result?: unknown; plugins?: ReturnType<typeof pluginStatus>[] } = {},
): FakeDaemon {
  return new FakeDaemon({
    plugins: options.plugins ?? [pluginStatus("orders", true)],
    toolResults: {
      "orders.build_cart": options.result ?? {
        result: {
          status: "PASS",
          summary: "built 1 vendor cart(s)",
          artifacts: [
            {
              id: "art:orders_lcsc_cart",
              kind: "csv",
              vendor: "lcsc",
              format: "lcsc",
              path: "/daemon/artifacts/orders/lcsc-cart.csv",
              sha256: "sha256:abc",
              bytes: 42,
              written: true,
            },
          ],
          orders: ["order:draft_lcsc"],
          notice: "DRAFT ONLY: no order was placed.",
        },
      },
    },
    ir: ledgerDoc([DRAFT]),
  });
}

describe("atomc orders", () => {
  it("prints the ledger and exits 0", async () => {
    const daemon = new FakeDaemon({
      plugins: [pluginStatus("orders", true)],
      ir: ledgerDoc([DRAFT, SHIPPED]),
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["orders", "--json"]);
    expect(code).toBe(0);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.status).toBe("ok");
    expect(payload.count).toBe(2);
    expect(payload.total).toBe(2);
    expect(payload.orders[0].tracking_summary).toBe("mock:MOCK-TRACK-1001");
    expect(payload.orders[1].tracking_summary).toBe("—");
  });

  it("filters by status", async () => {
    const daemon = new FakeDaemon({
      plugins: [pluginStatus("orders", true)],
      ir: ledgerDoc([DRAFT, SHIPPED]),
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["orders", "--status", "shipped", "--json"]);
    expect(code).toBe(0);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.filter).toBe("shipped");
    expect(payload.count).toBe(1);
    expect(payload.orders[0].id).toBe(SHIPPED.id);
  });

  it("returns ok with an empty filter but a non-empty ledger", async () => {
    const daemon = new FakeDaemon({
      plugins: [pluginStatus("orders", true)],
      ir: ledgerDoc([DRAFT]),
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["orders", "--status", "delivered", "--json"]);
    expect(code).toBe(0);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.status).toBe("ok");
    expect(payload.count).toBe(0);
    expect(payload.total).toBe(1);
  });

  it("exits 1 for an empty ledger", async () => {
    const daemon = new FakeDaemon({
      plugins: [pluginStatus("orders", true)],
      ir: ledgerDoc([]),
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["orders", "--json"]);
    expect(code).toBe(1);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.status).toBe("empty");
    expect(payload.reason).toContain("no orders");
  });

  it("rejects an invalid --status with exit 2", async () => {
    const daemon = new FakeDaemon({ plugins: [pluginStatus("orders", true)] });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["orders", "--status", "bogus"]);
    expect(code).toBe(2);
    expect(captured.err.join("")).toContain("invalid --status");
  });

  it("reports unavailable when the orders plugin is missing", async () => {
    const daemon = new FakeDaemon({ plugins: [] });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["orders", "--json"]);
    expect(code).toBe(3);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.status).toBe("unavailable");
    expect(payload.plugin).toBe("orders");
  });

  it("reports unavailable when the daemon cannot be started", async () => {
    const { deps, captured } = makeDeps({ daemon: new FakeDaemon() });
    deps.ensureDaemon = async () => {
      throw new Error("connect ECONNREFUSED");
    };
    const code = await runCli(deps, ["orders", "--json"]);
    expect(code).toBe(3);
    expect(JSON.parse(captured.out.join("")).reason).toContain("daemon unavailable");
  });

  it("prints a human ledger table", async () => {
    const daemon = new FakeDaemon({
      plugins: [pluginStatus("orders", true)],
      ir: ledgerDoc([DRAFT, SHIPPED]),
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["orders"]);
    expect(code).toBe(0);
    const text = captured.err.join("");
    expect(text).toContain("orders: 2 of 2 record(s)");
    expect(text).toContain("order:draft_lcsc");
    expect(text).toContain("mock:MOCK-TRACK-1001");
    expect(captured.out).toEqual([]);
  });

  it("prints the empty-ledger human message", async () => {
    const daemon = new FakeDaemon({ plugins: [pluginStatus("orders", true)], ir: ledgerDoc([]) });
    const { deps, captured } = makeDeps({ daemon });
    await runCli(deps, ["orders"]);
    expect(captured.err.join("")).toContain("no orders recorded");
  });

  it("reports unavailable when the IR read fails", async () => {
    const daemon = new FakeDaemon({ plugins: [pluginStatus("orders", true)], getIRThrows: true });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["orders", "--json"]);
    expect(code).toBe(3);
    expect(JSON.parse(captured.out.join("")).status).toBe("unavailable");
  });

  it("reports unavailable when plugins.list fails", async () => {
    const daemon = new FakeDaemon({ listPluginsThrows: true });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["orders", "--json"]);
    expect(code).toBe(3);
    expect(JSON.parse(captured.out.join("")).reason).toContain("daemon RPC failed");
  });

  it("skips malformed ledger entries and defaults fields", async () => {
    const daemon = new FakeDaemon({
      plugins: [pluginStatus("orders", true)],
      ir: {
        orders: {
          orders: [
            null,
            "garbage",
            {},
            {
              id: "order:z",
              vendor: 1,
              kind: 2,
              status: 3,
              total_minor: "x",
              currency: 5,
              tracking: [{ carrier: 1 }, { carrier: "mock", number: "N1", url: 9 }],
            },
          ],
        },
      },
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["orders", "--project", "sub", "--json"]);
    expect(code).toBe(0);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.project).toBe("/work/sub");
    expect(payload.count).toBe(1);
    expect(payload.orders[0]).toMatchObject({
      id: "order:z",
      vendor: "",
      kind: "parts",
      status: "draft",
      total_minor: 0,
      currency: "USD",
      external_id: null,
      tracking_summary: "mock:N1",
    });
  });
});

describe("atomc orders build-cart", () => {
  it("builds carts and prints the written paths", async () => {
    const daemon = cartDaemon();
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["orders", "build-cart", "--json"]);
    expect(code).toBe(0);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.status).toBe("ok");
    expect(payload.count).toBe(1);
    expect(payload.artifacts[0].path).toBe("/daemon/artifacts/orders/lcsc-cart.csv");
    expect(payload.orders).toEqual(["order:draft_lcsc"]);
    expect(payload.notice).toContain("DRAFT ONLY");
    expect(daemon.toolCalls[0]).toMatchObject({ plugin: "orders", tool: "build_cart", args: {} });
  });

  it("filters artifacts by --vendor", async () => {
    const daemon = cartDaemon({
      result: {
        result: {
          status: "PASS",
          summary: "built 2 vendor cart(s)",
          artifacts: [
            { vendor: "lcsc", path: "/a/lcsc-cart.csv" },
            { vendor: "mouser", path: "/a/mouser-cart.csv" },
          ],
          orders: [],
        },
      },
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["orders", "build-cart", "--vendor", "lcsc", "--json"]);
    expect(code).toBe(0);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.vendor).toBe("lcsc");
    expect(payload.count).toBe(1);
    expect(payload.artifacts[0].vendor).toBe("lcsc");
  });

  it("copies artifacts to --out", async () => {
    const fs = new FakeFs();
    fs.addFile("/daemon/artifacts/orders/lcsc-cart.csv", "sku,qty\nR1,2\n");
    const daemon = cartDaemon();
    const { deps, captured } = makeDeps({ daemon, fs });
    const code = await runCli(deps, ["orders", "build-cart", "--out", "out", "--json"]);
    expect(code).toBe(0);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.written_to).toEqual(["/work/out/lcsc-cart.csv"]);
    expect(getFile(fs, "/work/out/lcsc-cart.csv")).toBe("sku,qty\nR1,2\n");
  });

  it("fails when the plugin reports FAIL", async () => {
    const daemon = cartDaemon({
      result: { result: { status: "FAIL", summary: "no chosen offers" } },
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["orders", "build-cart", "--json"]);
    expect(code).toBe(1);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.status).toBe("failed");
    expect(payload.reason).toBe("no chosen offers");
  });

  it("fails when no cart matches --vendor", async () => {
    const daemon = cartDaemon({
      result: {
        result: {
          status: "PASS",
          summary: "built 1 cart",
          artifacts: [{ vendor: "lcsc", path: "/a/lcsc-cart.csv" }],
          orders: [],
        },
      },
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["orders", "build-cart", "--vendor", "mouser", "--json"]);
    expect(code).toBe(1);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.reason).toContain('no cart file was built for vendor "mouser"');
    expect(payload.vendors).toEqual(["lcsc"]);
  });

  it("reports unavailable when the tool invocation throws", async () => {
    const daemon = new FakeDaemon({ plugins: [pluginStatus("orders", true)] });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["orders", "build-cart", "--json"]);
    expect(code).toBe(3);
    expect(JSON.parse(captured.out.join("")).status).toBe("unavailable");
  });

  it("reports unavailable when the daemon cannot be started", async () => {
    const { deps, captured } = makeDeps({ daemon: new FakeDaemon() });
    deps.ensureDaemon = async () => {
      throw new Error("nope");
    };
    const code = await runCli(deps, ["orders", "build-cart", "--json"]);
    expect(code).toBe(3);
    expect(JSON.parse(captured.out.join("")).status).toBe("unavailable");
  });

  it("prints human build-cart output", async () => {
    const daemon = cartDaemon();
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["orders", "build-cart"]);
    expect(code).toBe(0);
    const text = captured.err.join("");
    expect(text).toContain("built 1 cart(s)");
    expect(text).toContain("lcsc lcsc /daemon/artifacts/orders/lcsc-cart.csv");
    expect(text).toContain("notice: DRAFT ONLY");
  });

  it("fails when a cart file cannot be copied to --out", async () => {
    const fs = new FakeFs();
    fs.addFile("/daemon/artifacts/orders/lcsc-cart.csv", "data");
    fs.copyFile = async () => {
      throw new Error("EACCES");
    };
    const daemon = cartDaemon();
    const { deps, captured } = makeDeps({ daemon, fs });
    const code = await runCli(deps, ["orders", "build-cart", "--out", "out", "--json"]);
    expect(code).toBe(1);
    expect(JSON.parse(captured.out.join("")).reason).toContain("could not copy cart files");
  });

  it("tolerates malformed artifacts and a non-array orders list", async () => {
    const daemon = cartDaemon({
      result: {
        result: {
          status: "PASS",
          summary: "built 2",
          artifacts: [
            null,
            "garbage",
            {},
            { vendor: 1, path: "/a/cart.csv" },
            { vendor: "lcsc", path: "/b/p.csv", format: 7, sha256: 8, bytes: "x" },
          ],
          orders: "not-a-list",
        },
      },
    });
    const { deps, captured } = makeDeps({ daemon });
    const code = await runCli(deps, ["orders", "build-cart", "--json"]);
    expect(code).toBe(0);
    const payload = JSON.parse(captured.out.join(""));
    expect(payload.count).toBe(2);
    expect(payload.artifacts[0]).toMatchObject({ vendor: "unknown", path: "/a/cart.csv" });
    expect(payload.artifacts[1]).toMatchObject({
      vendor: "lcsc",
      format: null,
      sha256: null,
      bytes: null,
    });
    expect(payload.orders).toEqual([]);
    expect(payload.notice).toBeNull();
  });
});
