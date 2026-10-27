import React, { useState } from 'react';
import { Play, Square, AlertTriangle, AlertCircle, Sparkles, RefreshCw } from 'lucide-react';
import { ExplainTooltip } from './ExplainTooltip';

interface CommandCenterProps {
  expression: string;
  setExpression: (expr: string) => void;
  maxIterations: number;
  setMaxIterations: (val: number) => void;
  isRunning: boolean;
  is429Blocked: boolean;
  retryCountdown: number;
  error: string | null;
  clearError: () => void;
  onStartRun: (expr: string, maxIters: number) => void;
  onCancelRun: () => void;
  explainMode: boolean;
}

const PRESETS = [
  {
    label: 'Classic 2-Turn Demo',
    expr: '(x ^ y) + 2 * (x & y)',
    desc: 'MBA sum identity. In Demo mode, guess 1 fails with witness (x=1,y=1), guess 2 succeeds with x + y.',
  },
  {
    label: 'Bitwise AND',
    expr: '(x | y) - (x ^ y)',
    desc: 'Rewrites (x | y) - (x ^ y) into simpler x & y.',
  },
  {
    label: 'Bitwise XOR',
    expr: '(x & ~y) + (y & ~x)',
    desc: 'Combines two disjoint bit masks into x ^ y.',
  },
  {
    label: 'OR / AND Sum',
    expr: '(x & y) + (x | y)',
    desc: 'Common addition rewrite into x + y.',
  },
  {
    label: 'Negated Addition',
    expr: '(x ^ ~y) + 2 * (x | y) + 1',
    desc: 'Obfuscated identity utilizing bitwise NOT on 64-bit words.',
  },
];

export const CommandCenter: React.FC<CommandCenterProps> = ({
  expression,
  setExpression,
  maxIterations,
  setMaxIterations,
  isRunning,
  is429Blocked,
  retryCountdown,
  error,
  clearError,
  onStartRun,
  onCancelRun,
  explainMode,
}) => {
  const [copiedPreset, setCopiedPreset] = useState<string | null>(null);

  const handleSelectPreset = (expr: string, label: string) => {
    setExpression(expr);
    setCopiedPreset(label);
    setTimeout(() => setCopiedPreset(null), 1500);
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (!expression.trim() || isRunning || is429Blocked) return;
    onStartRun(expression, maxIterations);
  };

  return (
    <div className="bg-cyber-surface border border-cyber-border rounded-xl p-5 shadow-lg">
      {/* 429 Concurrency Backoff Banner */}
      {is429Blocked && (
        <div className="mb-4 p-4 rounded-lg bg-amber-950/40 border border-amber-500/50 text-amber-200 flex items-start gap-3">
          <AlertTriangle className="w-5 h-5 text-amber-400 shrink-0 mt-0.5 animate-pulse" />
          <div className="flex-1 text-sm">
            <div className="font-semibold text-amber-300">Previous Run Still Finishing</div>
            <p className="mt-0.5 text-slate-300">
              Only 1 local inference run is supported at a time. Concurrency lock is active. Resuming in{' '}
              <span className="font-mono font-bold text-amber-400">{retryCountdown}s</span>...
            </p>
            <div className="mt-2 w-full bg-slate-900/80 rounded-full h-1.5 overflow-hidden">
              <div
                className="bg-amber-400 h-full transition-all duration-1000 ease-linear"
                style={{ width: `${Math.min(100, (retryCountdown / 5) * 100)}%` }}
              />
            </div>
          </div>
        </div>
      )}

      {/* General Error Banner */}
      {error && !is429Blocked && (
        <div className="mb-4 p-4 rounded-lg bg-rose-950/40 border border-rose-500/50 text-rose-200 flex items-start justify-between gap-3">
          <div className="flex items-start gap-3">
            <AlertCircle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
            <div className="text-sm">
              <div className="font-semibold text-rose-300">Synthesis Error</div>
              <p className="mt-0.5 text-slate-300">{error}</p>
            </div>
          </div>
          <button
            onClick={clearError}
            className="text-xs text-rose-300 hover:text-white px-2 py-1 rounded bg-rose-900/40 hover:bg-rose-900/60 transition-colors"
          >
            Dismiss
          </button>
        </div>
      )}

      <form onSubmit={handleSubmit} className="space-y-4">
        {/* Expression Input Area */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <label htmlFor="mba-input" className="text-xs font-semibold text-slate-300 flex items-center gap-1.5">
              <span>OBFUSCATED 64-BIT MBA EXPRESSION</span>
              <ExplainTooltip topic="mba" explainMode={explainMode} inline />
            </label>
            <span className="text-xs text-slate-500 font-mono">
              {expression.length} / 5,000 chars
            </span>
          </div>

          <div className="relative">
            <textarea
              id="mba-input"
              rows={3}
              value={expression}
              onChange={(e) => setExpression(e.target.value)}
              placeholder="Enter scrambled MBA expression (e.g. (x ^ y) + 2 * (x & y))..."
              disabled={isRunning}
              className="w-full bg-cyber-bg border border-cyber-border rounded-lg px-4 py-3 font-mono text-sm text-cyan-300 placeholder-slate-600 focus:outline-none focus:border-cyan-500 focus:ring-1 focus:ring-cyan-500/50 transition-all resize-none disabled:opacity-60"
            />
          </div>
        </div>

        {/* Presets Row */}
        <div>
          <div className="text-xs font-semibold text-slate-400 mb-2 flex items-center gap-1.5">
            <Sparkles className="w-3.5 h-3.5 text-cyan-400" />
            <span>EXPRESSION PRESETS</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {PRESETS.map((preset) => (
              <button
                key={preset.label}
                type="button"
                disabled={isRunning}
                onClick={() => handleSelectPreset(preset.expr, preset.label)}
                title={preset.desc}
                className="px-2.5 py-1.5 rounded-md text-xs font-mono bg-cyber-bg border border-cyber-border text-slate-300 hover:border-cyan-500/50 hover:text-cyan-300 hover:bg-cyan-950/20 transition-all disabled:opacity-50 text-left"
              >
                {copiedPreset === preset.label ? (
                  <span className="text-emerald-400 font-semibold">✓ Loaded</span>
                ) : (
                  <span>{preset.label}</span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* Controls: Iterations slider & Action buttons */}
        <div className="pt-2 border-t border-cyber-border flex flex-col sm:flex-row sm:items-center justify-between gap-4">
          {/* Max Iterations Slider */}
          <div className="flex items-center gap-3">
            <label htmlFor="max-iters" className="text-xs font-medium text-slate-400 flex items-center gap-1">
              <span>Max CEGIS Loops:</span>
              <span className="font-mono text-cyan-400 font-semibold ml-1">{maxIterations}</span>
              <ExplainTooltip topic="cegis" explainMode={explainMode} inline />
            </label>
            <input
              id="max-iters"
              type="range"
              min="1"
              max="10"
              value={maxIterations}
              onChange={(e) => setMaxIterations(parseInt(e.target.value, 10))}
              disabled={isRunning}
              className="w-28 accent-cyan-400 cursor-pointer disabled:opacity-50"
            />
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2">
            {isRunning ? (
              <button
                type="button"
                onClick={onCancelRun}
                className="flex items-center gap-2 px-4 py-2 rounded-lg text-xs font-semibold bg-rose-950/80 border border-rose-500/50 text-rose-300 hover:bg-rose-900 transition-all shadow-[0_0_10px_rgba(239,68,68,0.2)]"
              >
                <Square className="w-3.5 h-3.5 fill-current" />
                <span>Abort Run</span>
              </button>
            ) : null}

            <button
              type="submit"
              disabled={isRunning || is429Blocked || !expression.trim()}
              className={`flex items-center gap-2 px-5 py-2.5 rounded-lg text-xs font-bold font-mono tracking-wider transition-all ${
                is429Blocked
                  ? 'bg-amber-950/40 border border-amber-600/50 text-amber-400 cursor-not-allowed'
                  : isRunning
                  ? 'bg-cyan-950 border border-cyan-500/40 text-cyan-300 cursor-wait'
                  : 'bg-cyan-500 hover:bg-cyan-400 text-slate-950 shadow-[0_0_15px_rgba(6,182,212,0.4)] hover:shadow-[0_0_20px_rgba(6,182,212,0.6)] cursor-pointer'
              } disabled:opacity-50`}
            >
              {is429Blocked ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin text-amber-400" />
                  <span>WAIT ({retryCountdown}s)</span>
                </>
              ) : isRunning ? (
                <>
                  <RefreshCw className="w-3.5 h-3.5 animate-spin text-cyan-400" />
                  <span>DE-OBFUSCATING...</span>
                </>
              ) : (
                <>
                  <Play className="w-3.5 h-3.5 fill-current" />
                  <span>DE-OBFUSCATE</span>
                </>
              )}
            </button>
          </div>
        </div>
      </form>
    </div>
  );
};

