from typing import List
from .nonogram_pysat import nonogram_to_cnf, solve_with_pysat, model_to_grid, validate_puzzle

class UnsolvableError(Exception):
    """Raised when the Nonogram puzzle has no valid solution."""
    pass

def solve_nonogram(row_clues: List[List[int]], col_clues: List[List[int]]) -> List[List[int]]:
    """
    Solves a Nonogram puzzle and returns a 2D list (grid) of 0/1.
    1 = filled cell, 0 = empty cell.
    """
    puzzle = {"rows": row_clues, "columns": col_clues}
    # Validate
    rlen, clen = validate_puzzle(puzzle)

    # Build CNF and solve
    clauses, _, _, _ = nonogram_to_cnf(puzzle)
    model = solve_with_pysat(clauses)
    if model is None:
        raise UnsolvableError("This puzzle has no solution.")

    # Convert model -> grid
    grid = model_to_grid(model, rlen, clen)
    return grid
