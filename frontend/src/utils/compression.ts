/**
 * Utility functions for compression and expression minimization display.
 */

export function clampCompressionPct(pct: number | null | undefined): number {
  if (pct === null || pct === undefined || Number.isNaN(pct)) return 0;
  return Math.max(0, Math.round(pct * 100) / 100);
}

export function isExpressionAlreadyMinimal(
  original: string | null | undefined,
  candidate: string | null | undefined
): boolean {
  if (!original || !candidate) return false;
  return original.trim() === candidate.trim();
}
