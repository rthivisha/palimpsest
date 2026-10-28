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

test('Replay returns null for missing fields without inventing defaults', () => {
  // Legacy row where outcome, compression_pct, total_ms, obf_nodes, attempts, and final_nodes are not set
  const legacyRow = {
    run_id: 'legacy-unpopulated',
    final_expr: 'x + y',
    // Missing: final_status, outcome, obf_nodes, final_nodes, compression_pct, total_ms, attempts, reason
  };

  const res = deriveReplayFinalResult(legacyRow);
  assert.strictEqual(res.status, null); // never defaults to FAILED
  assert.strictEqual(res.outcome, null); // never defaults to verified or unknown
  assert.strictEqual(res.obf_nodes, null); // never defaults to 0
  assert.strictEqual(res.final_nodes, null); // numeric or null only, never a string
  assert.strictEqual(res.compression_pct, null); // never defaults to 0
  assert.strictEqual(res.total_ms, null); // never defaults to 0
  assert.strictEqual(res.attempts, null); // never defaults to 0
  assert.strictEqual(res.reason, null);
});

test('Replay keeps final_nodes strictly numeric or null', () => {
  const legacyVerified = {
    run_id: 'legacy-verif',
    final_status: 'VERIFIED_EQUIVALENT',
    final_expr: 'x + y',
    obf_nodes: 9,
    final_nodes: null, // missing numeric count
  };

  const res = deriveReplayFinalResult(legacyVerified);
  // Must be strictly null (not the string 'unknown') so counter animations never crash
  assert.strictEqual(res.final_nodes, null);
  assert.strictEqual(typeof res.final_nodes, 'object'); // null is typeof object
  assert.notStrictEqual(typeof res.final_nodes, 'string');
});

