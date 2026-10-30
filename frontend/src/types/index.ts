/**
 * Type definitions for PALIMPSEST (VEX-MORPH) Frontend.
 * Matches frozen API payloads and database schema contracts.
 */

export type BlueprintStatus =
  | 'VERIFIED_EQUIVALENT'
  | 'FAILED'
  | 'REJECTED_UNSAFE'
  | 'CANCELLED'
  | 'ERROR';

export type RunOutcome =
  | 'verified'
  | 'verified-not-simpler'
  | 'failed-exhausted'
  | 'unknown-timeout'
  | 'invalid'
  | 'rejected-unsafe'
  | 'depth-rejected'
  | 'unconvertible'
  | 'cancelled'
  | 'error'
  | 'VERIFIED_EQUIVALENT'
  | 'FAILED'
  | 'REJECTED_UNSAFE';

export type RunStatus = BlueprintStatus | RunOutcome | 'IDLE' | 'RUNNING';

export type VerificationStatus =
  | 'QF_BV_UNSAT_64BIT_VERIFIED'
  | 'SAT'
  | 'INVALID'
  | 'UNKNOWN_TIMEOUT'
  | 'ERROR';

export interface Attempt {
  iteration: number;
  candidate?: string;
  raw_output?: string;
  think?: string | null;
  status?: VerificationStatus | string;
  latency_ms?: number;
  witness?: Record<string, string>;
  expected?: string | null;
  actual?: string | null;
  diff_bits?: string | null;
  feedback_message?: string;
}

export interface RunStartedPayload {
  run_id: string;
  expression: string;
  obf_nodes: number;
  max_iterations: number;
  backend: string;
  model_name?: string;
  is_fallback?: boolean;
}

export interface FinalPayload {
  status: BlueprintStatus | string | null;
  outcome?: RunOutcome | string | null;
  final_expr: string | null;
  obf_nodes: number | null;
  final_nodes: number | null;
  compression_pct: number | null;
  total_ms: number | null;
  attempts: number | null;
  reason: string | null;
  backend?: string | null;
  model_name?: string | null;
  is_fallback?: boolean;
}

export interface RunSummary {
  run_id: string;
  timestamp: string;
  expression: string;
  obf_nodes: number | null;
  final_status: string;
  outcome?: string | null;
  reason?: string | null;
  final_expr: string | null;
  final_nodes?: number | null;
  compression_pct: number | null;
  attempts: number | null;
  total_ms: number | null;
  backend: string;
  model_name?: string | null;
  max_iterations: number;
}

export interface RunDetail extends RunSummary {
  attempts_history: Attempt[];
}

export interface StatsResponse {
  total_runs: number;
  completed_runs?: number;
  verified_runs: number;
  strictly_simpler_runs?: number;
  failed_exhausted_runs?: number;
  failed_runs: number;
  rejected_runs?: number;
  cancelled_runs?: number;
  error_runs?: number;
  proven_equivalent_rate_pct?: number;
  success_rate_pct: number;
  strictly_simpler_rate_pct?: number;
  simpler_rate_pct?: number;
  avg_compression_pct?: number;
  avg_latency_ms?: number;
  avg_total_ms?: number;
  avg_attempts: number;
}

export interface ExampleExpr {
  id?: string;
  title?: string;
  name?: string;
  category?: string;
  expression: string;
  expected_simplified: string;
  description?: string;
  variables?: string[];
  transformation_steps?: string[];
}

export type ModelStatus = 'ready' | 'ollama_not_running' | 'model_missing' | 'error';

export interface SystemHealth {
  status: string;
  backend: string;
  model_name: string;
  model_reachable?: boolean;
  model_unreachable_reason?: string | null;
  model_status?: ModelStatus;
  hint?: string | null;
  fix_command?: string | null;
  is_fallback?: boolean;
  fallback_backend?: string | null;
  fake_hint?: string | null;
  z3_version: string;
  z3_logic: string;
  langsmith_enabled?: boolean;
  langsmith_tracing?: boolean;
}

