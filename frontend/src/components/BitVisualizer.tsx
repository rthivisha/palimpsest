import React from 'react';
import { Binary } from 'lucide-react';
import { ExplainTooltip } from './ExplainTooltip';

interface BitVisualizerProps {
  witness: Record<string, string>;
  expected: string | null;
  actual: string | null;
  diffBits: string | null;
  explainMode: boolean;
}

export const BitVisualizer: React.FC<BitVisualizerProps> = ({
  witness,
  expected,
  actual,
  diffBits,
  explainMode,
}) => {
  if (!diffBits || expected === null || actual === null) return null;

  // Format decimal to 64-bit hex representation
  const formatHex = (valStr: string): string => {
    try {
      const bn = BigInt(valStr);
      return '0x' + bn.toString(16).padStart(16, '0').toUpperCase();
    } catch {
      return '0x????????????????';
    }
  };

  // Convert 64-bit unsigned string to 64-character binary string (MSB bit 63 to LSB bit 0)
  const formatBin = (valStr: string): string => {
    try {
      const bn = BigInt(valStr);
      return bn.toString(2).padStart(64, '0');
    } catch {
      return '0'.repeat(64);
    }
  };

  const expectedBin = formatBin(expected);
  const actualBin = formatBin(actual);

  // Pad diffBits to 64 characters if needed
  const diffPadded = diffBits.padStart(64, '0');

  // Count mismatched bits
  const mismatchCount = (diffPadded.match(/1/g) || []).length;

  return (
    <div className="bg-[#0b101b] border border-amber-900/40 rounded-lg p-3.5 my-2.5">
      <div className="flex items-center justify-between mb-2">
        <div className="flex items-center gap-1.5 text-xs font-semibold text-amber-300 font-mono">
          <Binary className="w-4 h-4 text-amber-400" />
          <span>COUNTEREXAMPLE 64-BIT BIT-LEVEL DIFF</span>
          <ExplainTooltip topic="bitvec" explainMode={explainMode} inline />
        </div>
        <span className="text-[11px] font-mono px-2 py-0.5 rounded bg-rose-950/60 border border-rose-500/40 text-rose-300">
          {mismatchCount} differing {mismatchCount === 1 ? 'bit' : 'bits'}
        </span>
      </div>

      {/* Concrete Witness Inputs */}
      <div className="mb-3 p-2 rounded bg-slate-900/80 border border-slate-800 text-xs font-mono">
        <span className="text-slate-400 mr-2">Counterexample Input:</span>
        {Object.entries(witness).map(([v, val], idx) => (
          <span key={v} className="inline-block mr-3">
            <span className="text-cyan-400 font-bold">{v}</span>
            <span className="text-slate-500"> = </span>
            <span className="text-slate-200">{val}</span>
            <span className="text-slate-500 text-[10px] ml-1">({formatHex(val)})</span>
            {idx < Object.entries(witness).length - 1 ? ',' : ''}
          </span>
        ))}
      </div>

      {/* Expected vs Actual Comparison */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 text-xs font-mono mb-3">
        <div className="p-2 rounded bg-emerald-950/20 border border-emerald-900/40">
          <div className="text-emerald-400 font-semibold mb-0.5">Expected (Original Expression):</div>
          <div className="text-slate-200 truncate">{expected}</div>
          <div className="text-emerald-500/70 text-[11px]">{formatHex(expected)}</div>
        </div>

        <div className="p-2 rounded bg-rose-950/20 border border-rose-900/40">
          <div className="text-rose-400 font-semibold mb-0.5">Actual (Model Candidate):</div>
          <div className="text-slate-200 truncate">{actual}</div>
          <div className="text-rose-500/70 text-[11px]">{formatHex(actual)}</div>
        </div>
      </div>

      {/* 64-bit Bit Row Diff */}
      <div className="space-y-1">
        <div className="flex justify-between text-[10px] text-slate-500 font-mono px-0.5">
          <span>Bit 63 (MSB)</span>
          <span>Bit 0 (LSB)</span>
        </div>

        {/* Diff Grid */}
        <div className="grid grid-cols-64 gap-[1px] bg-slate-900 p-1.5 rounded border border-slate-800 overflow-x-auto">
          {Array.from({ length: 64 }).map((_, i) => {
            const isDiff = diffPadded[i] === '1';
            const expBit = expectedBin[i];
            const actBit = actualBin[i];
            const bitIndex = 63 - i;

            return (
              <div
                key={i}
                title={`Bit ${bitIndex}: Expected ${expBit}, Got ${actBit} ${isDiff ? '(MISMATCH)' : '(Match)'}`}
                className={`h-6 min-w-[7px] flex items-center justify-center rounded-[1px] text-[8px] font-mono transition-colors ${
                  isDiff
                    ? 'bg-rose-500 text-white font-bold shadow-[0_0_6px_rgba(239,68,68,0.8)]'
                    : 'bg-slate-800/80 text-slate-500 hover:bg-slate-700 hover:text-slate-200'
                }`}
              >
                {isDiff ? '!' : ''}
              </div>
            );
          })}
        </div>

        <div className="flex items-center justify-between text-[10px] text-slate-400 pt-1">
          <div className="flex items-center gap-3">
            <span className="flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-[1px] bg-rose-500" />
              <span className="text-rose-300">Mismatch (diff=1)</span>
            </span>
            <span className="flex items-center gap-1">
              <span className="w-2.5 h-2.5 rounded-[1px] bg-slate-800" />
              <span>Equivalent bit (diff=0)</span>
            </span>
          </div>
          <span className="text-slate-500 italic">Hover bit block for bit index & values</span>
        </div>
      </div>
    </div>
  );
};
