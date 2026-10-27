import React, { useEffect, useState } from 'react';
import {
  BarChart,
  Bar,
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts';
import { Database, RotateCcw } from 'lucide-react';
import { RunSummary, StatsResponse, RunDetail } from '../types';

interface HistoryPageProps {
  onReplayRun: (detail: RunDetail) => void;
  onNavigateToMain: () => void;
}

export const HistoryPage: React.FC<HistoryPageProps> = ({ onReplayRun, onNavigateToMain }) => {
  const [history, setHistory] = useState<RunSummary[]>([]);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);
  const [hideFake, setHideFake] = useState<boolean>(false);

  const fetchTelemetry = async (excludeFake: boolean = false) => {
    setLoading(true);
    setError(null);
    try {
      const [histRes, statsRes] = await Promise.all([
        fetch(`/api/history?limit=50&exclude_fake=${excludeFake}`),
        fetch(`/api/stats?exclude_fake=${excludeFake}`),
      ]);

      if (histRes.ok) {
        const histData = await histRes.json();
        setHistory(histData);
      }
      if (statsRes.ok) {
        const statsData = await statsRes.json();
        setStats(statsData);
      }
    } catch (err: any) {
      setError(err.message || 'Failed to load telemetry history from SQLite.');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchTelemetry(hideFake);
  }, [hideFake]);

  const handleInspect = async (runId: string) => {
    try {
      const res = await fetch(`/api/runs/${runId}`);
      if (res.ok) {
        const detail: RunDetail = await res.json();
        onReplayRun(detail);
        onNavigateToMain();
      }
    } catch (err) {
      console.error('Failed to load run detail:', err);
    }
  };

  // Prepare chart data: 1. Attempts distribution
  const attemptsDist = [
    { name: '1 Turn', count: 0 },
    { name: '2 Turns', count: 0 },
    { name: '3 Turns', count: 0 },
    { name: '4+ Turns', count: 0 },
  ];

  history.forEach((run) => {
    if (run.attempts === 1) attemptsDist[0].count += 1;
    else if (run.attempts === 2) attemptsDist[1].count += 1;
    else if (run.attempts === 3) attemptsDist[2].count += 1;
    else if (run.attempts >= 4) attemptsDist[3].count += 1;
  });

  // Prepare chart data: 2. Success Rate ratio
  const successRatioData = [
    { name: 'Verified (UNSAT)', count: stats?.verified_runs || 0 },
    { name: 'Failed / Unverified', count: stats?.failed_runs || 0 },
  ];

  // Prepare chart data: 3. Z3 Latency Progression across recent runs
  const latencyData = history
    .slice(0, 10)
    .reverse()
    .map((run, idx) => ({
      name: `Run ${idx + 1}`,
      latency: run.total_ms,
      status: run.final_status,
    }));

  return (
    <div className="space-y-6">
      {/* Page Header */}
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-lg font-bold font-mono text-slate-100 flex items-center gap-2">
            <Database className="w-5 h-5 text-cyan-400" />
            <span>TELEMETRY & INSIGHTS (SQLITE WAL)</span>
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Historical de-obfuscation records and solver metrics persisted locally.
          </p>
        </div>

        <div className="flex items-center gap-2">
          <label className="flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-mono bg-cyber-surface border border-cyber-border text-slate-300 cursor-pointer hover:border-cyan-500/40 transition-colors">
            <input
              type="checkbox"
              checked={hideFake}
              onChange={(e) => setHideFake(e.target.checked)}
              className="rounded bg-slate-900 border-slate-700 text-cyan-500 focus:ring-0 focus:ring-offset-0 cursor-pointer"
            />
            <span>Hide FAKE runs</span>
          </label>

          <button
            onClick={() => fetchTelemetry(hideFake)}
            className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-mono bg-cyber-surface border border-cyber-border text-slate-300 hover:text-cyan-400 hover:border-cyan-500/40 transition-colors"
          >
            <RotateCcw className="w-3.5 h-3.5" />
            <span>Refresh</span>
          </button>
        </div>
      </div>

      {/* Aggregate Stats Cards */}
      {stats && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div className="bg-cyber-surface border border-cyber-border rounded-xl p-4">
            <div className="text-xs font-medium text-slate-400 font-mono">TOTAL RUNS</div>
            <div className="text-2xl font-bold font-mono text-slate-100 mt-1">{stats.total_runs}</div>
            <div className="text-[11px] text-slate-500 mt-1">Recorded in telemetry database</div>
          </div>

          <div className="bg-cyber-surface border border-cyber-border rounded-xl p-4">
            <div className="text-xs font-medium text-slate-400 font-mono">VERIFIED BY Z3</div>
            <div className="text-2xl font-bold font-mono text-emerald-400 mt-1">
              {stats.verified_runs}{' '}
              <span className="text-xs font-normal text-slate-400">({stats.success_rate_pct}%)</span>
            </div>
            <div className="text-[11px] text-slate-500 mt-1">QF_BV mathematical proofs</div>
          </div>

          <div className="bg-cyber-surface border border-cyber-border rounded-xl p-4">
            <div className="text-xs font-medium text-slate-400 font-mono">AVG LATENCY</div>
            <div className="text-2xl font-bold font-mono text-cyan-400 mt-1">
              {stats.avg_total_ms} <span className="text-xs font-normal text-slate-400">ms</span>
            </div>
            <div className="text-[11px] text-slate-500 mt-1">Total runtime per synthesis</div>
          </div>

          <div className="bg-cyber-surface border border-cyber-border rounded-xl p-4">
            <div className="text-xs font-medium text-slate-400 font-mono">AVG CEGIS LOOPS</div>
            <div className="text-2xl font-bold font-mono text-amber-400 mt-1">
              {stats.avg_attempts} <span className="text-xs font-normal text-slate-400">turns</span>
            </div>
            <div className="text-[11px] text-slate-500 mt-1">Iterations until resolution</div>
          </div>
        </div>
      )}

      {/* Analytics Charts Grid: Attempts, Success Rate, Z3 Latency */}
      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Chart 1: Attempts per Run */}
        <div className="bg-cyber-surface border border-cyber-border rounded-xl p-4 shadow-lg">
          <div className="text-xs font-semibold text-slate-300 font-mono mb-3 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-cyan-400" />
            <span>ATTEMPTS PER RUN</span>
          </div>
          <div className="h-40 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={attemptsDist} margin={{ top: 10, right: 10, left: -25, bottom: 0 }}>
                <XAxis dataKey="name" stroke="#64748b" fontSize={10} tickLine={false} />
                <YAxis stroke="#64748b" fontSize={10} tickLine={false} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0f172a',
                    borderColor: '#1e293b',
                    fontSize: '11px',
                    fontFamily: 'monospace',
                  }}
                />
                <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                  {attemptsDist.map((_, index) => (
                    <Cell key={`cell-att-${index}`} fill={index === 0 ? '#10b981' : index === 1 ? '#06b6d4' : '#f59e0b'} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Chart 2: Success Rate (Verification Ratio) */}
        <div className="bg-cyber-surface border border-cyber-border rounded-xl p-4 shadow-lg">
          <div className="text-xs font-semibold text-slate-300 font-mono mb-3 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-emerald-400" />
            <span>SUCCESS RATE RATIO</span>
          </div>
          <div className="h-40 w-full">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={successRatioData} margin={{ top: 10, right: 10, left: -25, bottom: 0 }}>
                <XAxis dataKey="name" stroke="#64748b" fontSize={10} tickLine={false} />
                <YAxis stroke="#64748b" fontSize={10} tickLine={false} allowDecimals={false} />
                <Tooltip
                  contentStyle={{
                    backgroundColor: '#0f172a',
                    borderColor: '#1e293b',
                    fontSize: '11px',
                    fontFamily: 'monospace',
                  }}
                />
                <Bar dataKey="count" radius={[3, 3, 0, 0]}>
                  <Cell fill="#10b981" />
                  <Cell fill="#ef4444" />
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        {/* Chart 3: Z3 Latency Progression (ms) */}
        <div className="bg-cyber-surface border border-cyber-border rounded-xl p-4 shadow-lg">
          <div className="text-xs font-semibold text-slate-300 font-mono mb-3 flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-amber-400" />
            <span>Z3 LATENCY PROGRESSION (ms)</span>
          </div>
          <div className="h-40 w-full">
            {latencyData.length > 0 ? (
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={latencyData} margin={{ top: 10, right: 10, left: -20, bottom: 0 }}>
                  <XAxis dataKey="name" stroke="#64748b" fontSize={10} tickLine={false} />
                  <YAxis stroke="#64748b" fontSize={10} tickLine={false} />
                  <Tooltip
                    contentStyle={{
                      backgroundColor: '#0f172a',
                      borderColor: '#1e293b',
                      fontSize: '11px',
                      fontFamily: 'monospace',
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="latency"
                    stroke="#06b6d4"
                    fill="rgba(6, 182, 212, 0.2)"
                    strokeWidth={2}
                  />
                </AreaChart>
              </ResponsiveContainer>
            ) : (
              <div className="h-full flex items-center justify-center text-slate-500 font-mono text-xs">
                No latency history recorded yet
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Run History Table */}
      <div className="bg-cyber-surface border border-cyber-border rounded-xl shadow-lg overflow-hidden">
        <div className="p-4 border-b border-cyber-border flex items-center justify-between">
          <div className="text-xs font-semibold text-slate-300 font-mono">
            PERSISTED RUNS LOG ({history.length})
          </div>
          <span className="text-[11px] text-slate-500 font-mono">Click Inspect to replay in graph</span>
        </div>

        {error && (
          <div className="p-4 bg-rose-950/40 border border-rose-500/50 text-rose-300 rounded-lg text-xs font-mono">
            {error}
          </div>
        )}

        {loading ? (
          <div className="p-8 text-center text-slate-500 font-mono text-sm">
            Loading telemetry records...
          </div>
        ) : history.length === 0 ? (
          <div className="p-8 text-center text-slate-500 text-sm">
            No runs recorded in telemetry yet. Run expressions in the De-obfuscator to populate history.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono">
              <thead className="bg-cyber-bg text-slate-400 border-b border-cyber-border">
                <tr>
                  <th className="py-2.5 px-4">Time</th>
                  <th className="py-2.5 px-4">Backend / Model</th>
                  <th className="py-2.5 px-4">Obfuscated Expression</th>
                  <th className="py-2.5 px-4">Status</th>
                  <th className="py-2.5 px-4">Proven Simplified Form</th>
                  <th className="py-2.5 px-4">Reduction</th>
                  <th className="py-2.5 px-4">Turns</th>
                  <th className="py-2.5 px-4">Duration</th>
                  <th className="py-2.5 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-cyber-border/60">
                {history.map((run) => {
                  const isVer = run.final_status === 'VERIFIED_EQUIVALENT';
                  const isFail = run.final_status === 'FAILED';
                  const isUnsafe = run.final_status === 'REJECTED_UNSAFE';

                  return (
                    <tr key={run.run_id} className="hover:bg-slate-900/40 transition-colors">
                      <td className="py-3 px-4 text-slate-500 whitespace-nowrap">
                        {new Date(run.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })}
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap">
                        <span className="px-1.5 py-0.5 rounded text-[10px] font-bold bg-slate-900 border border-slate-700 text-cyan-300">
                          {run.backend?.toUpperCase()}
                        </span>
                        {run.model_name && (
                          <span className="ml-1 text-[10px] text-slate-400">
                            {run.model_name}
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-slate-300 font-semibold max-w-[200px] truncate" title={run.expression}>
                        {run.expression}
                      </td>
                      <td className="py-3 px-4 whitespace-nowrap">
                        {isVer ? (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-emerald-950 border border-emerald-500/40 text-emerald-300">
                            PROVEN
                          </span>
                        ) : isFail ? (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-rose-950/60 border border-rose-500/40 text-rose-300">
                            FAILED
                          </span>
                        ) : isUnsafe ? (
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold bg-amber-950/60 border border-amber-500/40 text-amber-300">
                            UNSAFE
                          </span>
                        ) : (
                          <span className="px-2 py-0.5 rounded text-[10px] bg-slate-800 text-slate-400">
                            {run.final_status}
                          </span>
                        )}
                      </td>
                      <td className="py-3 px-4 text-emerald-300 font-bold max-w-[150px] truncate">
                        {run.final_expr || '-'}
                      </td>
                      <td className="py-3 px-4 text-slate-300">
                        {run.compression_pct > 0 ? `-${run.compression_pct}%` : '-'}
                      </td>
                      <td className="py-3 px-4 text-slate-400">{run.attempts}</td>
                      <td className="py-3 px-4 text-slate-400 whitespace-nowrap">{run.total_ms} ms</td>
                      <td className="py-3 px-4 text-right">
                        <button
                          type="button"
                          onClick={() => handleInspect(run.run_id)}
                          className="px-2.5 py-1 rounded bg-cyan-950/60 border border-cyan-500/40 text-cyan-300 hover:bg-cyan-900/60 hover:text-white transition-colors"
                        >
                          Inspect
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
