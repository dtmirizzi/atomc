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
export {
  type CheckpointContext,
  type CheckpointDecision,
  type CheckpointReason,
  type ConvergeAuditEntry,
  type ConvergeEvent,
  type ConvergenceModelHost,
  type ConvergenceRegistry,
  type ConvergeOptions,
  type ConvergeResult,
  type ConvergeStatus,
  converge,
  defaultIsConverged,
  type ProviderFactory,
  type RollbackPolicy,
  scopesOverlap,
  splitBudget,
} from "./converge.js";
export { DaemonClientAdapter } from "./daemon-adapter.js";
export {
  ALLOWED_IMAGE_MIME_TYPES,
  type AllowedImageMimeType,
  type ArtifactReader,
  type AttachmentLimits,
  type AttachmentSource,
  type BoundedFileSystem,
  createImageAttachment,
  HarnessInspectionDaemon,
  INSPECTION_TOOL_NAMES,
  INSPECTION_TOOLS,
  type InspectionToolName,
  inspectionToolGrants,
  isModelAttachment,
  isPathContained,
  loadImageAttachment,
  MAX_ATTACHMENT_BYTES,
  MultimodalInspector,
  normalizeProjectPath,
  ProjectImageReader,
  sniffImageMimeType,
} from "./multimodal.js";
export {
  createPiAiProvider,
  DECISION_INSTRUCTIONS,
  DEFAULT_PI_AI_COMPLETE,
  decodeToolName,
  encodeToolName,
  extractJsonObject,
  type PiAiComplete,
  PiAiProvider,
  type PiAiProviderConfig,
  type PiAiProviderDeps,
  type PiAiProviderOptions,
  toModelDecision,
  toPiAiContext,
  toTurnUsage,
} from "./providers/index.js";
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
