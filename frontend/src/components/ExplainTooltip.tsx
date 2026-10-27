import React, { useState } from 'react';
import { Info } from 'lucide-react';

interface ExplainTooltipProps {
  topic:
    | 'mba'
    | 'cegis'
    | 'z3'
    | 'smt'
    | 'bitvec'
    | 'sat_unsat'
    | 'counterexample'
    | 'opaque'
    | 'compression';
  explainMode: boolean;
  inline?: boolean;
}

const EXPLANATIONS: Record<string, { title: string; content: string }> = {
  mba: {
    title: 'Mixed Boolean-Arithmetic (MBA)',
    content:
      'MBA combines bitwise logic (&, |, ^, ~) with normal arithmetic (+, -, *). Obfuscators use MBA identities to hide simple operations inside convoluted, mathematically equivalent formulas that confuse disassemblers and decompilers.',
  },
  cegis: {
    title: 'CEGIS (Counterexample-Guided Synthesis)',
    content:
      'CEGIS is a neurosymbolic feedback loop: A fast language model PROPOSES a simplification, then an exact SMT solver JUDGES it. If incorrect, the solver extracts a concrete failing counterexample and feeds it back to the model to try again.',
  },
  z3: {
    title: 'Z3 SMT Solver (QF_BV)',
    content:
      'Microsoft Z3 is a formal verification solver, NOT an AI model. In QF_BV (Quantifier-Free Bit-Vectors), Z3 algebraically checks whether there is ANY input where original != candidate across all 2^64 values. It produces mathematical proofs, never probabilistic guesses.',
  },
  smt: {
    title: 'SMT Solving (Satisfiability Modulo Theories)',
    content:
      'SMT solvers generalize boolean SAT solving by supporting rich background theories like fixed-width bit-vectors. Instead of sampling random test cases, SMT solvers systematically explore mathematical constraints to definitively prove equivalence.',
  },
  bitvec: {
    title: '64-bit Unsigned Bit-Vectors',
    content:
      'Modern CPU registers operate on fixed-width words. 64-bit arithmetic wraps modulo 2^64 on overflow, and bitwise operations apply to each of the 64 individual bits. Expressions must evaluate identically under exact hardware wrapping semantics.',
  },
  sat_unsat: {
    title: 'UNSAT (Equivalent) vs SAT (Counterexample)',
    content:
      '• UNSAT: The miter condition (original != candidate) has NO solutions. Equivalence is mathematically PROVEN.\n• SAT: A counterexample was found. The solver gives concrete variable values where the candidate produces the wrong output.',
  },
  counterexample: {
    title: 'Counterexample Witness',
    content:
      'A concrete set of variable values (e.g. x=1, y=1) discovered by Z3 where original and candidate evaluate to different outputs. This concrete failure is fed back into the model prompt so it learns from its exact mistake.',
  },
  opaque: {
    title: 'Opaque Predicates',
    content:
      'Dead code expressions that look complex but always evaluate to a constant (e.g., (x & ~x) * y always equals 0). Obfuscators inject them to bloat the code with dead terms.',
  },
  compression: {
    title: 'AST Node Compression',
    content:
      'Measures how much the syntax tree was simplified. We count syntactic operations (binary operators, unary operators, variables, constants) before and after de-obfuscation.',
  },
};

export const ExplainTooltip: React.FC<ExplainTooltipProps> = ({ topic, explainMode, inline = false }) => {
  const [open, setOpen] = useState(false);
  const info = EXPLANATIONS[topic];
  if (!explainMode || !info) return null;

  return (
    <span className={`relative ${inline ? 'inline-flex align-middle ml-1.5' : 'block'}`}>
      <button
        type="button"
        onClick={() => setOpen(!open)}
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        className="text-amber-400 hover:text-amber-300 p-0.5 rounded transition-colors focus:outline-none"
        aria-label={`Explain ${info.title}`}
      >
        <Info className="w-3.5 h-3.5" />
      </button>

      {open && (
        <div className="absolute z-50 left-1/2 -translate-x-1/2 bottom-full mb-2 w-72 p-3 bg-slate-900 border border-amber-500/40 rounded-lg shadow-xl text-xs text-slate-200 pointer-events-none transition-all">
          <div className="font-semibold text-amber-300 mb-1 flex items-center gap-1.5">
            <span>Explain Mode:</span>
            <span>{info.title}</span>
          </div>
          <p className="whitespace-pre-line leading-relaxed text-slate-300">{info.content}</p>
          <div className="absolute top-full left-1/2 -translate-x-1/2 border-4 border-transparent border-t-slate-900" />
        </div>
      )}
    </span>
  );
};

