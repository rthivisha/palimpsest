import React, { useMemo } from 'react';
import {
  ReactFlow,
  Background,
  Node,
  Edge,
  MarkerType,
  Position,
  Handle,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import { Shield, Sparkles, Scale, GitFork, CheckCircle2, XCircle } from 'lucide-react';
import { Attempt, FinalPayload } from '../types';

interface LiveLoopGraphProps {
  activeNode: string | null;
  isRunning: boolean;
  attempts: Attempt[];
  finalResult: FinalPayload | null;
  explainMode: boolean;
}

// Custom Node Component for Cyber-Lab Aesthetic
const GraphStepNode: React.FC<{
  data: {
    label: string;
    sublabel: string;
    icon: any;
    isActive: boolean;
    isSuccess?: boolean;
    isFailed?: boolean;
    stats?: string;
  };
}> = ({ data }) => {
  const Icon = data.icon;

  let borderColor = 'border-slate-800';
  let bgColor = 'bg-cyber-surface';
  let textColor = 'text-slate-300';
  let glowStyle = '';

  if (data.isActive) {
    borderColor = 'border-cyan-400';
    bgColor = 'bg-cyan-950/60';
    textColor = 'text-cyan-200';
    glowStyle = 'shadow-[0_0_15px_rgba(6,182,212,0.5)]';
  } else if (data.isSuccess) {
    borderColor = 'border-emerald-500';
    bgColor = 'bg-emerald-950/50';
    textColor = 'text-emerald-200';
    glowStyle = 'shadow-[0_0_15px_rgba(16,185,129,0.4)]';
  } else if (data.isFailed) {
    borderColor = 'border-rose-500';
    bgColor = 'bg-rose-950/50';
    textColor = 'text-rose-200';
    glowStyle = 'shadow-[0_0_15px_rgba(239,68,68,0.4)]';
  }

  return (
    <div
      className={`px-3 py-2 rounded-lg border ${borderColor} ${bgColor} ${glowStyle} transition-all duration-300 w-44 text-left relative`}
    >
      <Handle type="target" position={Position.Top} className="!bg-slate-600 !w-2 !h-2" />
      <div className="flex items-center gap-2 mb-1">
        <div
          className={`p-1.5 rounded-md ${
            data.isActive
              ? 'bg-cyan-500/20 text-cyan-400'
              : data.isSuccess
              ? 'bg-emerald-500/20 text-emerald-400'
              : data.isFailed
              ? 'bg-rose-500/20 text-rose-400'
              : 'bg-slate-800 text-slate-400'
          }`}
        >
          <Icon className="w-4 h-4" />
        </div>
        <div className="overflow-hidden">
          <div className={`text-xs font-bold font-mono ${textColor} truncate`}>{data.label}</div>
          <div className="text-[10px] text-slate-500 font-mono truncate">{data.sublabel}</div>
        </div>
      </div>
      {data.stats && (
        <div className="mt-1 text-[10px] text-slate-400 font-mono border-t border-slate-800/80 pt-1 break-words whitespace-normal leading-tight">
          {data.stats}
        </div>
      )}
      <Handle type="source" position={Position.Bottom} className="!bg-slate-600 !w-2 !h-2" />
    </div>
  );
};

const nodeTypes = {
  customStep: GraphStepNode,
};

export const LiveLoopGraph: React.FC<LiveLoopGraphProps> = ({
  activeNode,
  isRunning,
  attempts,
  finalResult,
}) => {
  // Check prefers-reduced-motion
  const prefersReducedMotion = useMemo(() => {
    return typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  }, []);

  const latestAttempt = attempts[attempts.length - 1];

  // Derive active nodes and state highlights
  const isParseActive = activeNode === 'parse_ast';
  const isProposeActive = activeNode === 'propose';
  const isVerifyActive = activeNode === 'verify';
  const isRouterActive = isRunning && activeNode === 'router';
  const isSuccessFinal =
    finalResult?.status === 'verified' ||
    finalResult?.status === 'verified-not-simpler' ||
    finalResult?.status === 'VERIFIED_EQUIVALENT';
  const isFailFinal =
    finalResult?.status === 'FAILED' ||
    finalResult?.status === 'REJECTED_UNSAFE' ||
    finalResult?.status === 'CANCELLED';

  const nodes: Node[] = useMemo(() => {
    return [
      {
        id: 'parse_ast',
        type: 'customStep',
        position: { x: 180, y: 15 },
        data: {
          label: 'parse_ast',
          sublabel: 'AST Security Gate',
          icon: Shield,
          isActive: isParseActive,
          stats: finalResult?.obf_nodes ? `${finalResult.obf_nodes} AST nodes` : undefined,
        },
      },
      {
        id: 'propose',
        type: 'customStep',
        position: { x: 180, y: 105 },
        data: {
          label: 'propose',
          sublabel: 'Candidate Proposer',
          icon: Sparkles,
          isActive: isProposeActive,
          stats: latestAttempt?.candidate ? `Cand: ${latestAttempt.candidate}` : undefined,
        },
      },
      {
        id: 'verify',
        type: 'customStep',
        position: { x: 180, y: 195 },
        data: {
          label: 'verify',
          sublabel: 'Z3 SMT Solver (QF_BV)',
          icon: Scale,
          isActive: isVerifyActive,
          stats: latestAttempt?.status ? `${latestAttempt.status} (${latestAttempt.latency_ms}ms)` : undefined,
        },
      },
      {
        id: 'router',
        type: 'customStep',
        position: { x: 180, y: 285 },
        data: {
          label: 'router',
          sublabel: 'CEGIS Edge Router',
          icon: GitFork,
          isActive: isRouterActive,
          stats: attempts.length > 0 ? `Iteration ${attempts.length}` : undefined,
        },
      },
      {
        id: 'finalize_success',
        type: 'customStep',
        position: { x: 50, y: 380 },
        data: {
          label: 'finalize_success',
          sublabel: 'QF_BV Proven',
          icon: CheckCircle2,
          isActive: activeNode === 'finalize_success',
          isSuccess: isSuccessFinal,
          stats: isSuccessFinal && finalResult ? `${finalResult.compression_pct}% reduced` : undefined,
        },
      },
      {
        id: 'finalize_fail',
        type: 'customStep',
        position: { x: 310, y: 380 },
        data: {
          label: 'finalize_fail',
          sublabel: 'No Proof Accepted',
          icon: XCircle,
          isActive: activeNode === 'finalize_fail',
          isFailed: isFailFinal,
          stats: isFailFinal ? (finalResult?.reason || 'Unverified') : undefined,
        },
      },
    ];
  }, [
    isParseActive,
    isProposeActive,
    isVerifyActive,
    isRouterActive,
    isSuccessFinal,
    isFailFinal,
    activeNode,
    latestAttempt,
    attempts.length,
    finalResult,
  ]);

  const edges: Edge[] = useMemo(() => {
    const shouldAnimate = !prefersReducedMotion && isRunning;

    return [
      {
        id: 'e-parse-propose',
        source: 'parse_ast',
        target: 'propose',
        animated: shouldAnimate && isParseActive,
        style: { stroke: isParseActive ? '#06b6d4' : '#334155', strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: isParseActive ? '#06b6d4' : '#334155' },
      },
      {
        id: 'e-propose-verify',
        source: 'propose',
        target: 'verify',
        animated: shouldAnimate && isProposeActive,
        style: { stroke: isProposeActive ? '#06b6d4' : '#334155', strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: isProposeActive ? '#06b6d4' : '#334155' },
      },
      {
        id: 'e-verify-router',
        source: 'verify',
        target: 'router',
        animated: shouldAnimate && isVerifyActive,
        style: { stroke: isVerifyActive ? '#06b6d4' : '#334155', strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: isVerifyActive ? '#06b6d4' : '#334155' },
      },
      {
        id: 'e-router-success',
        source: 'router',
        target: 'finalize_success',
        animated: shouldAnimate && isSuccessFinal,
        label: 'UNSAT',
        labelStyle: { fill: '#10b981', fontSize: 10, fontFamily: 'monospace' },
        style: { stroke: isSuccessFinal ? '#10b981' : '#334155', strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: isSuccessFinal ? '#10b981' : '#334155' },
      },
      {
        id: 'e-router-fail',
        source: 'router',
        target: 'finalize_fail',
        animated: shouldAnimate && isFailFinal,
        label: 'Max Iter / Unsafe',
        labelStyle: { fill: '#ef4444', fontSize: 9, fontFamily: 'monospace' },
        style: { stroke: isFailFinal ? '#ef4444' : '#334155', strokeWidth: 2 },
        markerEnd: { type: MarkerType.ArrowClosed, color: isFailFinal ? '#ef4444' : '#334155' },
      },
      {
        id: 'e-router-retry',
        source: 'router',
        target: 'propose',
        type: 'smoothstep',
        animated: shouldAnimate && (activeNode === 'retry' || (isProposeActive && attempts.length > 1)),
        label: 'SAT (Counterexample Feedback)',
        labelStyle: { fill: '#f59e0b', fontSize: 9, fontFamily: 'monospace' },
        style: {
          stroke: activeNode === 'retry' || (isProposeActive && attempts.length > 1) ? '#f59e0b' : '#334155',
          strokeWidth: 2,
          strokeDasharray: '4,4',
        },
        markerEnd: { type: MarkerType.ArrowClosed, color: '#f59e0b' },
      },
    ];
  }, [prefersReducedMotion, isRunning, isParseActive, isProposeActive, isVerifyActive, isSuccessFinal, isFailFinal, activeNode, attempts.length]);

  return (
    <div className="bg-cyber-surface border border-cyber-border rounded-xl p-4 shadow-lg h-[500px] flex flex-col">
      <div className="flex items-center justify-between mb-2 px-1">
        <div className="text-xs font-semibold text-slate-300 font-mono flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-cyan-400" />
          <span>LANGGRAPH CEGIS STATE MACHINE (LIVE)</span>
        </div>
        <div className="text-[11px] text-slate-500 font-mono">
          {isRunning ? (
            <span className="text-cyan-400 animate-pulse">Running: {activeNode || 'executing'}</span>
          ) : (
            <span>Ready</span>
          )}
        </div>
      </div>

      <div className="flex-1 w-full rounded-lg overflow-hidden border border-cyber-border/60 bg-[#070b12] relative">
        <ReactFlow
          key={`${attempts.length}-${finalResult?.status || 'idle'}`}
          nodes={nodes}
          edges={edges}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.12 }}
          minZoom={0.2}
          maxZoom={1.5}
          nodesDraggable={false}
          nodesConnectable={false}
          elementsSelectable={false}
          panOnDrag={true}
          zoomOnScroll={false}
        >
          <Background color="#1f293d" gap={16} size={1} />
        </ReactFlow>
      </div>
    </div>
  );
};

