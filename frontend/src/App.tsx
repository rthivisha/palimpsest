import { useState, useEffect } from 'react';
import { Header } from './components/Header';
import { CommandCenter } from './components/CommandCenter';
import { LiveLoopGraph } from './components/LiveLoopGraph';
import { AttemptTimeline } from './components/AttemptTimeline';
import { ProofBanner } from './components/ProofBanner';
import { HistoryPage } from './pages/HistoryPage';
import { DatasetExplorer } from './pages/DatasetExplorer';
import { useRunStream } from './hooks/useRunStream';
import { SystemHealth } from './types';

export function App() {
  const [activeTab, setActiveTab] = useState<'main' | 'history' | 'dataset'>('main');
  const [explainMode, setExplainMode] = useState<boolean>(true);
  const [expression, setExpression] = useState<string>('(x ^ y) + 2 * (x & y)');
  const [maxIterations, setMaxIterations] = useState<number>(5);
  const [health, setHealth] = useState<SystemHealth | null>(null);

  useEffect(() => {
    fetch('/api/health')
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) setHealth(data);
      })
      .catch(() => {});
  }, []);

  const {
    isRunning,
    activeNode,
    attempts,
    finalResult,
    error,
    is429Blocked,
    retryCountdown,
    backend,
    modelName,
    elapsedSeconds,
    isModelLoading,
    startRun,
    cancelRun,
    loadPastRun,
    clearError,
  } = useRunStream();

  const currentBackend = backend || health?.backend || 'fake';
  const currentModelName = modelName || health?.model_name || '';
  const fakeHint =
    currentBackend === 'fake'
      ? health?.fake_hint || 'Scripted demo model: only the Classic 2-Turn Demo is solvable'
      : null;

  const handleStartRun = async (expr: string, maxIters: number) => {
    try {
      const res = await fetch('/api/health');
      if (res.ok) {
        const freshHealth: SystemHealth = await res.json();
        setHealth(freshHealth);
        if (freshHealth.model_reachable === false) {
          return;
        }
      }
    } catch {
      // Best-effort health check
    }
    startRun(expr, maxIters);
  };

  const handleReplayRun = (detail: any) => {
    setExpression(detail.expression);
    setMaxIterations(detail.max_iterations);
    loadPastRun(detail);
  };

  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const runIdParam = params.get('run_id');
    const replayLatest = params.get('replay_latest');
    const tabParam = params.get('tab');

    if (tabParam === 'history' || tabParam === 'dataset' || tabParam === 'main') {
      setActiveTab(tabParam);
    }

    if (runIdParam) {
      fetch(`/api/runs/${runIdParam}`)
        .then((res) => (res.ok ? res.json() : null))
        .then((detail) => {
          if (detail) handleReplayRun(detail);
        })
        .catch(() => {});
    } else if (replayLatest) {
      fetch('/api/history?limit=1')
        .then((res) => (res.ok ? res.json() : null))
        .then((data) => {
          const run = Array.isArray(data) ? data[0] : (data?.runs ? data.runs[0] : null);
          if (run && run.run_id) {
            fetch(`/api/runs/${run.run_id}`)
              .then((res) => (res.ok ? res.json() : null))
              .then((detail) => {
                if (detail) handleReplayRun(detail);
              })
              .catch(() => {});
          }
        })
        .catch(() => {});
    }
  }, []);

  return (
    <div className="min-h-screen bg-cyber-bg text-slate-100 flex flex-col font-sans selection:bg-cyan-500 selection:text-black">
      {/* Forensic Cyber-Lab Header */}
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        explainMode={explainMode}
        setExplainMode={setExplainMode}
        backend={currentBackend}
        modelName={currentModelName}
      />

      {/* Main Container */}
      <main className="flex-1 max-w-7xl w-full mx-auto p-4 lg:p-8 space-y-6">
        {activeTab === 'main' && (
          <div className="space-y-6">
            {/* Terminal Proof & Compression Result Banner (if run complete) */}
            {finalResult && (
              <ProofBanner
                originalExpr={expression}
                finalResult={finalResult}
                explainMode={explainMode}
              />
            )}

            {/* Split Workspace */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
              {/* Left Column: Input Command Center & Timeline */}
              <div className="lg:col-span-7 space-y-6">
                <CommandCenter
                  expression={expression}
                  setExpression={setExpression}
                  maxIterations={maxIterations}
                  setMaxIterations={setMaxIterations}
                  isRunning={isRunning}
                  activeNode={activeNode}
                  isModelLoading={isModelLoading}
                  elapsedSeconds={elapsedSeconds}
                  is429Blocked={is429Blocked}
                  retryCountdown={retryCountdown}
                  error={error}
                  clearError={clearError}
                  onStartRun={handleStartRun}
                  onCancelRun={cancelRun}
                  explainMode={explainMode}
                  fakeHint={fakeHint}
                  isModelReachable={health?.model_reachable !== false}
                  modelUnreachableReason={health?.model_unreachable_reason}
                />

                <AttemptTimeline
                  attempts={attempts}
                  explainMode={explainMode}
                />
              </div>

              {/* Right Column: Live Interactive LangGraph State Machine */}
              <div className="lg:col-span-5 lg:sticky lg:top-20 space-y-4">
                <LiveLoopGraph
                  activeNode={activeNode}
                  isRunning={isRunning}
                  attempts={attempts}
                  finalResult={finalResult}
                  explainMode={explainMode}
                />
              </div>
            </div>
          </div>
        )}

        {activeTab === 'history' && (
          <HistoryPage
            onReplayRun={handleReplayRun}
            onNavigateToMain={() => setActiveTab('main')}
          />
        )}

        {activeTab === 'dataset' && (
          <DatasetExplorer
            onLoadExpression={(expr) => setExpression(expr)}
            onNavigateToMain={() => setActiveTab('main')}
          />
        )}
      </main>

      {/* Footer */}
      <footer className="border-t border-cyber-border py-4 px-6 text-center text-xs font-mono text-slate-500">
        PALIMPSEST Neurosymbolic De-obfuscation • SMT Equivalence Prover (QF_BV, 64-bit) • CEGIS Synthesis Loop
      </footer>
    </div>
  );
}

export default App;
