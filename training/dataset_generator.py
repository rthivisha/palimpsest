# High-performance multi-core neurosymbolic dataset generator with formal Z3 gatekeeper.
import argparse
import concurrent.futures
import hashlib
import json
import multiprocessing
import os
import random
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple

# Raise recursion limit for deep AST operations.
sys.setrecursionlimit(10000)

# Import local modules with directory fallback.
try:
    from ast_slicer import count_nodes
    from mba_mutator import (
        MBAMutator,
        Node,
        Const,
        parse_to_ir,
        get_masked_const,
        SEEDS,
    )
    from z3_verifier import verify_equivalence
except ImportError:
    from training.ast_slicer import count_nodes
    from training.mba_mutator import (
        MBAMutator,
        Node,
        Const,
        parse_to_ir,
        get_masked_const,
        SEEDS,
    )
    from training.z3_verifier import verify_equivalence

# Canonical constant-heavy seed expressions for algebraic folding traces.
CONSTANT_SEEDS = [
    "rax + 0x1000",
    "rbx - 0x20",
    "rcx ^ 0x5555",
    "rdx & 0x7fff",
    "rsi | 0x1234",
    "(rax + 0x100) ^ 0x20",
    "(rbx & 0x3ff) + 0x80",
    "(rcx << 1) + 0x50",
    "r8 + 0xdead",
    "r9 - 0xbeef",
    "(rsi ^ 0x100) + 0x20",
    "(rdi & 0xffff) ^ 0x55",
]

# Canonical register and variable pool for procedural expressions.
CANONICAL_VARS = [
    "x", "y", "z", "rax", "rbx", "rcx", "rdx", "rsi", "rdi",
    "r8", "r9", "r10", "r11", "r12", "r13", "r14", "r15"
]

# Canonical binary operators for procedural expressions.
CANONICAL_OPS = ["+", "-", "^", "&", "|"]

# Procedural canonical irreducible expression generator for idempotency traces.
def generate_canonical_expression() -> str:
    if random.random() < 0.3:
        return random.choice(SEEDS)
    mode = random.randint(1, 4)
    r1 = random.choice(CANONICAL_VARS)
    r2 = random.choice([r for r in CANONICAL_VARS if r != r1])
    op = random.choice(CANONICAL_OPS)
    if mode == 1:
        return f"{r1} {op} {r2}"
    elif mode == 2:
        c = random.choice([1, 2, 4, 8, 16, 32, 64, 0x10, 0x20, 0x55, 0xaa, 0xff, 0x100, 0x1000])
        c_str = hex(c) if c > 255 else str(c)
        return f"{r1} {op} {c_str}"
    elif mode == 3:
        r3 = random.choice([r for r in CANONICAL_VARS if r not in (r1, r2)])
        op2 = random.choice(CANONICAL_OPS)
        return f"({r1} {op} {r2}) {op2} {r3}"
    else:
        return f"~{r1} {op} {r2}"

# Supported binary operator swaps for realistic near-miss mutation.
OP_SWAPS = [
    ("+", "^"),
    ("-", "+"),
    ("^", "|"),
    ("&", "^"),
    ("|", "&"),
    ("<<", ">>"),
    (">>", "<<"),
    ("*", "+"),
]

# Generate realistic near-miss expression for CEGIS repair simulation.
def generate_near_miss(seed: str) -> str:
    candidates = []
    # Strip bitwise inversion if present.
    if "~" in seed:
        candidates.append(seed.replace("~", ""))
    # Apply operator substitutions.
    for op, rep in OP_SWAPS:
        if op in seed:
            idx = seed.find(op)
            candidates.append(seed[:idx] + rep + seed[idx + len(op):])
    # Off-by-one perturbations.
    candidates.append(f"({seed}) ^ 1")
    candidates.append(f"({seed}) + 1")
    candidates.append(f"({seed}) - 1")
    random.shuffle(candidates)
    return candidates[0]

# Build reversed step-by-step reasoning Chain-of-Thought string.
def build_reversible_cot(
    mutation_ledger: List[str],
    tier: int,
    obf_nodes: int,
    seed_nodes: int,
    eta_ast: float,
) -> str:
    # Reverse ledger to transition from obfuscated structure back to canonical seed.
    reversed_ledger = mutation_ledger[::-1]
    steps = []
    for idx, rule in enumerate(reversed_ledger, 1):
        if "Opaque Zero" in rule:
            cleaned = rule.replace("Opaque Zero: ", "").replace(" == 0", " -> 0")
            steps.append(f"Step {idx}: Neutralize Opaque Zero {cleaned}.")
        elif "Opaque One" in rule:
            cleaned = rule.replace("Opaque One: ", "").replace(" == 1", " -> 1")
            steps.append(f"Step {idx}: Collapse Opaque One {cleaned}.")
        elif "Constant Unfolded" in rule:
            steps.append(f"Step {idx}: Fold unfolded constant decomposition back into immediate value.")
        elif "Linear MBA" in rule:
            rule_clean = rule.replace("Linear MBA: ", "")
            if " -> " in rule_clean:
                lhs, rhs = rule_clean.split(" -> ", 1)
                steps.append(f"Step {idx}: Fold Linear MBA identity {rhs} back to canonical form {lhs}.")
            else:
                steps.append(f"Step {idx}: Fold Linear MBA identity back to canonical form.")
        else:
            steps.append(f"Step {idx}: Simplify algebraic expression.")

    steps_str = " ".join(steps)
    return (
        f"<think>\n"
        f"AST Nodes: {obf_nodes} (Tier {tier}). {steps_str} "
        f"Verified target AST Nodes: {seed_nodes}.\n"
        f"</think>"
    )

# Parallel worker generating a single verified row according to specified pillar and tier.
def generate_row_worker(args_tuple: Tuple[int, str, int]) -> Optional[Dict[str, Any]]:
    task_id, pillar, tier = args_tuple
    random.seed(os.getpid() + task_id * 1009 + random.randint(1, 10000000))
    mutator = MBAMutator()

    # Attempt generation with bounded retries.
    for _ in range(12):
        if pillar == "SFT":
            target_seed = random.choice(SEEDS)
            target_nodes = count_nodes(target_seed)
            mut_res = mutator.mutate(seed=target_seed, tier=tier)
            expr_obf = mut_res["obfuscated_expr"]
            ledger = mut_res["mutation_ledger"]
            obf_nodes = count_nodes(expr_obf)

            if obf_nodes <= target_nodes:
                continue

            verif = verify_equivalence(target_seed, expr_obf)
            if verif.get("status") != "QF_BV_UNSAT_64BIT_VERIFIED":
                continue

            z3_lat = verif.get("latency_ms", 0.0)
            eta_ast = round(1.0 - (target_nodes / obf_nodes), 4)
            cot_block = build_reversible_cot(ledger, tier, obf_nodes, target_nodes, eta_ast)

            conversations = [
                {
                    "from": "user",
                    "value": f"De-obfuscate this 64-bit MBA expression:\n{expr_obf}",
                },
                {
                    "from": "assistant",
                    "value": f"{cot_block}\n{target_seed}",
                },
            ]

            return {
                "row": {
                    "conversations": conversations,
                    "type": "SFT",
                    "eta_ast": eta_ast,
                    "z3_latency_ms": z3_lat,
                },
                "expr_obf": expr_obf,
                "pillar": "SFT",
                "tier": tier,
                "obf_nodes": obf_nodes,
                "eta_ast": eta_ast,
                "z3_latency_ms": z3_lat,
            }

        elif pillar == "CEGIS":
            target_seed = random.choice(SEEDS)
            target_nodes = count_nodes(target_seed)
            mut_res = mutator.mutate(seed=target_seed, tier=tier)
            expr_obf = mut_res["obfuscated_expr"]
            obf_nodes = count_nodes(expr_obf)

            if obf_nodes <= target_nodes:
                continue

            verif = verify_equivalence(target_seed, expr_obf)
            if verif.get("status") != "QF_BV_UNSAT_64BIT_VERIFIED":
                continue

            # Generate near-miss and obtain verified SAT counterexample witness.
            near_miss = None
            witness = None
            expected = 0
            actual = 0
            for _ in range(8):
                cand_miss = generate_near_miss(target_seed)
                cegis_verif = verify_equivalence(target_seed, cand_miss)
                if cegis_verif.get("status") == "SAT":
                    near_miss = cand_miss
                    witness = cegis_verif.get("witness", {})
                    expected = cegis_verif.get("expected", 0)
                    actual = cegis_verif.get("actual", 0)
                    break

            if near_miss is None or witness is None:
                continue

            z3_lat = verif.get("latency_ms", 0.0)
            eta_ast = round(1.0 - (target_nodes / obf_nodes), 4)

            # Build diagnosis think block plugging in witness values.
            witness_str = ", ".join(f"{k}={v}" for k, v in witness.items())
            turn3_think = (
                f"<think>\n"
                f"Counterexample witness assignment ({witness_str}) evaluated candidate '{near_miss}' "
                f"to {actual}, differing from expected ground truth {expected}. "
                f"Plugging assignment into candidate isolates the bitwise discrepancy in the evaluated operator. "
                f"Restoring formal algebraic identity yields verified canonical expression {target_seed}.\n"
                f"</think>"
            )

            conversations = [
                {
                    "from": "user",
                    "value": f"De-obfuscate this 64-bit MBA expression:\n{expr_obf}",
                },
                {
                    "from": "assistant",
                    "value": f"<think>\nAST Nodes: {obf_nodes}. Initial structural reduction and operator estimation...\n</think>\n{near_miss}",
                },
                {
                    "from": "tool",
                    "value": f"Z3_VERIFICATION_FAILED: SAT\nCounterexample Witness: {witness}\nExpected: {expected}, Actual: {actual}",
                },
                {
                    "from": "assistant",
                    "value": f"{turn3_think}\n{target_seed}",
                },
            ]

            return {
                "row": {
                    "conversations": conversations,
                    "type": "CEGIS",
                    "eta_ast": eta_ast,
                    "z3_latency_ms": z3_lat,
                },
                "expr_obf": expr_obf,
                "pillar": "CEGIS",
                "tier": tier,
                "obf_nodes": obf_nodes,
                "eta_ast": eta_ast,
                "z3_latency_ms": z3_lat,
            }

        elif pillar == "IDEMPOTENT":
            canonical_seed = generate_canonical_expression()
            nodes = count_nodes(canonical_seed)
            verif = verify_equivalence(canonical_seed, canonical_seed)
            z3_lat = verif.get("latency_ms", 0.0)

            think_block = (
                f"<think>\n"
                f"AST Nodes: {nodes}. Scanning expression for opaque predicates, redundant BitVec expansions, "
                f"or reducible MBA identities. No reducible linear MBA identities or opaque zero/one terms detected. "
                f"Expression is already in irreducible canonical form.\n"
                f"</think>"
            )

            conversations = [
                {
                    "from": "user",
                    "value": f"De-obfuscate this 64-bit MBA expression:\n{canonical_seed}",
                },
                {
                    "from": "assistant",
                    "value": f"{think_block}\n{canonical_seed}",
                },
            ]

            return {
                "row": {
                    "conversations": conversations,
                    "type": "IDEMPOTENT",
                    "eta_ast": 0.0,
                    "z3_latency_ms": z3_lat,
                },
                "expr_obf": canonical_seed,
                "pillar": "IDEMPOTENT",
                "tier": 1,
                "obf_nodes": nodes,
                "eta_ast": 0.0,
                "z3_latency_ms": z3_lat,
            }

        elif pillar == "CONSTANT_FOLDING":
            const_seed = random.choice(CONSTANT_SEEDS)
            target_nodes = count_nodes(const_seed)
            seed_ir = parse_to_ir(const_seed)
            unfolded_ir = mutator.unfold_constants(seed_ir)
            obf_ir = mutator.inject_opaque_zeros(unfolded_ir)
            expr_obf = obf_ir.to_string()
            obf_nodes = count_nodes(expr_obf)

            if obf_nodes <= target_nodes:
                continue

            verif = verify_equivalence(const_seed, expr_obf)
            if verif.get("status") != "QF_BV_UNSAT_64BIT_VERIFIED":
                continue

            z3_lat = verif.get("latency_ms", 0.0)
            eta_ast = round(1.0 - (target_nodes / obf_nodes), 4)

            think_block = (
                f"<think>\n"
                f"AST Nodes: {obf_nodes}. Unfolding constant expressions: collapsing decomposed BitVec operations "
                f"back into literal constants. Constant terms fold into canonical immediate. "
                f"Result simplifies to canonical register-immediate expression {const_seed}.\n"
                f"</think>"
            )

            conversations = [
                {
                    "from": "user",
                    "value": f"De-obfuscate this 64-bit MBA expression:\n{expr_obf}",
                },
                {
                    "from": "assistant",
                    "value": f"{think_block}\n{const_seed}",
                },
            ]

            return {
                "row": {
                    "conversations": conversations,
                    "type": "CONSTANT_FOLDING",
                    "eta_ast": eta_ast,
                    "z3_latency_ms": z3_lat,
                },
                "expr_obf": expr_obf,
                "pillar": "CONSTANT_FOLDING",
                "tier": 2,
                "obf_nodes": obf_nodes,
                "eta_ast": eta_ast,
                "z3_latency_ms": z3_lat,
            }

    return None

# Main pipeline orchestrator executing streaming bounded multiprocessing.
def main() -> None:
    parser = argparse.ArgumentParser(description="V2 Formal Neurosymbolic Dataset Engine for PALIMPSEST")
    parser.add_argument("--rows", type=int, default=5000, help="Number of verified rows to generate")
    parser.add_argument("--output", type=str, default="backend/data/samples.jsonl", help="Output JSONL path")
    args = parser.parse_args()

    num_cpus = multiprocessing.cpu_count()
    print(f"Initializing V2 Dataset Generator: Target {args.rows} rows across {num_cpus} workers.")

    # Calculate exact pillar quota distribution.
    count_sft = int(round(args.rows * 0.55))
    count_cegis = int(round(args.rows * 0.30))
    count_idempotent = int(round(args.rows * 0.10))
    count_constant = args.rows - (count_sft + count_cegis + count_idempotent)

    # Build sequence of required task assignments.
    task_queue: List[Tuple[str, int]] = []
    # Stratify SFT evenly across Tier 1, 2, and 3.
    for i in range(count_sft):
        task_queue.append(("SFT", (i % 3) + 1))
    # Stratify CEGIS evenly across Tier 1, 2, and 3.
    for i in range(count_cegis):
        task_queue.append(("CEGIS", (i % 3) + 1))
    # Canonical pass-through traces.
    for _ in range(count_idempotent):
        task_queue.append(("IDEMPOTENT", 1))
    # Constant-heavy folding traces.
    for _ in range(count_constant):
        task_queue.append(("CONSTANT_FOLDING", 2))

    random.shuffle(task_queue)

    # Ensure parent output directory exists.
    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    seen_hashes: Set[str] = set()
    total_verified = 0
    rejected_count = 0
    pillar_counts: Dict[str, int] = {"SFT": 0, "CEGIS": 0, "IDEMPOTENT": 0, "CONSTANT_FOLDING": 0}
    tier_counts: Dict[int, int] = {1: 0, 2: 0, 3: 0}
    total_nodes = 0
    total_eta = 0.0
    total_latency = 0.0

    task_id_counter = 0
    max_in_flight = min(200, num_cpus * 4)
    next_progress_pct = 5.0
    start_time = time.time()

    # Open streaming JSONL writer with immediate line-flush.
    with open(args.output, "w", encoding="utf-8") as out_f:
        with concurrent.futures.ProcessPoolExecutor(max_workers=num_cpus) as executor:
            # Map future to (pillar, tier).
            active_futures: Dict[concurrent.futures.Future, Tuple[str, int]] = {}

            # Seed initial batch of in-flight tasks.
            while len(active_futures) < max_in_flight and task_queue:
                p, t = task_queue.pop()
                task_id_counter += 1
                fut = executor.submit(generate_row_worker, (task_id_counter, p, t))
                active_futures[fut] = (p, t)

            # Consume results as completed and replenish executor queue.
            while active_futures and total_verified < args.rows:
                done, _ = concurrent.futures.wait(
                    active_futures.keys(),
                    return_when=concurrent.futures.FIRST_COMPLETED,
                )

                for fut in done:
                    assigned_p, assigned_t = active_futures.pop(fut)
                    res = fut.result()

                    if res is None:
                        rejected_count += 1
                        # Re-enqueue failed task.
                        task_id_counter += 1
                        new_fut = executor.submit(generate_row_worker, (task_id_counter, assigned_p, assigned_t))
                        active_futures[new_fut] = (assigned_p, assigned_t)
                        continue

                    expr_obf = res["expr_obf"]
                    expr_hash = hashlib.sha256(expr_obf.encode()).hexdigest()

                    # Strict deduplication gatekeeper across all pillars.
                    if expr_hash in seen_hashes:
                        rejected_count += 1
                        task_id_counter += 1
                        new_fut = executor.submit(generate_row_worker, (task_id_counter, assigned_p, assigned_t))
                        active_futures[new_fut] = (assigned_p, assigned_t)
                        continue

                    seen_hashes.add(expr_hash)
                    out_f.write(json.dumps(res["row"]) + "\n")
                    out_f.flush()

                    total_verified += 1
                    pillar_counts[res["pillar"]] += 1
                    tier_counts[res["tier"]] += 1
                    total_nodes += res["obf_nodes"]
                    total_eta += res["eta_ast"]
                    total_latency += res["z3_latency_ms"]

                    # Emit real-time progress update at 5% intervals.
                    pct = (total_verified / args.rows) * 100.0
                    if pct >= next_progress_pct or total_verified == args.rows:
                        elapsed = time.time() - start_time
                        print(f"[Progress] {total_verified}/{args.rows} rows verified ({pct:.1f}%) | Elapsed: {elapsed:.1f}s", flush=True)
                        next_progress_pct += 5.0

                    # Submit replenishment task if remaining work exists.
                    if task_queue and len(active_futures) < max_in_flight:
                        p, t = task_queue.pop()
                        task_id_counter += 1
                        new_fut = executor.submit(generate_row_worker, (task_id_counter, p, t))
                        active_futures[new_fut] = (p, t)

    elapsed_total = time.time() - start_time
    avg_nodes = total_nodes / total_verified if total_verified > 0 else 0.0
    avg_eta = (total_eta / total_verified) * 100.0 if total_verified > 0 else 0.0
    avg_latency = total_latency / total_verified if total_verified > 0 else 0.0

    # Display final comprehensive telemetry table.
    print("\n" + "=" * 65)
    print("      PALIMPSEST V2 NEUROSYMBOLIC DATASET TELEMETRY")
    print("=" * 65)
    print(f"Total Verified Rows:          {total_verified}")
    print(f"Rejected / Retried Rows:      {rejected_count}")
    print(f"Deduplication (Unique Inputs): 100.0% ({len(seen_hashes)} unique)")
    print("-" * 65)
    print("Pillar Distribution:")
    for p_name in ["SFT", "CEGIS", "IDEMPOTENT", "CONSTANT_FOLDING"]:
        cnt = pillar_counts[p_name]
        pct = (cnt / total_verified) * 100.0 if total_verified > 0 else 0.0
        print(f"  - {p_name:<18}: {cnt:>5} rows ({pct:5.1f}%)")
    print("-" * 65)
    print("Curriculum Tier Distribution:")
    for t_num in [1, 2, 3]:
        cnt = tier_counts[t_num]
        pct = (cnt / total_verified) * 100.0 if total_verified > 0 else 0.0
        print(f"  - Tier {t_num}            : {cnt:>5} rows ({pct:5.1f}%)")
    print("-" * 65)
    print(f"Average Obfuscated AST Nodes: {avg_nodes:.2f}")
    print(f"Average AST Compression Ratio: {avg_eta:.2f}%")
    print(f"Average Z3 Proof Latency:     {avg_latency:.3f} ms")
    print(f"Total Generation Wall Clock:  {elapsed_total:.2f} s")
    print(f"Dataset Written Directly To:  {args.output}")
    print("=" * 65 + "\n")

if __name__ == "__main__":
    main()
