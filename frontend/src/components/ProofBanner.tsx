import React, { useState } from 'react';
import { ShieldCheck, ShieldAlert, Copy, Check } from 'lucide-react';
import { FinalPayload } from '../types';
import { ExplainTooltip } from './ExplainTooltip';

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

  const isVerified = finalResult.status === 'VERIFIED_EQUIVALENT';
  const isUnsafe = finalResult.status === 'REJECTED_UNSAFE';
  const isCancelled = finalResult.status === 'CANCELLED';

  const handleCopy = () => {
    if (finalResult.final_expr) {
      navigator.clipboard.writeText(finalResult.final_expr);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

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
            <div className="px-2.5 py-1 rounded bg-emerald-950/80 border border-emerald-800 text-emerald-300">
              <span className="text-slate-400">Total: </span>
              <span className="font-bold">{finalResult.total_ms} ms</span>
            </div>
            <div className="px-2.5 py-1 rounded bg-emerald-950/80 border border-emerald-800 text-emerald-300">
              <span className="text-slate-400">Attempts: </span>
              <span className="font-bold">{finalResult.attempts}</span>
            </div>
          </div>
        </div>

        {/* Side-by-side Expression Transformation */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {/* Obfuscated Input */}
          <div className="p-3.5 rounded-lg bg-cyber-bg border border-cyber-border">
            <div className="text-[11px] font-mono text-slate-400 mb-1 flex items-center justify-between">
              <span>ORIGINAL OBFUSCATED INPUT</span>
              <span className="text-slate-500 font-bold">{finalResult.obf_nodes} AST nodes</span>
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
                <span className="text-emerald-300 font-bold">{finalResult.final_nodes} nodes</span>
                <span className="text-xs px-1.5 py-0.2 rounded bg-emerald-900/60 text-emerald-300 font-bold">
                  -{finalResult.compression_pct}%
                </span>
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
  return (
    <div className="bg-rose-950/30 border border-rose-500/60 rounded-xl p-5 shadow-[0_0_20px_rgba(239,68,68,0.15)] space-y-3">
      <div className="flex items-center gap-3">
        <div className="p-2 rounded-lg bg-rose-500/20 text-rose-400 border border-rose-500/40">
          <ShieldAlert className="w-5 h-5" />
        </div>
        <div>
          <div className="text-sm font-bold font-mono text-rose-300 tracking-wide">
            {isUnsafe
              ? 'REJECTED BY SECURITY GATE'
              : isCancelled
              ? 'EXECUTION CANCELLED'
              : 'NOT VERIFIED. No answer accepted.'}
          </div>
          <p className="text-xs text-slate-300 mt-0.5">
            {isUnsafe
              ? finalResult.reason || 'Expression violated AST whitelist or depth limits. Execution aborted safely.'
              : isCancelled
              ? 'Synthesis run was interrupted by client disconnect.'
              : (finalResult.reason
                  ? `${finalResult.reason}. Candidate discarded.`
                  : 'Proposer was unable to propose an equivalent expression within the iteration budget. Candidate discarded.')}
          </p>
        </div>
      </div>

      <div className="flex items-center gap-4 text-xs font-mono text-slate-400 pt-2 border-t border-rose-900/40">
        <div>Total time: <span className="text-slate-200">{finalResult.total_ms} ms</span></div>
        <div>Attempts made: <span className="text-slate-200">{finalResult.attempts}</span></div>
        <div>Obfuscated complexity: <span className="text-slate-200">{finalResult.obf_nodes} nodes</span></div>
      </div>
    </div>
  );
};
