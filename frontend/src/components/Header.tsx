import React, { useEffect, useState } from 'react';
import { ShieldCheck, Cpu, HelpCircle, Activity, Database, BookOpen } from 'lucide-react';
import { SystemHealth } from '../types';

interface HeaderProps {
  activeTab: 'main' | 'history' | 'dataset';
  setActiveTab: (tab: 'main' | 'history' | 'dataset') => void;
  explainMode: boolean;
  setExplainMode: React.Dispatch<React.SetStateAction<boolean>>;
  backend?: string | null;
  modelName?: string | null;
}

export const Header: React.FC<HeaderProps> = ({
  activeTab,
  setActiveTab,
  explainMode,
  setExplainMode,
  backend: runBackend,
  modelName: runModelName,
}) => {
  const [health, setHealth] = useState<SystemHealth | null>(null);

  useEffect(() => {
    fetch('/api/health')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) setHealth(data);
      })
      .catch(() => {});
  }, []);

  const activeBackend = runBackend || health?.backend || 'fake';
  const activeModel = runModelName || health?.model_name || (activeBackend === 'fake' ? 'fake-scripted' : '');

  return (
    <header className="w-full border-b border-cyber-border bg-cyber-surface/90 backdrop-blur sticky top-0 z-50 px-4 sm:px-6 lg:px-8 py-2.5">
      <div className="w-full max-w-7xl mx-auto flex flex-col md:flex-row items-center justify-between gap-3 overflow-visible">
        {/* Logo and Codename */}
        <div className="flex items-center gap-3">
          <div className="h-10 w-10 rounded-lg bg-cyan-950 border border-cyan-500/40 flex items-center justify-center text-cyan-400 shadow-[0_0_12px_rgba(6,182,212,0.3)]">
            <Cpu className="w-5 h-5 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-mono font-bold tracking-wider text-lg text-slate-100">PALIMPSEST</span>
              <span className="text-xs px-2 py-0.5 rounded bg-cyan-950/80 border border-cyan-500/30 text-cyan-400 font-mono">
                VEX-MORPH
              </span>
            </div>
            <p className="text-xs text-slate-400">
              Neurosymbolic 64-bit MBA De-obfuscation Engine
            </p>
          </div>
        </div>

        {/* Navigation Tabs */}
        <nav className="flex items-center gap-1 bg-cyber-bg p-1 rounded-lg border border-cyber-border">
          <button
            onClick={() => setActiveTab('main')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeTab === 'main'
                ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 shadow-[0_0_8px_rgba(6,182,212,0.2)]'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Activity className="w-3.5 h-3.5" />
            De-obfuscator
          </button>
          <button
            onClick={() => setActiveTab('history')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeTab === 'history'
                ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 shadow-[0_0_8px_rgba(6,182,212,0.2)]'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <Database className="w-3.5 h-3.5" />
            History & Insights
          </button>
          <button
            onClick={() => setActiveTab('dataset')}
            className={`flex items-center gap-2 px-3 py-1.5 rounded-md text-xs font-medium transition-all ${
              activeTab === 'dataset'
                ? 'bg-cyan-500/10 text-cyan-400 border border-cyan-500/30 shadow-[0_0_8px_rgba(6,182,212,0.2)]'
                : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            <BookOpen className="w-3.5 h-3.5" />
            Dataset Explorer
          </button>
        </nav>

        {/* System Badges & Explain Mode Toggle */}
        <div className="flex items-center gap-2 flex-wrap justify-end">
          {/* Backend Badge & Model Name */}
          <div
            className="flex items-center gap-1.5 px-2.5 py-1 rounded border border-cyber-border bg-cyber-bg text-xs font-mono"
            title="Active Model Inference Engine"
          >
            <span className={`w-2 h-2 rounded-full ${activeBackend === 'fake' ? 'bg-amber-400' : 'bg-cyan-400 animate-ping'}`} />
            <span className="text-slate-400">LLM:</span>
            <span className="text-cyan-300 font-semibold uppercase">{activeBackend}</span>
            {activeModel && (
              <span className="text-slate-400 border-l border-slate-700 pl-1.5 text-[11px]">
                {activeModel}
              </span>
            )}
          </div>

          {/* SMT Solver Badge */}
          <div
            className="flex items-center gap-1.5 px-2.5 py-1 rounded border border-emerald-900/50 bg-emerald-950/20 text-xs font-mono text-emerald-300"
            title="SMT Solver: Bit-Vector Equivalence Prover"
          >
            <ShieldCheck className="w-3.5 h-3.5 text-emerald-400" />
            <span>Z3 QF_BV (64-bit)</span>
          </div>

          {/* Explain Mode Toggle */}
          <button
            onClick={() => setExplainMode((prev) => !prev)}
            className={`flex items-center gap-1.5 px-3 py-1 rounded text-xs font-medium border transition-all ${
              explainMode
                ? 'bg-amber-950/60 border-amber-500/60 text-amber-300 shadow-[0_0_10px_rgba(245,158,11,0.25)]'
                : 'bg-cyber-bg border-cyber-border text-slate-400 hover:text-slate-200'
            }`}
            title="Toggle plain-English explanations of MBA, CEGIS, Bit-Vectors, and SMT solving"
          >
            <HelpCircle className="w-3.5 h-3.5" />
            <span>Explain Mode {explainMode ? 'ON' : 'OFF'}</span>
          </button>
        </div>
      </div>
    </header>
  );
};

