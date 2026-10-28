import test from 'node:test';
import assert from 'node:assert/strict';
import { deriveReplayFinalResult } from '../src/utils/replay.ts';

test('Replay uses stored final_nodes, outcome, and reason when present', () => {
  const pastRun = {
    run_id: 'run-123',
    final_status: 'VERIFIED_EQUIVALENT',
    outcome: 'verified',
    final_nodes: 3,
    reason: null,
    final_expr: 'x + y',
    obf_nodes: 9,
    compression_pct: 66.67,
    total_ms: 120.5,
    attempts: 2,
    backend: 'ollama',
    model_name: 'palimpsest-q4_k_m',
  };

  const res = deriveReplayFinalResult(pastRun);
  assert.strictEqual(res.final_nodes, 3);
  assert.strictEqual(res.outcome, 'verified');
  assert.strictEqual(res.reason, null);
  assert.strictEqual(res.status, 'VERIFIED_EQUIVALENT');
});

test('Replay uses stored reason and outcome for failed runs when present', () => {
  const pastRun = {
    run_id: 'run-456',
    final_status: 'FAILED',
    outcome: 'failed-exhausted',
    final_nodes: null,
    reason: 'Max iterations reached without proving equivalence',
    final_expr: null,
    obf_nodes: 15,
    compression_pct: 0.0,
    total_ms: 500.0,
    attempts: 5,
    backend: 'fake',
  };

  const res = deriveReplayFinalResult(pastRun);
  assert.strictEqual(res.final_nodes, null);
  assert.strictEqual(res.outcome, 'failed-exhausted');
  assert.strictEqual(res.reason, 'Max iterations reached without proving equivalence');
  assert.strictEqual(res.status, 'FAILED');
});

test('Replay shows "unknown" for legacy rows without final_nodes or outcome', () => {
  // Legacy verified row where final_nodes, outcome, and reason were not recorded
  const legacyVerified = {
    run_id: 'legacy-verif',
    final_status: 'VERIFIED_EQUIVALENT',
    final_expr: 'x + y',
    obf_nodes: 9,
    // final_nodes, outcome, reason are undefined / null
    final_nodes: null,
    outcome: undefined,
    reason: null,
  };

  const resVerified = deriveReplayFinalResult(legacyVerified);
  assert.strictEqual(resVerified.final_nodes, 'unknown');
  assert.strictEqual(resVerified.outcome, 'verified');
  assert.strictEqual(resVerified.reason, null);

  // Legacy failed row where outcome and reason were not recorded
  const legacyFailed = {
    run_id: 'legacy-fail',
    final_status: 'FAILED',
    final_expr: null,
    obf_nodes: 9,
    final_nodes: null,
    outcome: undefined,
    reason: undefined,
  };

  const resFailed = deriveReplayFinalResult(legacyFailed);
  assert.strictEqual(resFailed.final_nodes, null);
  assert.strictEqual(resFailed.outcome, 'unknown');
  assert.strictEqual(resFailed.reason, 'unknown');
});
