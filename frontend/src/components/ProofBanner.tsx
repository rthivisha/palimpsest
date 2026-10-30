import React, { useState } from 'react';
import { ShieldCheck, ShieldAlert, Copy, Check } from 'lucide-react';
import { FinalPayload } from '../types';
import { ExplainTooltip } from './ExplainTooltip';
import { clampCompressionPct, isExpressionAlreadyMinimal } from '../utils/compression';

interface ProofBannerProps {
  originalExpr: string;
  finalResult: FinalPayload | null;
  explainMode: boolean;
}

export const ProofBanner: React.FC<ProofBannerProps> = ({
  originalExpr,
  finalResult,
  explainMode,
}) => {
  const [copied, setCopied] = useState(false);

  if (!finalResult) return null;

  const isNotSimpler =
    finalResult.outcome === 'verified-not-simpler' ||
    finalResult.status === 'verified-not-simpler';
  const isVerified =
    !isNotSimpler &&
    (finalResult.status === 'VERIFIED_EQUIVALENT' ||
      finalResult.status === 'verified' ||
      finalResult.outcome === 'verified');
  const isUnsafe =
    finalResult.status === 'REJECTED_UNSAFE' ||
    finalResult.status === 'rejected-unsafe' ||
    finalResult.status === 'depth-rejected' ||
    finalResult.outcome === 'rejected-unsafe' ||
    finalResult.outcome === 'depth-rejected' ||
    finalResult.outcome === 'unconvertible';
  const isCancelled =
    finalResult.status === 'CANCELLED' || finalResult.outcome === 'cancelled';

  const isAlreadyMinimal = isExpressionAlreadyMinimal(
    originalExpr,
    finalResult.final_expr
  );
  const clampedCompression = clampCompressionPct(finalResult.compression_pct);

  const handleCopy = () => {
    if (finalResult.final_expr) {
      navigator.clipboard.writeText(finalResult.final_expr);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  if (isNotSimpler) {
    return (
      <div className="bg-amber-950/30 border border-amber-500/60 rounded-xl p-5 shadow-[0_0_20px_rgba(245,158,11,0.15)] space-y-4">
        {/* Banner Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-amber-900/50 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-amber-500/20 text-amber-400 border border-amber-500/40">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <div className="text-sm font-bold font-mono text-amber-300 tracking-wide flex items-center gap-1.5">
                <span>Verified equivalent, but not simpler</span>
                <ExplainTooltip topic="z3" explainMode={explainMode} inline />
              </div>
              <p className="text-xs text-slate-300 mt-0.5">
                SMT solver verified bitwise equivalence (QF_BV UNSAT), but candidate AST node count ({finalResult.final_nodes != null ? `${finalResult.final_nodes} (semantic)` : 'unknown'}) is not smaller than original ({finalResult.obf_nodes != null ? `${finalResult.obf_nodes} (semantic)` : 'unknown'}).
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 text-xs font-mono">
            {finalResult.is_fallback && (
              <div className="px-2.5 py-1 rounded bg-amber-950/80 border border-amber-500/60 text-amber-300 font-mono text-xs font-bold">
                LLAMA.CPP (fallback)
              </div>
            )}
            {finalResult.backend && (
              <div className="px-2.5 py-1 rounded bg-slate-900/90 border border-slate-700 text-cyan-300 font-mono text-xs">
                <span className="font-bold">{finalResult.backend.toUpperCase()}</span>
                {finalResult.model_name && <span className="text-slate-400"> · {finalResult.model_name}</span>}
              </div>
            )}
            <div className="px-2.5 py-1 rounded bg-amber-950/80 border border-amber-800 text-amber-300">
              <span className="text-slate-400">Total: </span>
              <span className="font-bold">{finalResult.total_ms != null ? `${finalResult.total_ms} ms` : 'unknown'}</span>
            </div>
            <div className="px-2.5 py-1 rounded bg-amber-950/80 border border-amber-800 text-amber-300">
              <span className="text-slate-400">Attempts: </span>
              <span className="font-bold">{finalResult.attempts != null ? finalResult.attempts : 'unknown'}</span>
            </div>
          </div>
        </div>

        {/* Side-by-side Expression Transformation */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          <div className="p-3.5 rounded-lg bg-cyber-bg border border-cyber-border">
            <div className="text-[11px] font-mono text-slate-400 mb-1 flex items-center justify-between">
              <span>ORIGINAL INPUT</span>
              <span className="text-slate-500 font-bold">{finalResult.obf_nodes != null ? `${finalResult.obf_nodes} nodes (semantic)` : 'unknown'}</span>
            </div>
            <div className="font-mono text-sm text-slate-300 break-all bg-slate-950/60 p-2.5 rounded border border-slate-900">
              {originalExpr}
            </div>
          </div>

          <div className="p-3.5 rounded-lg bg-amber-950/20 border border-amber-500/40">
            <div className="text-[11px] font-mono text-amber-400 mb-1 flex items-center justify-between">
              <span className="font-bold flex items-center gap-1">
                <span>EQUIVALENT CANDIDATE</span>
              </span>
              <div className="flex items-center gap-2">
                <span className="text-amber-300 font-bold">{finalResult.final_nodes != null ? `${finalResult.final_nodes} nodes (semantic)` : 'unknown'}</span>
                {isAlreadyMinimal ? (
                  <span className="text-xs px-2 py-0.5 rounded bg-blue-900/60 border border-blue-500/40 text-blue-300 font-bold">
                    Already minimal
                  </span>
                ) : (
                  <span className="text-xs px-1.5 py-0.5 rounded bg-amber-900/60 text-amber-300 font-bold">
                    {finalResult.compression_pct != null ? `${clampedCompression}%` : 'unknown'}
                  </span>
                )}
              </div>
            </div>

            <div className="flex items-center justify-between gap-2 font-mono text-base font-bold text-amber-200 bg-slate-950/80 p-2.5 rounded border border-amber-900/50">
              <span className="break-all">{finalResult.final_expr}</span>
              <button
                type="button"
                onClick={handleCopy}
                className="shrink-0 p-1.5 rounded bg-amber-900/40 hover:bg-amber-900/80 text-amber-300 transition-colors"
                title="Copy candidate expression"
              >
                {copied ? <Check className="w-4 h-4 text-amber-400" /> : <Copy className="w-4 h-4" />}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  if (isVerified) {
    return (
      <div className="bg-emerald-950/30 border border-emerald-500/60 rounded-xl p-5 shadow-[0_0_20px_rgba(16,185,129,0.15)] space-y-4">
        {/* Banner Header */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-emerald-900/50 pb-3">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-lg bg-emerald-500/20 text-emerald-400 border border-emerald-500/40">
              <ShieldCheck className="w-5 h-5" />
            </div>
            <div>
              <div className="text-sm font-bold font-mono text-emerald-300 tracking-wide flex items-center gap-1.5">
                <span>EQUIVALENCE PROVEN BY Z3 (QF_BV, 64-bit)</span>
                <ExplainTooltip topic="z3" explainMode={explainMode} inline />
              </div>
              <p className="text-xs text-slate-300 mt-0.5">
                SMT solver verified bitwise equivalence across 64-bit unsigned bit-vector semantics. Zero counterexamples exist.
              </p>
            </div>
          </div>

          <div className="flex items-center gap-3 text-xs font-mono">
            {finalResult.is_fallback && (
              <div className="px-2.5 py-1 rounded bg-amber-950/80 border border-amber-500/60 text-amber-300 font-mono text-xs font-bold">
                LLAMA.CPP (fallback)
              </div>
            )}
            {finalResult.backend && (
              <div className="px-2.5 py-1 rounded bg-slate-900/90 border border-slate-700 text-cyan-300 font-mono text-xs">
                <span className="font-bold">{finalResult.backend.toUpperCase()}</span>
                {finalResult.model_name && <span className="text-slate-400"> · {finalResult.model_name}</span>}
              </div>
            )}
            <div className="px-2.5 py-1 rounded bg-emerald-950/80 border border-emerald-800 text-emerald-300">
              <span className="text-slate-400">Total: </span>
              <span className="font-bold">{finalResult.total_ms != null ? `${finalResult.total_ms} ms` : 'unknown'}</span>
            </div>
            <div className="px-2.5 py-1 rounded bg-emerald-950/80 border border-emerald-800 text-emerald-300">
              <span className="text-slate-400">Attempts: </span>
              <span className="font-bold">{finalResult.attempts != null ? finalResult.attempts : 'unknown'}</span>
            </div>
          </div>
        </div>

        {/* Side-by-side Expression Transformation */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Obfuscated Input */}
          <div className="p-3.5 rounded-lg bg-cyber-bg border border-cyber-border">
            <div className="text-[11px] font-mono text-slate-400 mb-1 flex items-center justify-between">
              <span>ORIGINAL OBFUSCATED INPUT</span>
              <span className="text-slate-500 font-bold">{finalResult.obf_nodes != null ? `${finalResult.obf_nodes} nodes (semantic)` : 'unknown'}</span>
            </div>
            <div className="font-mono text-sm text-slate-300 break-all bg-slate-950/60 p-2.5 rounded border border-slate-900">
              {originalExpr}
            </div>
          </div>

          {/* Simplified Target */}
          <div className="p-3.5 rounded-lg bg-emerald-950/20 border border-emerald-500/40">
            <div className="text-[11px] font-mono text-emerald-400 mb-1 flex items-center justify-between">
              <span className="font-bold flex items-center gap-1">
                <span>PROVEN CANONICAL FORM</span>
                <ExplainTooltip topic="compression" explainMode={explainMode} inline />
              </span>
              <div className="flex items-center gap-2">
                <span className="text-emerald-300 font-bold">{finalResult.final_nodes != null ? `${finalResult.final_nodes} nodes (semantic)` : 'unknown'}</span>
                {isAlreadyMinimal ? (
                  <span className="text-xs px-2 py-0.5 rounded bg-blue-900/60 border border-blue-500/40 text-blue-300 font-bold">
                    Already minimal
                  </span>
                ) : (
                  <span className="text-xs px-1.5 py-0.5 rounded bg-emerald-900/60 text-emerald-300 font-bold">
                    {finalResult.compression_pct != null ? `-${clampedCompression}%` : 'unknown'}
                  </span>
                )}
              </div>
            </div>

            <div className="flex items-center justify-between gap-2 font-mono text-base font-bold text-emerald-200 bg-slate-950/80 p-2.5 rounded border border-emerald-900/50">
              <span className="break-all">{finalResult.final_expr}</span>
              <button
                type="button"
                onClick={handleCopy}
                className="shrink-0 p-1.5 rounded bg-emerald-900/40 hover:bg-emerald-900/80 text-emerald-300 transition-colors"
                title="Copy simplified expression"
              >
                {copied ? <Check className="w-4 h-4 text-emerald-400" /> : <Copy className="w-4 h-4" />}
              </button>
            </div>
          </div>
        </div>
      </div>
    );
  }

  // Terminal Fail or Security Rejection
  const rawReason =
    finalResult.reason ||
    (isUnsafe
      ? 'Security Gate Rejection: Malformed or disallowed syntax.'
      : isCancelled
      ? 'Synthesis cancelled by user.'
      : 'Verification budget exhausted without equivalence proof.');
  const cleanReason = rawReason.replace(/\r?\n|\r/g, ' ').replace(/\s+/g, ' ').trim();
  const truncatedReason = cleanReason.length > 200 ? cleanReason.slice(0, 197) + '...' : cleanReason;

  return (
    <div className="bg-rose-950/30 border border-rose-500/60 rounded-xl p-5 shadow-[0_0_20px_rgba(239,68,68,0.15)] space-y-3">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-rose-500/20 text-rose-400 border border-rose-500/40">
          <ShieldAlert className="w-5 h-5" />
        </div>
        <div>
          <div className="text-sm font-bold font-mono text-rose-300 tracking-wide flex items-center gap-1.5">
            <span>
              {isUnsafe
                ? 'SECURITY GATE REJECTION (BLOCKED)'
                : isCancelled
                ? 'SYNTHESIS CANCELLED BY USER'
                : 'NOT VERIFIED (FAILED)'}
            </span>
            <ExplainTooltip topic="cegis" explainMode={explainMode} inline />
          </div>
          <p
            className="text-xs text-slate-300 mt-0.5 font-mono line-clamp-2 break-words max-w-3xl"
            title={cleanReason}
          >
            {truncatedReason}
          </p>
        </div>
      </div>
    </div>
  );
};
