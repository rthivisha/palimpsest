import { useState, useRef, useCallback } from 'react';
import { Attempt, FinalPayload, RunDetail, RunStartedPayload } from '../types';
import { deriveReplayFinalResult } from '../utils/replay';
import { fetchWithInitialRetry } from '../utils/fetchWithRetry';

interface UseRunStreamReturn {
  isRunning: boolean;
  activeNode: string | null;
  runId: string | null;
  expression: string;
  obfNodes: number;
  maxIterations: number;
  attempts: Attempt[];
  finalResult: FinalPayload | null;
  error: string | null;
  is429Blocked: boolean;
  retryCountdown: number;
  backend: string | null;
  modelName: string | null;
  elapsedSeconds: number;
  isModelLoading: boolean;
  startRun: (expr: string, maxIters?: number) => Promise<void>;
  cancelRun: () => Promise<void>;
  resetRun: () => void;
  loadPastRun: (pastRun: RunDetail) => void;
  clearError: () => void;
}

export function useRunStream(): UseRunStreamReturn {
  const [isRunning, setIsRunning] = useState<boolean>(false);
  const [activeNode, setActiveNode] = useState<string | null>(null);
  const [runId, setRunId] = useState<string | null>(null);
  const [expression, setExpression] = useState<string>('');
  const [obfNodes, setObfNodes] = useState<number>(0);
  const [maxIterations, setMaxIterations] = useState<number>(5);
  const [attempts, setAttempts] = useState<Attempt[]>([]);
  const [finalResult, setFinalResult] = useState<FinalPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [backend, setBackend] = useState<string | null>(null);
  const [modelName, setModelName] = useState<string | null>(null);

  // HTTP 429 Concurrency Backoff State
  const [is429Blocked, setIs429Blocked] = useState<boolean>(false);
  const [retryCountdown, setRetryCountdown] = useState<number>(0);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);

  const abortControllerRef = useRef<AbortController | null>(null);
  const countdownTimerRef = useRef<number | null>(null);
  const elapsedTimerRef = useRef<number | null>(null);

  const clearError = useCallback(() => {
    setError(null);
  }, []);

  const resetRun = useCallback(() => {
    setIsRunning(false);
    setActiveNode(null);
    setRunId(null);
    setAttempts([]);
    setFinalResult(null);
    setError(null);
    setModelName(null);
  }, []);

  const loadPastRun = useCallback((pastRun: RunDetail) => {
    setIsRunning(false);
    setActiveNode(null);
    setRunId(pastRun.run_id);
    setExpression(pastRun.expression);
    setObfNodes(pastRun.obf_nodes ?? 0);
    setMaxIterations(pastRun.max_iterations);
    setBackend(pastRun.backend);
    if (pastRun.model_name) setModelName(pastRun.model_name);
    setAttempts(pastRun.attempts_history || []);
    setFinalResult(deriveReplayFinalResult(pastRun));
    setError(null);
  }, []);

  const cancelRun = useCallback(async () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
      abortControllerRef.current = null;
    }
    if (runId) {
      try {
        await fetch(`/api/runs/${runId}/cancel`, { method: 'POST' });
      } catch {
        // Best effort cancellation
      }
    }
    setIsRunning(false);
    setActiveNode(null);
    setError('Execution aborted by user.');
  }, [runId]);

  const startRun = useCallback(async (expr: string, maxIters: number = 5) => {
    if (!expr.trim() || is429Blocked) return;

    // Reset current run state
    setIsRunning(true);
    setActiveNode('parse_ast');
    setError(null);
    setFinalResult(null);
    setAttempts([]);
    setExpression(expr);
    setMaxIterations(maxIters);
    setElapsedSeconds(0);

    if (elapsedTimerRef.current) clearInterval(elapsedTimerRef.current);
    const startTimestamp = performance.now();
    elapsedTimerRef.current = window.setInterval(() => {
      setElapsedSeconds(Number(((performance.now() - startTimestamp) / 1000).toFixed(1)));
    }, 100);

    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    let response: Response;
    try {
      // Connect to API with at most 1 retry ONLY before any response arrives
      response = await fetchWithInitialRetry(
        '/api/run',
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
          },
          body: jsonBody({ expression: expr, max_iterations: maxIters }),
          signal: abortController.signal,
        },
        500
      );

      // 1. Handle HTTP 429: "previous run still finishing" with Retry-After header
      if (response.status === 429) {
        const retryHeader = response.headers.get('retry-after');
        const seconds = retryHeader ? Math.max(1, parseInt(retryHeader, 10)) : 5;

        setIs429Blocked(true);
        setRetryCountdown(seconds);
        setError(`Previous run still finishing. Please wait ${seconds}s before retrying.`);
        setIsRunning(false);
        setActiveNode(null);

        if (countdownTimerRef.current) {
          clearInterval(countdownTimerRef.current);
        }

        countdownTimerRef.current = window.setInterval(() => {
          setRetryCountdown((prev) => {
            if (prev <= 1) {
              if (countdownTimerRef.current) clearInterval(countdownTimerRef.current);
              setIs429Blocked(false);
              return 0;
            }
            return prev - 1;
          });
        }, 1000);

        return;
      }

      if (!response.ok) {
        let errorDetail = `Server responded with HTTP ${response.status}`;
        try {
          const errData = await response.json();
          if (errData.detail) errorDetail = errData.detail;
        } catch {
          // Keep generic detail
        }
        setError(errorDetail);
        setIsRunning(false);
        setActiveNode(null);
        return;
      }

      if (!response.body) {
        setError('No response stream received from server.');
        setIsRunning(false);
        setActiveNode(null);
        return;
      }

      // 2. Consume SSE stream reader
      const reader = response.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let buffer = '';
      let receivedFinalOrError = false;

      while (true) {
        const { value, done } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n\n');
        buffer = lines.pop() || '';

        for (const block of lines) {
          const trimmed = block.trim();
          if (!trimmed || trimmed.startsWith(':')) {
            // Heartbeat ping comment, ignore
            continue;
          }

          let eventType = '';
          let eventData: any = null;

          for (const line of trimmed.split('\n')) {
            if (line.startsWith('event:')) {
              eventType = line.slice(6).trim();
            } else if (line.startsWith('data:')) {
              try {
                eventData = JSON.parse(line.slice(5).trim());
              } catch {
                eventData = null;
              }
            }
          }

          if (!eventType || !eventData) continue;

          // Process parsed SSE event
          switch (eventType) {
            case 'run_started': {
              const payload = eventData as RunStartedPayload;
              setRunId(payload.run_id);
              setObfNodes(payload.obf_nodes);
              setBackend(payload.backend);
              if (payload.model_name) setModelName(payload.model_name);
              break;
            }

            case 'node_started': {
              setActiveNode(eventData.node);
              break;
            }

            case 'node_finished': {
              // Active node will update with next node_started or final
              break;
            }

            case 'proposal': {
              const iter = eventData.iteration;
              setAttempts((prev) => {
                const existing = prev.find((a) => a.iteration === iter);
                if (existing) {
                  return prev.map((a) =>
                    a.iteration === iter
                      ? { ...a, candidate: eventData.candidate, think: eventData.think, raw_output: eventData.raw_output }
                      : a
                  );
                } else {
                  return [
                    ...prev,
                    {
                      iteration: iter,
                      candidate: eventData.candidate,
                      think: eventData.think,
                      raw_output: eventData.raw_output,
                    },
                  ];
                }
              });
              break;
            }

            case 'verification': {
              const iter = eventData.iteration;
              setAttempts((prev) => {
                const existing = prev.find((a) => a.iteration === iter);
                if (existing) {
                  return prev.map((a) =>
                    a.iteration === iter
                      ? {
                          ...a,
                          status: eventData.status,
                          latency_ms: eventData.latency_ms,
                          witness: eventData.witness,
                          expected: eventData.expected,
                          actual: eventData.actual,
                          diff_bits: eventData.diff_bits,
                        }
                      : a
                  );
                } else {
                  return [
                    ...prev,
                    {
                      iteration: iter,
                      candidate: eventData.candidate,
                      status: eventData.status,
                      latency_ms: eventData.latency_ms,
                      witness: eventData.witness,
                      expected: eventData.expected,
                      actual: eventData.actual,
                      diff_bits: eventData.diff_bits,
                    },
                  ];
                }
              });
              break;
            }

            case 'retry': {
              const iter = eventData.iteration;
              setAttempts((prev) =>
                prev.map((a) =>
                  a.iteration === iter
                    ? { ...a, feedback_message: eventData.feedback_message }
                    : a
                )
              );
              break;
            }

            case 'final': {
              receivedFinalOrError = true;
              setFinalResult(eventData as FinalPayload);
              setIsRunning(false);
              setActiveNode(null);
              break;
            }

            case 'error': {
              receivedFinalOrError = true;
              setError(eventData.error || 'Synthesis run terminated with an internal error.');
              setIsRunning(false);
              setActiveNode(null);
              break;
            }
          }
        }
      }

      if (!receivedFinalOrError) {
        setError('Backend server disconnected before synthesis run completed.');
      }
    } catch (err: any) {
      if (err.name === 'AbortError') {
        // Handled cleanly
      } else {
        const isNetworkErr =
          err instanceof TypeError ||
          err.message?.includes('Failed to fetch') ||
          err.message?.includes('NetworkError') ||
          err.message?.includes('ECONNREFUSED');
        if (isNetworkErr) {
          setError(
            'Backend server offline: Unable to connect to PALIMPSEST API server at http://127.0.0.1:8000. Please verify the backend service is running.'
          );
        } else {
          setError(err.message || 'Stream connection failed.');
        }
      }
    } finally {
      if (elapsedTimerRef.current) {
        clearInterval(elapsedTimerRef.current);
        elapsedTimerRef.current = null;
      }
      setIsRunning(false);
      setActiveNode(null);
      abortControllerRef.current = null;
    }
  }, [is429Blocked]);

  return {
    isRunning,
    activeNode,
    runId,
    expression,
    obfNodes,
    maxIterations,
    attempts,
    finalResult,
    error,
    is429Blocked,
    retryCountdown,
    backend,
    modelName,
    elapsedSeconds,
    isModelLoading: isRunning && (activeNode === 'propose' || (activeNode === 'parse_ast' && attempts.length === 0)),
    startRun,
    cancelRun,
    resetRun,
    loadPastRun,
    clearError,
  };
}

function jsonBody(obj: any): string {
  return JSON.stringify(obj);
}

