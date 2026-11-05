/**
 * Runtime plugin registration API.
 *
 * `defineAtomcPlugin({ manifest, setup })` validates the manifest, runs `setup` to
 * collect gate/tool/CLI handlers, and returns an immutable {@link AtomcPlugin}
 * descriptor. Nothing runs at module import time.
 *
 * The SDK deliberately does not depend on the daemon: {@link PluginContext} describes
 * the host services a handler may use, and the daemon (or a test fake) supplies the
 * concrete implementation when it invokes a handler.
 */
import { z } from "zod";
import {
  type AtomcPluginManifest,
  GATE_SEVERITIES,
  type GateSeverity,
  type ManifestValidationContext,
  OWNER_AGENTS,
  type OwnerAgent,
  parsePluginManifest,
} from "./manifest.js";

/** JSON Patch operation as used by `ir.transact` (RFC 6902 subset). */
export interface IrTransactionOp {
  op: "add" | "remove" | "replace" | "move" | "copy" | "test";
  path: string;
  value?: unknown;
  from?: string;
}

/** Result of a successful IR transaction. */
export interface IrTransactionResult<T = unknown> {
  /** New document revision after the transaction committed. */
  rev: number;
  /** Value at the transacted subtree after the transaction. */
  value: T;
}

/** Read/write access to the daemon-owned IR. */
export interface PluginIr {
  /** Read the value at an RFC 6901 pointer. */
  get<T = unknown>(pointer: string): Promise<T>;
  /** Apply JSON Patch ops relative to `pointer`, guarded by `baseRev`. */
  transact<T = unknown>(
    pointer: string,
    baseRev: number,
    ops: readonly IrTransactionOp[],
  ): Promise<IrTransactionResult<T>>;
}

/** Access to the plugin's artifact directory. */
export interface PluginArtifacts {
  /** Absolute path of this plugin's artifact root. */
  readonly root: string;
  write(relativePath: string, data: Uint8Array | string): Promise<string>;
  read(relativePath: string): Promise<Uint8Array>;
  exists(relativePath: string): Promise<boolean>;
}

/** Structured logger supplied by the host. */
export interface PluginLogger {
  debug(message: string, fields?: Record<string, unknown>): void;
  info(message: string, fields?: Record<string, unknown>): void;
  warn(message: string, fields?: Record<string, unknown>): void;
  error(message: string, fields?: Record<string, unknown>): void;
}

/** Host-provided key/value cache (TTL is advisory). */
export interface PluginCache {
  get(key: string): Promise<unknown | undefined>;
  set(key: string, value: unknown, ttlMs?: number): Promise<void>;
}

/** Host event bus (daemon pushes `ir.changed`, `gate.result`, `dag.node.*`, `log`). */
export interface PluginEvents {
  emit(event: string, payload?: unknown): void;
  on(event: string, listener: (payload: unknown) => void): () => void;
}

/** Host services available to a plugin handler at call time. */
export interface PluginContext {
  readonly ir: PluginIr;
  readonly artifacts: PluginArtifacts;
  readonly logger: PluginLogger;
  readonly cache: PluginCache;
  readonly signal: AbortSignal;
  readonly events: PluginEvents;
}

/** Evidence entry attached to a {@link GateResult}. */
export interface GateEvidence {
  kind: "text" | "json" | "artifact" | "image";
  ref?: string;
  data?: unknown;
  message?: string;
}

/** Suggested remediation attached to a {@link GateResult}. */
export interface GateSuggestion {
  message: string;
  patch?: { path: string; ops: IrTransactionOp[] };
}

/** Gate outcome — mirrors `docs/architecture/contracts/gate-result.md` v0.1. */
export interface GateResult {
  id: string;
  status: "PASS" | "FAIL" | "SKIP" | "ERROR";
  severity: GateSeverity;
  plugin: string;
  owner_agent: OwnerAgent | null;
  evaluated_at: string;
  ir_rev: number;
  duration_ms: number;
  summary: string;
  evidence: GateEvidence[];
  suggestions: GateSuggestion[];
  refs: string[];
}

const irTransactionOpSchema = z.strictObject({
  op: z.enum(["add", "remove", "replace", "move", "copy", "test"]),
  path: z.string(),
  value: z.unknown().optional(),
  from: z.string().optional(),
});

/** Runtime validator for {@link GateResult} (gate-result.md v0.1). */
export const GateResultSchema = z.strictObject({
  id: z.string().min(1),
  status: z.enum(["PASS", "FAIL", "SKIP", "ERROR"]),
  severity: z.enum(GATE_SEVERITIES),
  plugin: z.string().min(1),
  owner_agent: z.enum(OWNER_AGENTS).nullable(),
  evaluated_at: z.string().min(1),
  ir_rev: z.number().int(),
  duration_ms: z.number().nonnegative(),
  summary: z.string(),
  evidence: z.array(
    z.strictObject({
      kind: z.enum(["text", "json", "artifact", "image"]),
      ref: z.string().optional(),
      data: z.unknown().optional(),
      message: z.string().optional(),
    }),
  ),
  suggestions: z.array(
    z.strictObject({
      message: z.string(),
      patch: z
        .strictObject({
          path: z.string(),
          ops: z.array(irTransactionOpSchema),
        })
        .optional(),
    }),
  ),
  refs: z.array(z.string()),
});

/** A gate handler: invoked by the daemon with the gate id it is registered for. */
export type GateHandler = (ctx: PluginContext, gateId: string) => GateResult | Promise<GateResult>;
/** A tool handler: invoked with arbitrary JSON arguments. */
export type ToolHandler = (ctx: PluginContext, args: unknown) => unknown | Promise<unknown>;
/** A CLI handler: invoked with the raw argument vector after the command name. */
export type CliHandler = (
  ctx: PluginContext,
  args: readonly string[],
) => unknown | Promise<unknown>;

/** Setup-time context: host services plus handler registration methods. */
export interface PluginSetupContext extends PluginContext {
  registerGate(handler: string, fn: GateHandler): void;
  registerTool(handler: string, fn: ToolHandler): void;
  registerCli(handler: string, fn: CliHandler): void;
}

/** The plugin author's setup function. Must only register declared handlers. */
export type PluginSetup = (ctx: PluginSetupContext) => void | Promise<void>;

/** Immutable descriptor returned by {@link defineAtomcPlugin}. */
export interface AtomcPlugin {
  readonly manifest: Readonly<AtomcPluginManifest>;
  /** Gate handlers keyed by gate id. */
  readonly gates: ReadonlyMap<string, GateHandler>;
  /** Tool handlers keyed by tool name. */
  readonly tools: ReadonlyMap<string, ToolHandler>;
  /** CLI handlers keyed by command name. */
  readonly cli: ReadonlyMap<string, CliHandler>;
}

/** Options accepted by {@link defineAtomcPlugin}. */
export interface AtomcPluginOptions {
  manifest: unknown;
  setup: PluginSetup;
}

/** Thrown when `setup` registers an undeclared/duplicate handler or leaves one missing. */
export class PluginRegistrationError extends Error {
  readonly code: string;

  constructor(code: string, message: string) {
    super(message);
    this.name = "PluginRegistrationError";
    this.code = code;
  }
}

class ImmutableMap<K, V> implements ReadonlyMap<K, V> {
  readonly #entries: Map<K, V>;

  constructor(entries: Iterable<[K, V]>) {
    this.#entries = new Map(entries);
    Object.freeze(this);
  }

  get size(): number {
    return this.#entries.size;
  }

  get(key: K): V | undefined {
    return this.#entries.get(key);
  }

  has(key: K): boolean {
    return this.#entries.has(key);
  }

  entries(): MapIterator<[K, V]> {
    return this.#entries.entries();
  }

  keys(): MapIterator<K> {
    return this.#entries.keys();
  }

  values(): MapIterator<V> {
    return this.#entries.values();
  }

  forEach(callbackfn: (value: V, key: K, map: ReadonlyMap<K, V>) => void, thisArg?: unknown): void {
    for (const [key, value] of this.#entries) callbackfn.call(thisArg, value, key, this);
  }

  [Symbol.iterator](): MapIterator<[K, V]> {
    return this.#entries[Symbol.iterator]();
  }
}

function deepFreeze<T>(value: T): Readonly<T> {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    for (const key of Object.keys(value)) {
      deepFreeze((value as Record<string, unknown>)[key]);
    }
    Object.freeze(value);
  }
  return value;
}

const noopLogger: PluginLogger = {
  debug: () => {},
  info: () => {},
  warn: () => {},
  error: () => {},
};

function unavailable(method: string): never {
  throw new Error(
    `PluginContext.${method} is unavailable during setup(); host services are only provided at handler runtime`,
  );
}

/** Host services are placeholders until the daemon invokes a handler. */
function createRegistrationBase(): PluginContext {
  return {
    ir: {
      get: () => unavailable("ir.get"),
      transact: () => unavailable("ir.transact"),
    },
    artifacts: {
      get root(): string {
        return unavailable("artifacts.root");
      },
      write: () => unavailable("artifacts.write"),
      read: () => unavailable("artifacts.read"),
      exists: () => unavailable("artifacts.exists"),
    },
    logger: noopLogger,
    cache: {
      get: () => unavailable("cache.get"),
      set: () => unavailable("cache.set"),
    },
    signal: new AbortController().signal,
    events: {
      emit: () => {},
      on: () => () => {},
    },
  };
}

function checkRegistration(
  kind: string,
  handler: string,
  declared: ReadonlySet<string>,
  registered: { has(value: string): boolean },
): void {
  if (!declared.has(handler)) {
    throw new PluginRegistrationError(
      "undeclared_handler",
      `${kind} handler "${handler}" is not declared in the manifest`,
    );
  }
  if (registered.has(handler)) {
    throw new PluginRegistrationError(
      "duplicate_handler",
      `${kind} handler "${handler}" is already registered`,
    );
  }
}

/**
 * Validate a manifest and run `setup`, returning an immutable plugin descriptor.
 *
 * Throws {@link PluginRegistrationError} for undeclared/duplicate handlers and for
 * declared handlers that `setup` never registered.
 */
export async function defineAtomcPlugin(
  options: AtomcPluginOptions,
  context: ManifestValidationContext = {},
): Promise<AtomcPlugin> {
  const manifest = parsePluginManifest(options.manifest, context);

  const gateHandlers = new Map<string, GateHandler>();
  const toolHandlers = new Map<string, ToolHandler>();
  const cliHandlers = new Map<string, CliHandler>();

  const declaredGateHandlers = new Set(manifest.gates.map((gate) => gate.handler));
  const declaredToolHandlers = new Set(manifest.tools.map((tool) => tool.handler));
  const declaredCliHandlers = new Set(manifest.cli.map((entry) => entry.handler));

  const setupContext: PluginSetupContext = {
    ...createRegistrationBase(),
    registerGate(handler, fn) {
      checkRegistration("gate", handler, declaredGateHandlers, gateHandlers);
      gateHandlers.set(handler, fn);
    },
    registerTool(handler, fn) {
      checkRegistration("tool", handler, declaredToolHandlers, toolHandlers);
      toolHandlers.set(handler, fn);
    },
    registerCli(handler, fn) {
      checkRegistration("cli", handler, declaredCliHandlers, cliHandlers);
      cliHandlers.set(handler, fn);
    },
  };

  await options.setup(setupContext);

  for (const handler of declaredGateHandlers) {
    if (!gateHandlers.has(handler)) {
      throw new PluginRegistrationError(
        "missing_handler",
        `declared gate handler "${handler}" was not registered by setup()`,
      );
    }
  }
  for (const handler of declaredToolHandlers) {
    if (!toolHandlers.has(handler)) {
      throw new PluginRegistrationError(
        "missing_handler",
        `declared tool handler "${handler}" was not registered by setup()`,
      );
    }
  }
  for (const handler of declaredCliHandlers) {
    if (!cliHandlers.has(handler)) {
      throw new PluginRegistrationError(
        "missing_handler",
        `declared CLI handler "${handler}" was not registered by setup()`,
      );
    }
  }

  const gates = new Map<string, GateHandler>();
  for (const gate of manifest.gates) {
    const handler = gateHandlers.get(gate.handler);
    if (handler) gates.set(gate.id, handler);
  }
  const tools = new Map<string, ToolHandler>();
  for (const tool of manifest.tools) {
    const handler = toolHandlers.get(tool.handler);
    if (handler) tools.set(tool.name, handler);
  }
  const cli = new Map<string, CliHandler>();
  for (const entry of manifest.cli) {
    const handler = cliHandlers.get(entry.handler);
    if (handler) cli.set(entry.command, handler);
  }

  return deepFreeze({
    manifest: deepFreeze(manifest),
    gates: new ImmutableMap(gates),
    tools: new ImmutableMap(tools),
    cli: new ImmutableMap(cli),
  });
}
