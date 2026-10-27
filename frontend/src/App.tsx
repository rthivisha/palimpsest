import { useState } from 'react';
import { Header } from './components/Header';
import { CommandCenter } from './components/CommandCenter';
import { LiveLoopGraph } from './components/LiveLoopGraph';
import { AttemptTimeline } from './components/AttemptTimeline';
import { ProofBanner } from './components/ProofBanner';
import { HistoryPage } from './pages/HistoryPage';
import { DatasetExplorer } from './pages/DatasetExplorer';
import { useRunStream } from './hooks/useRunStream';

export function App() {
  const [activeTab, setActiveTab] = useState<'main' | 'history' | 'dataset'>('main');
  const [explainMode, setExplainMode] = useState<boolean>(true);
  const [expression, setExpression] = useState<string>('(x ^ y) + 2 * (x & y)');
  const [maxIterations, setMaxIterations] = useState<number>(5);

  const {
    isRunning,
    activeNode,
    attempts,
    finalResult,
    error,
    is429Blocked,
    retryCountdown,
    startRun,
    cancelRun,
    loadPastRun,
    clearError,
  } = useRunStream();

  const handleStartRun = (expr: string, maxIters: number) => {
    startRun(expr, maxIters);
  };

  const handleReplayRun = (detail: any) => {
    setExpression(detail.expression);
    setMaxIterations(detail.max_iterations);
    loadPastRun(detail);
  };

  return (
    <div className="min-h-screen bg-cyber-bg text-slate-100 flex flex-col font-sans selection:bg-cyan-500 selection:text-black">
      {/* Forensic Cyber-Lab Header */}
      <Header
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        explainMode={explainMode}
        setExplainMode={setExplainMode}
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
                  is429Blocked={is429Blocked}
                  retryCountdown={retryCountdown}
                  error={error}
                  clearError={clearError}
                  onStartRun={handleStartRun}
                  onCancelRun={cancelRun}
                  explainMode={explainMode}
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
