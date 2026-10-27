import React, { useState } from 'react';
import { ChevronDown, ChevronRight, CheckCircle, XCircle, AlertTriangle, Clock, Brain, MessageSquare } from 'lucide-react';
import { Attempt } from '../types';
import { BitVisualizer } from './BitVisualizer';

interface AttemptTimelineProps {
  attempts: Attempt[];
  explainMode: boolean;
}

export const AttemptTimeline: React.FC<AttemptTimelineProps> = ({ attempts, explainMode }) => {
  const [expandedThinks, setExpandedThinks] = useState<Record<number, boolean>>({});

  if (!attempts || attempts.length === 0) {
    return (
      <div className="bg-cyber-surface border border-cyber-border rounded-xl p-6 text-center text-slate-500 text-sm">
        No synthesis attempts initiated yet. Select an expression above and press De-obfuscate.
      </div>
    );
  }

  const toggleThink = (iter: number) => {
    setExpandedThinks((prev) => ({ ...prev, [iter]: !prev[iter] }));
  };

  return (
    <div className="bg-cyber-surface border border-cyber-border rounded-xl p-5 shadow-lg space-y-4">
      <div className="flex items-center justify-between border-b border-cyber-border pb-3">
        <div className="text-xs font-semibold text-slate-300 font-mono flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-cyan-400" />
          <span>SYNTHESIS TIMELINE ({attempts.length} {attempts.length === 1 ? 'ATTEMPT' : 'ATTEMPTS'})</span>
        </div>
        <div className="text-xs text-slate-400">
          Formal CEGIS verification log
        </div>
      </div>

      <div className="space-y-3">
        {attempts.map((att) => {
          const isVerified =
            att.status === 'QF_BV_UNSAT_64BIT_VERIFIED' || att.status === 'UNSAT';
          const isSAT = att.status === 'SAT';
          const isInvalid = att.status === 'INVALID';
          const isThinkOpen = expandedThinks[att.iteration] ?? (isVerified || isSAT);

          return (
            <div
              key={att.iteration}
              className={`rounded-lg border transition-all ${
                isVerified
                  ? 'bg-emerald-950/20 border-emerald-500/50 shadow-[0_0_12px_rgba(16,185,129,0.15)]'
                  : isSAT
                  ? 'bg-cyber-bg border-amber-900/40'
                  : 'bg-cyber-bg border-rose-900/40'
              } p-4`}
            >
              {/* Card Header */}
              <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 mb-3">
                <div className="flex items-center gap-2.5">
                  <span className="w-6 h-6 rounded-md bg-slate-800 text-cyan-400 border border-slate-700 flex items-center justify-center text-xs font-bold font-mono">
                    #{att.iteration}
                  </span>
                  <div className="font-mono text-sm text-slate-200">
                    Candidate: <span className="text-cyan-300 font-semibold">{att.candidate || '<empty>'}</span>
                  </div>
                </div>

                <div className="flex items-center gap-2">
                  {/* Z3 Latency Badge */}
                  {att.latency_ms !== undefined && (
                    <div className="flex items-center gap-1 text-[11px] font-mono text-slate-400 bg-slate-900/80 px-2 py-0.5 rounded border border-slate-800">
                      <Clock className="w-3 h-3 text-cyan-400" />
                      <span>{att.latency_ms} ms</span>
                    </div>
                  )}

                  {/* Status Badge */}
                  {isVerified ? (
                    <span className="flex items-center gap-1 text-xs font-mono font-semibold px-2.5 py-0.5 rounded bg-emerald-950 border border-emerald-500/50 text-emerald-300">
                      <CheckCircle className="w-3.5 h-3.5 text-emerald-400" />
                      UNSAT (Verified)
                    </span>
                  ) : isSAT ? (
                    <span className="flex items-center gap-1 text-xs font-mono font-semibold px-2.5 py-0.5 rounded bg-amber-950/60 border border-amber-500/50 text-amber-300">
                      <AlertTriangle className="w-3.5 h-3.5 text-amber-400" />
                      SAT (Counterexample)
                    </span>
                  ) : isInvalid ? (
                    <span className="flex items-center gap-1 text-xs font-mono font-semibold px-2.5 py-0.5 rounded bg-rose-950/60 border border-rose-500/50 text-rose-300">
                      <XCircle className="w-3.5 h-3.5 text-rose-400" />
                      INVALID CANDIDATE
                    </span>
                  ) : (
                    <span className="text-xs font-mono px-2 py-0.5 rounded bg-slate-800 text-slate-400">
                      {att.status || 'PENDING'}
                    </span>
                  )}
                </div>
              </div>

              {/* Model Reasoning <think> Block */}
              {att.think && (
                <div className="mb-3">
                  <button
                    type="button"
                    onClick={() => toggleThink(att.iteration)}
                    className="flex items-center gap-1.5 text-xs font-medium text-slate-400 hover:text-slate-200 transition-colors mb-1"
                  >
                    <Brain className="w-3.5 h-3.5 text-cyan-400" />
                    <span>Model-Generated Reasoning (Unverified Proposal)</span>
                    {isThinkOpen ? (
                      <ChevronDown className="w-3.5 h-3.5" />
                    ) : (
                      <ChevronRight className="w-3.5 h-3.5" />
                    )}
                  </button>

                  {isThinkOpen && (
                    <div className="p-3 rounded bg-slate-950/80 border border-slate-800/80 text-xs font-mono text-slate-300 leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto">
                      <div className="text-[10px] text-amber-400/90 font-mono mb-2 pb-1.5 border-b border-slate-800 flex items-center gap-1">
                        <span>⚠ Heuristic fast guess: Model output is not authoritative. Equivalence is verified strictly by Z3 below.</span>
                      </div>
                      {att.think}
                    </div>
                  )}
                </div>
              )}

              {/* Counterexample Visualizer (if SAT) */}
              {isSAT && att.witness && (
                <BitVisualizer
                  witness={att.witness}
                  expected={att.expected ?? null}
                  actual={att.actual ?? null}
                  diffBits={att.diff_bits ?? null}
                  explainMode={explainMode}
                />
              )}

              {/* Retry Feedback Sent to Next Iteration */}
              {att.feedback_message && (
                <div className="mt-2 p-2.5 rounded bg-slate-900/60 border border-slate-800 text-xs font-mono">
                  <div className="flex items-center gap-1.5 text-slate-400 mb-1">
                    <MessageSquare className="w-3.5 h-3.5 text-amber-400" />
                    <span className="font-semibold text-slate-300">CEGIS Feedback Injected:</span>
                  </div>
                  <pre className="text-amber-200/90 whitespace-pre-wrap text-[11px]">
                    {att.feedback_message}
                  </pre>
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
};
