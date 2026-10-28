import test from 'node:test';
import assert from 'node:assert/strict';
import { clampCompressionPct, isExpressionAlreadyMinimal } from '../src/utils/compression.ts';

test('clampCompressionPct clamps negative reduction to zero', () => {
  assert.strictEqual(clampCompressionPct(-25.5), 0);
  assert.strictEqual(clampCompressionPct(-0.01), 0);
  assert.strictEqual(clampCompressionPct(-100), 0);
});

test('clampCompressionPct preserves positive and zero values', () => {
  assert.strictEqual(clampCompressionPct(0), 0);
  assert.strictEqual(clampCompressionPct(66.67), 66.67);
  assert.strictEqual(clampCompressionPct(100), 100);
});

test('clampCompressionPct handles null, undefined, and NaN gracefully', () => {
  assert.strictEqual(clampCompressionPct(null), 0);
  assert.strictEqual(clampCompressionPct(undefined), 0);
  assert.strictEqual(clampCompressionPct(Number.NaN), 0);
});

test('isExpressionAlreadyMinimal detects identical expressions', () => {
  assert.strictEqual(isExpressionAlreadyMinimal('x + y', 'x + y'), true);
  assert.strictEqual(isExpressionAlreadyMinimal('  x + y  ', 'x + y'), true);
  assert.strictEqual(isExpressionAlreadyMinimal('(x ^ y)', ' (x ^ y) \n'), true);
});

test('isExpressionAlreadyMinimal detects simplified or differing expressions', () => {
  assert.strictEqual(isExpressionAlreadyMinimal('(x ^ y) + 2 * (x & y)', 'x + y'), false);
  assert.strictEqual(isExpressionAlreadyMinimal('x + y', 'x + z'), false);
  assert.strictEqual(isExpressionAlreadyMinimal(null, 'x + y'), false);
  assert.strictEqual(isExpressionAlreadyMinimal('x + y', undefined), false);
  assert.strictEqual(isExpressionAlreadyMinimal('', ''), false);
});
