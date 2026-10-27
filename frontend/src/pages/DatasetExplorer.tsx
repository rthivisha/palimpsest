import React, { useEffect, useState } from 'react';
import { BookOpen, ArrowRight, Sparkles } from 'lucide-react';
import { ExampleExpr } from '../types';

interface DatasetExplorerProps {
  onLoadExpression: (expr: string) => void;
  onNavigateToMain: () => void;
}

export const DatasetExplorer: React.FC<DatasetExplorerProps> = ({
  onLoadExpression,
  onNavigateToMain,
}) => {
  const [examples, setExamples] = useState<ExampleExpr[]>([]);
  const [loading, setLoading] = useState<boolean>(true);

  useEffect(() => {
    fetch('/api/examples')
      .then((res) => (res.ok ? res.json() : []))
      .then((data) => {
        setExamples(data);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const handleSelect = (expr: string) => {
    onLoadExpression(expr);
    onNavigateToMain();
  };

  return (
    <div className="space-y-6">
      <div>
        <div className="flex items-center gap-2 mb-1">
          <BookOpen className="w-5 h-5 text-cyan-400" />
          <h2 className="text-lg font-bold font-mono text-slate-100">
            DATASET EXPLORER (ILLUSTRATIVE PRESETS)
          </h2>
          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-amber-950/60 text-amber-400 border border-amber-500/40 font-semibold uppercase">
            Illustrative Only
          </span>
        </div>
        <p className="text-xs text-slate-400 mt-0.5">
          Educational illustrative examples demonstrating algebraic MBA simplification. Formal benchmark evaluation dataset (samples.jsonl) is separate and will be loaded upon delivery.
        </p>
      </div>

      {loading ? (
        <div className="p-8 text-center text-slate-500 font-mono text-sm">
          Loading benchmark presets...
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {examples.map((item, idx) => (
            <div
              key={idx}
              className="bg-cyber-surface border border-cyber-border rounded-xl p-5 shadow-lg flex flex-col justify-between space-y-4 hover:border-cyan-500/40 transition-colors"
            >
              <div>
                <div className="flex items-center justify-between mb-2">
                  <div className="text-sm font-bold font-mono text-slate-200 flex items-center gap-2">
                    <Sparkles className="w-4 h-4 text-cyan-400" />
                    <span>{item.title || item.name}</span>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-[9px] font-mono uppercase px-1.5 py-0.5 rounded bg-amber-950/50 text-amber-400 border border-amber-600/30 font-medium">
                      Illustrative
                    </span>
                    <div className="flex items-center gap-1.5 text-[11px] font-mono text-slate-400">
                      <span>Vars:</span>
                      <span className="text-cyan-300 font-semibold">{item.variables ? item.variables.join(', ') : 'none'}</span>
                    </div>
                  </div>
                </div>

                <p className="text-xs text-slate-400 mb-3">{item.description}</p>

                {/* Scrambled MBA Input */}
                <div className="mb-2 p-2.5 rounded bg-cyber-bg border border-cyber-border text-xs font-mono">
                  <span className="text-slate-500 block text-[10px] uppercase font-semibold mb-0.5">
                    Scrambled MBA Input
                  </span>
                  <div className="text-cyan-300 break-all">{item.expression}</div>
                </div>

                {/* Step-by-Step Algebraic Transformation Steps */}
                {item.transformation_steps && item.transformation_steps.length > 0 && (
                  <div className="mb-2 p-3 rounded bg-slate-900/60 border border-slate-800 text-xs font-mono">
                    <span className="text-amber-300 font-semibold block text-[11px] mb-1.5">
                      Algebraic De-obfuscation & Reasoning Steps:
                    </span>
                    <ol className="space-y-1 text-slate-300 text-[11px] leading-relaxed">
                      {item.transformation_steps.map((step, sIdx) => (
                        <li key={sIdx} className="pl-1.5 border-l-2 border-cyan-500/40">
                          {step}
                        </li>
                      ))}
                    </ol>
                  </div>
                )}

                {/* Target Canonical Form */}
                <div className="p-2.5 rounded bg-emerald-950/20 border border-emerald-900/40 text-xs font-mono">
                  <span className="text-emerald-500/80 block text-[10px] uppercase font-semibold mb-0.5">
                    Target Canonical Identity
                  </span>
                  <div className="text-emerald-300 font-bold">{item.expected_simplified}</div>
                </div>
              </div>

              <div className="pt-2 border-t border-cyber-border flex items-center justify-end">
                <button
                  type="button"
                  onClick={() => handleSelect(item.expression)}
                  className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono font-semibold bg-cyan-500/10 border border-cyan-500/30 text-cyan-300 hover:bg-cyan-500 hover:text-slate-950 transition-all shadow-[0_0_8px_rgba(6,182,212,0.2)]"
                >
                  <span>Load into De-obfuscator</span>
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
