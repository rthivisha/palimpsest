import type { RunDetail, FinalPayload } from '../types';

/**
 * Derives the FinalPayload state when replaying a past run.
 * Contract:
 * - Uses strictly stored values from pastRun.
 * - Never invents defaults: when outcome, compression_pct, total_ms, obf_nodes,
 *   attempts, or status are missing, sets them to null so the UI renders "unknown".
 * - Never defaults to 'verified', 0, or 'FAILED'.
 * - Keeps final_nodes strictly numeric or null so counter animations never receive strings.
 */
export function deriveReplayFinalResult(pastRun: Partial<RunDetail>): FinalPayload {
  return {
    status: pastRun.final_status ?? null,
    outcome: pastRun.outcome ?? null,
    final_expr: pastRun.final_expr ?? null,
    obf_nodes: typeof pastRun.obf_nodes === 'number' ? pastRun.obf_nodes : null,
    final_nodes: typeof pastRun.final_nodes === 'number' ? pastRun.final_nodes : null,
    compression_pct: typeof pastRun.compression_pct === 'number' ? pastRun.compression_pct : null,
    total_ms: typeof pastRun.total_ms === 'number' ? pastRun.total_ms : null,
    attempts: typeof pastRun.attempts === 'number' ? pastRun.attempts : null,
    reason: pastRun.reason ?? null,
    backend: pastRun.backend ?? null,
    model_name: pastRun.model_name ?? null,
  };
}


