/**
 * Deterministic in-memory {@link HarnessDaemon} for replay/end-to-end tests (WP-3.5).
 *
 * This is the seam the real `DaemonClientAdapter` implements over the RPC
 * transport: `runAgent` only ever sees the {@link HarnessDaemon} port, so driving
 * it with this fixture exercises the exact WP-3.2 transactional loop
 * (lock → transact → DAG → gates → release) without a Python process, socket,
 * credential or LLM. Errors use the real `@atomc/daemon-client` classes so
 * conflict/lock handling matches production.
 */

import type { JsonPatchOp } from "@atomc/core-ir";
import { ConflictError, type GateResult, LockedError } from "@atomc/daemon-client";
import type { HarnessDaemon, ToolDescriptor } from "../../src/types.js";

const FIXED_EXPIRY = "2026-11-04T23:59:59Z";

export interface FixtureDaemonOptions {
  /** Starting IR revision. Default 10. */
  rev?: number;
  /**
   * Gate results per `runGates` call. The last batch is reused once the queue is
   * exhausted, so `[[fail], [pass]]` models a fix-then-verify transition.
   */
  gates?: GateResult[][];
  /** Tools advertised by `listTools`. */
  tools?: ToolDescriptor[];
  /** Nodes that always report a lock conflict. */
  lockConflicts?: Iterable<string>;
  /** Nodes whose `unlock` throws (best-effort cleanup tests). */
  unlockFailures?: Iterable<string>;
  /** When true, every `transact` throws an optimistic {@link ConflictError}. */
  transactConflict?: boolean;
}

interface ToolCallRecord {
  plugin: string;
  tool: string;
  args: unknown;
  holder?: string;
}

/** Fully deterministic daemon port with observable call history. */
export class FixtureDaemon implements HarnessDaemon {
  rev: number;
  readonly events: string[] = [];
  readonly locked = new Map<string, string>();
  readonly lockOrder: string[] = [];
  readonly gateCalls: Array<readonly string[] | undefined> = [];
  readonly dagCalls: Array<string[] | undefined> = [];
  readonly toolCalls: ToolCallRecord[] = [];
  readonly tools: ToolDescriptor[];
  readonly #gates: GateResult[][];
  readonly #lockConflicts: Set<string>;
  readonly #unlockFailures: Set<string>;
  readonly #transactConflict: boolean;
  #gateIndex = 0;
  lockCalls = 0;
  unlockCalls = 0;
  transactCalls = 0;

  constructor(options: FixtureDaemonOptions = {}) {
    this.rev = options.rev ?? 10;
    this.#gates = options.gates ?? [];
    this.tools = options.tools ?? [];
    this.#lockConflicts = new Set(options.lockConflicts ?? []);
    this.#unlockFailures = new Set(options.unlockFailures ?? []);
    this.#transactConflict = options.transactConflict ?? false;
  }

  async getIR(path: string): Promise<{ rev: number; value: unknown }> {
    this.events.push(`getIR:${path}`);
    return { rev: this.rev, value: { path, rev: this.rev } };
  }

  async transact(params: {
    path: string;
    base_rev: number;
    ops: JsonPatchOp[];
    holder?: string;
  }): Promise<{ new_rev: number; changed_paths: string[] }> {
    this.transactCalls += 1;
    this.events.push(`transact:${params.path}`);
    if (this.#transactConflict) {
      throw new ConflictError("stale rev", {
        current_rev: this.rev,
        expected_rev: params.base_rev,
      });
    }
    if (params.base_rev !== this.rev) {
      throw new ConflictError("stale rev", {
        current_rev: this.rev,
        expected_rev: params.base_rev,
      });
    }
    this.rev += 1;
    return { new_rev: this.rev, changed_paths: [params.path] };
  }

  async lock(
    node: string,
    holder: string,
    _ttlS?: number,
    _reason?: string,
  ): Promise<{ expires_at: string }> {
    this.lockCalls += 1;
    this.events.push(`lock:${node}`);
    if (this.#lockConflicts.has(node)) {
      throw new LockedError("locked", { holder: "agent:other#1", expires_at: FIXED_EXPIRY });
    }
    this.locked.set(node, holder);
    this.lockOrder.push(node);
    return { expires_at: FIXED_EXPIRY };
  }

  async unlock(node: string, holder: string): Promise<{ released: true }> {
    this.unlockCalls += 1;
    this.events.push(`unlock:${node}`);
    if (this.#unlockFailures.has(node)) throw new Error(`unlock ${node} failed`);
    if (this.locked.get(node) === holder) this.locked.delete(node);
    return { released: true };
  }

  async runDAG(params?: { targets?: string[]; force?: boolean }): Promise<{ run_id: string }> {
    this.dagCalls.push(params?.targets);
    this.events.push(`runDAG:${params?.targets?.join(",") ?? "*"}`);
    return { run_id: "fixture-dag-run" };
  }

  async runGates(ids?: readonly string[]): Promise<GateResult[]> {
    this.gateCalls.push(ids);
    this.events.push(`runGates:${ids?.join(",") ?? "*"}`);
    if (this.#gates.length === 0) return [];
    const index = Math.min(this.#gateIndex, this.#gates.length - 1);
    this.#gateIndex += 1;
    return this.#gates[index] ?? [];
  }

  async listTools(_agent?: string): Promise<ToolDescriptor[]> {
    return this.tools;
  }

  async callTool(
    plugin: string,
    tool: string,
    args: unknown,
    holder?: string,
  ): Promise<{ result: unknown }> {
    this.toolCalls.push(
      holder === undefined ? { plugin, tool, args } : { plugin, tool, args, holder },
    );
    this.events.push(`callTool:${plugin}:${tool}`);
    return { result: { ok: true, plugin, tool } };
  }

  /** True when no locks remain held (a lock-leak assertion). */
  get locksReleased(): boolean {
    return this.locked.size === 0;
  }
}
