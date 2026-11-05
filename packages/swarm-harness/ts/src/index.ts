/**
 * `@atomc/swarm-harness` — transactional state machine for atomc swarm agents.
 *
 * Public surface:
 * - typed protocol ({@link AgentDefinition}, {@link AgentSession}, {@link GateFailure}, …)
 * - explicit state machine ({@link SwarmStateMachine}, {@link transition})
 * - the transactional agent loop ({@link runAgent})
 * - redacted JSONL transcripts ({@link TranscriptWriter})
 * - a `DaemonClient` adapter ({@link DaemonClientAdapter})
 *
 * See `docs/architecture/contracts/agent-protocol.md`.
 *
 * @packageDocumentation
 */

export {
  AGENT_DEFINITIONS,
  AgentDefinitionError,
  AgentRegistry,
  allAgentDefinitions,
  DEFAULT_AGENT_MODEL,
  defaultAgentRegistry,
  EE_AGENT_PROMPT,
  FW_AGENT_PROMPT,
  getAgentDefinition,
  HARNESS_INSPECTION_TOOL_GRANTS,
  MECH_AGENT_PROMPT,
  MULTI_OWNER_GATES,
  normalizeGateId,
  OPS_AGENT_PROMPT,
  routeGateToAgents,
  SHARED_AGENT_RULES,
} from "./agents/index.js";
export { DaemonClientAdapter } from "./daemon-adapter.js";
export {
  ALLOWED_IMAGE_MIME_TYPES,
  type AllowedImageMimeType,
  type ArtifactReader,
  type AttachmentLimits,
  type AttachmentSource,
  createImageAttachment,
  HarnessInspectionDaemon,
  INSPECTION_TOOL_NAMES,
  INSPECTION_TOOLS,
  type InspectionToolName,
  inspectionToolGrants,
  loadImageAttachment,
  MAX_ATTACHMENT_BYTES,
  MultimodalInspector,
  sniffImageMimeType,
} from "./multimodal.js";
export {
  DECISION_INSTRUCTIONS,
  decodeToolName,
  encodeToolName,
  extractJsonObject,
  type PiAiAssistantMessage,
  type PiAiComplete,
  type PiAiCompleteOptions,
  type PiAiContext,
  type PiAiImageContent,
  type PiAiMessage,
  PiAiProvider,
  type PiAiProviderOptions,
  type PiAiTextContent,
  type PiAiTool,
  type PiAiToolCall,
  type PiAiUsage,
  toModelDecision,
  toPiAiContext,
  toPiAiTool,
  toTurnUsage,
} from "./pi-ai-provider.js";
export { isToolPermitted, isWithinScopes, type RunAgentOptions, runAgent } from "./runner.js";
export {
  AGENT_EVENTS,
  type AgentEvent,
  isTerminal,
  StateTransitionError,
  SwarmStateMachine,
  TERMINAL_STATES,
  TRANSITIONS,
  transition,
} from "./state-machine.js";
export {
  DEFAULT_REDACT_PATTERNS,
  redactEntry,
  redactText,
  redactValue,
  SENSITIVE_KEYS,
  TranscriptWriter,
} from "./transcript.js";
export type {
  AgentBudget,
  AgentDefinition,
  AgentName,
  AgentPatchProposal,
  AgentRunResult,
  AgentSession,
  AgentState,
  AgentToolCall,
  AgentTurn,
  GateFailure,
  HarnessDaemon,
  ModelAttachment,
  ModelConfig,
  ModelDecision,
  ModelProvider,
  ModelRequest,
  RunOutcome,
  SwarmEvent,
  ToolDescriptor,
  TranscriptOptions,
  TurnUsage,
} from "./types.js";
export { AGENT_NAMES, AGENT_STATES } from "./types.js";
