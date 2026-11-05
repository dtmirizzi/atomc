/**
 * Thin adapter binding the harness port ({@link HarnessDaemon}) to the real
 * typed `@atomc/daemon-client`. Kept separate so tests use an in-memory fake
 * and never touch a socket.
 */
import type { DaemonClient } from "@atomc/daemon-client";
import type { AgentName, HarnessDaemon, ToolDescriptor } from "./types.js";

/** Adapts a connected {@link DaemonClient} to the {@link HarnessDaemon} port. */
export class DaemonClientAdapter implements HarnessDaemon {
  constructor(private readonly client: DaemonClient) {}

  getIR(path: string): Promise<{ rev: number; value: unknown }> {
    return this.client.getIR(path);
  }

  transact(params: {
    path: string;
    base_rev: number;
    ops: Parameters<DaemonClient["transact"]>[0]["ops"];
    holder?: string;
  }): Promise<{ new_rev: number; changed_paths: string[] }> {
    return this.client.transact(params);
  }

  lock(node: string, holder: string, ttlS: number, reason?: string) {
    return this.client.lock(node, holder, ttlS, reason);
  }

  unlock(node: string, holder: string) {
    return this.client.unlock(node, holder);
  }

  runDAG(params: { targets?: string[]; force?: boolean } = {}): Promise<{ run_id: string }> {
    return this.client.runDAG(params);
  }

  runGates(ids?: readonly string[]) {
    return this.client.runGates(ids);
  }

  async listTools(agent?: AgentName): Promise<ToolDescriptor[]> {
    const tools = await this.client.listTools(agent);
    return tools.map((tool) => ({
      plugin: tool.plugin,
      name: tool.name,
      description: tool.description,
      input_schema: tool.input_schema,
      mutates: tool.mutates,
    }));
  }

  callTool(plugin: string, tool: string, args: unknown, holder?: string) {
    return this.client.callTool(plugin, tool, args, holder);
  }
}
