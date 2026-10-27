/**
 * Type definitions for PALIMPSEST (VEX-MORPH) Frontend.
 * Matches frozen API payloads and database schema contracts.
 */

export type RunStatus =
  | 'IDLE'
  | 'RUNNING'
  | 'VERIFIED_EQUIVALENT'
  | 'FAILED'
  | 'REJECTED_UNSAFE'
  | 'CANCELLED'
  | 'ERROR';

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
}

export interface FinalPayload {
  status: RunStatus;
  final_expr: string | null;
  obf_nodes: number;
  final_nodes: number | null;
  compression_pct: number;
  total_ms: number;
  attempts: number;
  reason: string | null;
}

export interface RunSummary {
  run_id: string;
  timestamp: string;
  expression: string;
  obf_nodes: number;
  final_status: RunStatus;
  final_expr: string | null;
  compression_pct: number;
  attempts: number;
  total_ms: number;
  backend: string;
  max_iterations: number;
}

export interface RunDetail extends RunSummary {
  attempts_history: Attempt[];
}

export interface StatsResponse {
  total_runs: number;
  verified_runs: number;
  failed_runs: number;
  success_rate_pct: number;
  avg_total_ms: number;
  avg_attempts: number;
}

export interface ExampleExpr {
  name: string;
  expression: string;
  expected_simplified: string;
  description: string;
  variables: string[];
}

export interface SystemHealth {
  status: string;
  backend: string;
  model_name: string;
  z3_version: string;
  z3_logic: string;
  langsmith_enabled: boolean;
}

