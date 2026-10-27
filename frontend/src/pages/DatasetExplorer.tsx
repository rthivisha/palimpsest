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
        <h2 className="text-lg font-bold font-mono text-slate-100 flex items-center gap-2">
          <BookOpen className="w-5 h-5 text-cyan-400" />
          <span>DATASET EXPLORER & MBA REASONING BENCHMARK</span>
        </h2>
        <p className="text-xs text-slate-400 mt-0.5">
          Curated Mixed Boolean-Arithmetic benchmarks demonstrating algebraic identities, bit-vector semantics, and opaque terms.
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
                    <span>{item.name}</span>
                  </div>
                  <div className="flex items-center gap-1.5 text-[11px] font-mono text-slate-400">
                    <span>Vars:</span>
                    <span className="text-cyan-300 font-semibold">{item.variables.join(', ')}</span>
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
