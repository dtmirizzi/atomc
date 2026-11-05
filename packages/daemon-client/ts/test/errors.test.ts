import { describe, expect, it } from "vitest";
import {
  ConflictError,
  DaemonClientError,
  DagRunError,
  LockedError,
  MalformedResponseError,
  mapRpcError,
  PluginError,
  RefIntegrityError,
  RpcError,
  TimeoutError,
  ValidationError,
} from "../src/index.js";

describe("error hierarchy", () => {
  it("DaemonClientError carries a name and optional cause", () => {
    const cause = new Error("root");
    const err = new DaemonClientError("boom", { cause });
    expect(err.name).toBe("DaemonClientError");
    expect(err.message).toBe("boom");
    expect((err as { cause?: unknown }).cause).toBe(cause);
    expect(new DaemonClientError("plain").name).toBe("DaemonClientError");
  });

  it("TimeoutError exposes method and timeout", () => {
    const err = new TimeoutError("ir.get", 123);
    expect(err.method).toBe("ir.get");
    expect(err.timeoutMs).toBe(123);
    expect(err).toBeInstanceOf(DaemonClientError);
  });

  it("MalformedResponseError is a DaemonClientError", () => {
    expect(new MalformedResponseError("bad")).toBeInstanceOf(DaemonClientError);
  });

  it("ConflictError parses rev fields from data", () => {
    const withData = new ConflictError("stale", { current_rev: 4, expected_rev: 3 });
    expect(withData.code).toBe(-32010);
    expect(withData.current_rev).toBe(4);
    expect(withData.expected_rev).toBe(3);
    expect(new ConflictError("stale").current_rev).toBeUndefined();
  });

  it("LockedError parses holder/expiry from data", () => {
    const locked = new LockedError("locked", { holder: "a", expires_at: "t" });
    expect(locked.code).toBe(-32011);
    expect(locked.holder).toBe("a");
    expect(locked.expires_at).toBe("t");
    expect(new LockedError("locked").holder).toBeUndefined();
  });

  it("ValidationError parses the errors array", () => {
    const err = new ValidationError("bad", {
      errors: [{ path: "/x", message: "nope", type: "value" }],
    });
    expect(err.errors).toHaveLength(1);
    expect(new ValidationError("bad").errors).toEqual([]);
  });

  it("PluginError parses plugin metadata and retryable", () => {
    const err = new PluginError("boom", {
      plugin: "sourcing",
      tool: "search",
      retryable: true,
      detail: { why: "x" },
    });
    expect(err.plugin).toBe("sourcing");
    expect(err.tool).toBe("search");
    expect(err.retryable).toBe(true);
    expect(err.detail).toEqual({ why: "x" });
    expect(new PluginError("boom").retryable).toBe(false);
  });

  it("RefIntegrityError and DagRunError set their codes", () => {
    expect(new RefIntegrityError("dup").code).toBe(-32013);
    expect(new DagRunError("failed").code).toBe(-32030);
  });

  it("mapRpcError returns the most specific class for each required code", () => {
    expect(mapRpcError({ code: -32010, message: "x" })).toBeInstanceOf(ConflictError);
    expect(mapRpcError({ code: -32011, message: "x" })).toBeInstanceOf(LockedError);
    expect(mapRpcError({ code: -32012, message: "x" })).toBeInstanceOf(ValidationError);
    expect(mapRpcError({ code: -32013, message: "x" })).toBeInstanceOf(RefIntegrityError);
    expect(mapRpcError({ code: -32020, message: "x" })).toBeInstanceOf(PluginError);
    expect(mapRpcError({ code: -32030, message: "x" })).toBeInstanceOf(DagRunError);
    const generic = mapRpcError({ code: -32603, message: "x", data: { id: 1 } });
    expect(generic).toBeInstanceOf(RpcError);
    expect(generic.code).toBe(-32603);
    expect(generic.data).toEqual({ id: 1 });
  });
});
