from typing import List, Dict, Tuple, Optional
from itertools import combinations
import time
# from pysat.solvers import Solver  # uses Glucose by default
from pysat.solvers import Minisat22 as Solver
import csv


def validate_puzzle(p: Dict[str, List[List[int]]]) -> Tuple[int,int]:
    assert isinstance(p, dict) and "rows" in p and "columns" in p, \
        "Expect dict with keys 'rows' and 'columns'."
    rows, cols = p["rows"], p["columns"]
    assert isinstance(rows, list) and isinstance(cols, list), "rows/columns must be lists."
    for line in rows:
        assert isinstance(line, list) and all(isinstance(x, int) and x > 0 for x in line), \
            "Each row clue must be a list of positive ints."
    for line in cols:
        assert isinstance(line, list) and all(isinstance(x, int) and x > 0 for x in line), \
            "Each column clue must be a list of positive ints."
    rlen, clen = len(rows), len(cols)
    assert rlen > 0 and clen > 0, "Empty puzzle."
    return rlen, clen


def cell_var(r: int, c: int, clen: int) -> int:
    # 1-based
    return r * clen + c + 1


class VarPool:
    def __init__(self, start: int = 0):
        self.n = start  # last used var id
    def new(self, k: int = 1) -> List[int]:
        self.n += k
        return list(range(self.n - k + 1, self.n + 1))


def encode_line(N: int, blocks: List[int], line_vars: List[int], vp: VarPool) -> List[List[int]]:
    clauses: List[List[int]] = []

    # handle empty line (no blocks)
    if not blocks:
        for x in line_vars:
            clauses.append([-x])
        return clauses

    k = len(blocks)
    L = blocks[:]

    # earliest/latest feasible starts (with >=1 space between blocks)
    min_start = [0] * k
    for i in range(1, k):
        min_start[i] = min_start[i-1] + L[i-1] + 1
    total_len = sum(L) + (k - 1)
    tail = N - total_len
    if tail < 0:
        # impossible to fit -> add empty clause to force UNSAT
        clauses.append([])
        return clauses
    max_start = [min_start[i] + tail for i in range(k)]

    # start variables for each block, with exactly-one constraints
    starts: List[List[int]] = []
    for i in range(k):
        positions = list(range(min_start[i], max_start[i] + 1))
        s_vars = vp.new(len(positions))
        starts.append(s_vars)
        # at least one
        clauses.append(s_vars[:])
        # at most one (pairwise)
        for a, b in combinations(s_vars, 2):
            clauses.append([-a, -b])

    # ordering between consecutive blocks
    for i in range(k - 1):
        Li = L[i]
        for idx_p, p in enumerate(range(min_start[i], max_start[i] + 1)):
            s_ip = starts[i][idx_p]
            earliest_next = p + Li + 1
            for idx_q, q in enumerate(range(min_start[i+1], max_start[i+1] + 1)):
                if q < earliest_next:
                    clauses.append([-s_ip, -starts[i+1][idx_q]])

    # coverage: s(i,p) -> fill covered cells
    for i in range(k):
        Li = L[i]
        for idx_p, p in enumerate(range(min_start[i], max_start[i] + 1)):
            s_ip = starts[i][idx_p]
            for j in range(p, p + Li):
                clauses.append([-s_ip, line_vars[j]])

    # soundness: filled -> some covering start
    for j, x in enumerate(line_vars):
        covering = []
        for i in range(k):
            Li = L[i]
            for idx_p, p in enumerate(range(min_start[i], max_start[i] + 1)):
                if p <= j <= p + Li - 1:
                    covering.append(starts[i][idx_p])
        if covering:
            clauses.append([-x] + covering)
        else:
            clauses.append([-x])

    return clauses


def nonogram_to_cnf(puzzle: Dict[str, List[List[int]]]) -> Tuple[List[List[int]], int, int, int]:
    rlen, clen = validate_puzzle(puzzle)
    rows, cols = puzzle["rows"], puzzle["columns"]

    clauses: List[List[int]] = []
    vp = VarPool(start=rlen * clen)

    # rows
    for r in range(rlen):
        row_vars = [cell_var(r, c, clen) for c in range(clen)]
        clauses += encode_line(clen, rows[r], row_vars, vp)

    # columns
    for c in range(clen):
        col_vars = [cell_var(r, c, clen) for r in range(rlen)]
        clauses += encode_line(rlen, cols[c], col_vars, vp)

    num_vars = vp.n
    return clauses, num_vars, rlen, clen


def solve_with_pysat(clauses: List[List[int]], print_stats: bool = True) -> Optional[List[int]]:
    nvars_input = max(abs(lit) for cl in clauses for lit in cl)
    nclauses_input = len(clauses)
    with Solver(bootstrap_with=clauses) as s:
        t0 = time.perf_counter()
        sat = s.solve()
        t1 = time.perf_counter()
        elapsed = t1 - t0
        stats = s.accum_stats().copy()
        stats.update({
            "nvars_input": nvars_input,
            "nclauses_input": nclauses_input,
            "nvars_solver": s.nof_vars(),
            "nclauses_solver": s.nof_clauses(),
            "backend": type(s).__name__,
            "time_ms": round(elapsed * 1000, 3),
        })
        if print_stats:
            print(stats)
        if not sat:
            return None
        return s.get_model()  # list of signed ints


def check_model(clauses, model):
    assignment = {abs(l): (l > 0) for l in model}
    return all(any(assignment.get(abs(lit), False) == (lit > 0) for lit in cl)
               for cl in clauses)


def model_to_grid(model: List[int], rlen: int, clen: int) -> List[List[int]]:
    true_lits = set(l for l in model if l > 0)
    grid = [[1 if cell_var(r, c, clen) in true_lits else 0 for c in range(clen)] for r in range(rlen)]
    return grid


def pretty_print(grid: List[List[int]]) -> None:
    for row in grid:
        print(" ".join("█" if v else "·" for v in row))


def save_nonogram_csv(grid, puzzle_id):
    filename = f"nonogram_solution_{puzzle_id}.csv"
    with open(filename, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerows(grid)
    print(f"Raw grid saved to '{filename}'")

def solve_nonogram(puzzle: Dict[str, List[List[int]]], print_stats = True) -> List[List[List[int]]]:
    clauses, num_vars, rlen, clen = nonogram_to_cnf(puzzle)
    grids = []
    unsolvable = False
    num_solutions = 0
    while not unsolvable:
        model = solve_with_pysat(clauses, print_stats=print_stats)
        if model is None:
            unsolvable = True
            break
        # add blocking clause to prevent same solution
        grid = model_to_grid(model, rlen, clen)
        grids.append(grid)
        blocking_clauses = [-cell_var(r, c, clen) if grid[r][c] == 1 else cell_var(r, c, clen)
                           for r in range(rlen) for c in range(clen)]
        clauses.append(blocking_clauses)
        num_solutions += 1
        if num_solutions >= 2:
            print("Reached 2 solutions, stopping search.")
            break
    
    return grids


if __name__ == "__main__":

    import json

    # verify unique solution nonograms are indeed unique and solution matches original
    unique_solution_nonograms = json.load(open('unique_solution_nonograms.json'))
    for nonogram in unique_solution_nonograms:
        grids = solve_nonogram(nonogram['clues'], True)
        assert len(grids) == 1 and grids[0] == nonogram['solution']
        print(f"Verified puzzle {nonogram['id']} with density {nonogram['density']:.2f} has a unique solution.")
