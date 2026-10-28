import type { RunDetail, FinalPayload } from '../types';

/**
 * Derives the FinalPayload state when replaying a past run.
 * Contract:
 * - Uses stored `final_nodes`, `outcome`, and `reason` when present.
 * - For legacy rows lacking them:
 *   - `outcome`: returns 'unknown' (or 'verified' if verified equivalent)
 *   - `final_nodes`: returns 'unknown' if verified equivalent, else null
 *   - `reason`: returns 'unknown' if not verified equivalent, else null
 */
export function deriveReplayFinalResult(pastRun: Partial<RunDetail>): FinalPayload {
  const isVerified = pastRun.final_status === 'VERIFIED_EQUIVALENT';
  return {
    status: pastRun.final_status || 'FAILED',
    outcome: pastRun.outcome ?? (isVerified ? 'verified' : 'unknown'),
    final_expr: pastRun.final_expr ?? null,
    obf_nodes: pastRun.obf_nodes ?? 0,
    final_nodes:
      pastRun.final_nodes !== undefined && pastRun.final_nodes !== null
        ? pastRun.final_nodes
        : isVerified
        ? 'unknown'
        : null,
    compression_pct: pastRun.compression_pct ?? 0.0,
    total_ms: pastRun.total_ms ?? 0.0,
    attempts: pastRun.attempts ?? 0,
    reason:
      pastRun.reason !== undefined && pastRun.reason !== null
        ? pastRun.reason
        : isVerified
        ? null
        : 'unknown',
    backend: pastRun.backend,
    model_name: pastRun.model_name,
  };
}
