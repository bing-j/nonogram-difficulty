import time
import numpy as np
import pandas as pd
from backend.nonogram_pysat import nonogram_to_cnf, solve_with_pysat
from backend.nonogram_pysat import solve_nonogram

def count_consecutive_ones(arr: np.ndarray):
    """Count lengths of groups of consecutive 1s in a binary array."""
    lengths = []
    count = 0
    for val in arr:
        if val == 1:
            count += 1
        elif count > 0:
            lengths.append(count)
            count = 0
    if count > 0:
        lengths.append(count)
    return lengths

def generate_nonogram(cell_count: int):
    """
    Generate a random 10x10 nonogram with a specified number of filled cells.
    Returns the grid and the corresponding row and column hints.
    """
    if cell_count < 0 or cell_count > 100:
        raise ValueError("cell_count must be between 0 and 100")
    
    # Create a 10x10 array filled with zeros
    grid = np.zeros((10, 10), dtype=int)

    # Randomly select cell_count unique positions to set to 1
    indices = np.random.choice(grid.size, cell_count, replace=False)
    np.put(grid, indices, 1)

    # For each row, count lengths of groups of consecutive 1s
    row_hints = [count_consecutive_ones(row) for row in grid]
    # For each column, count lengths of groups of consecutive 1s
    column_hints = [count_consecutive_ones(grid[:, col]) for col in range(grid.shape[1])]

    return grid, row_hints, column_hints

def generate_nonogram_set(num_per_density: int, densities: list[int]):
    """
    Generate a set of nonograms with specified densities and number per density.
    Returns a list of nonograms with their grids and hints.
    """
    nonograms = []
    i = 1
    for density in densities:
        for _ in range(num_per_density):
            grid, row_hints, column_hints = generate_nonogram(density)
            nonograms.append({
                "id": i,
                "solution": grid.tolist(),
                "clues": {
                    "rows": row_hints,
                    "columns": column_hints
                },
                "density": density / 100
            })
            i += 1
    return nonograms

def generate_unique_nonograms(num_per_density: int, densities: list[int]):
    """
    Generate nonograms and filter to those with a unique solution.
    Returns a list of nonograms with unique solutions.
    """
    all_nonograms = []
    all_unique_nonograms = []
    one_density_unique_nonograms = []
    for i in range(len(densities)):
        while len(one_density_unique_nonograms) < num_per_density:
            density = densities[i]
            print(f"Generating nonogram with density {density}")
            grid, row_hints, column_hints = generate_nonogram(density)
            puzzle = {
                "id": len(all_nonograms) + 1,
                "solution": grid.tolist(),
                "clues": {
                    "rows": row_hints,
                    "columns": column_hints
                },
                "density": density / 100
            }
            all_nonograms.append(puzzle)
            grids = solve_nonogram(puzzle['clues'], print_stats=False)
            if len(grids) == 1 and puzzle not in one_density_unique_nonograms:
                one_density_unique_nonograms.append(puzzle)
                print(f"Found unique solution for puzzle {puzzle['id']} with density {puzzle['density']:.2f}")
        all_unique_nonograms.extend(one_density_unique_nonograms)
        one_density_unique_nonograms = []
    return all_unique_nonograms

def solve_batch(nonograms: list[dict]):
    """
    Generate random nonograms and solve them using PySAT.
    Collects solver statistics for each puzzle.
    
    Args:
        num_nonograms: Number of nonograms to generate and solve
        cell_count: Number of filled cells (default 50 for 10x10 = 50% density)
    
    Returns:
        DataFrame with solver statistics for each puzzle
    """
    stats_list = []
    for i in range(len(nonograms)):
        # Generate a random nonogram
        grid, row_hints, column_hints = nonograms[i]['solution'], nonograms[i]['clues']['rows'], nonograms[i]['clues']['columns']

        # Save the nonogram
        
        puzzle = {
            "rows": row_hints,
            "columns": column_hints
        }
        
        try:
            # Convert to CNF
            clauses, num_vars, rlen, clen = nonogram_to_cnf(puzzle)
            
            # Solve with PySAT and capture statistics
            t0 = time.perf_counter()
            model = solve_with_pysat(clauses, print_stats=False)
            t1 = time.perf_counter()
            
            # Get solver stats (solve_with_pysat returns None for model if UNSAT)
            # We need to re-run to get stats, so let's extract from solver
            from pysat.solvers import Minisat22 as Solver
            with Solver(bootstrap_with=clauses) as s:
                sat = s.solve()
                stats = s.accum_stats().copy()
                stats.update({
                    "puzzle_id": nonograms[i]['id'],
                    "solving_time": round((t1 - t0)*1000, 2),  # in milliseconds
                    "nvars_input": max(abs(lit) for cl in clauses for lit in cl) if clauses else 0,
                    "nclauses_input": len(clauses),
                    "nvars_solver": s.nof_vars(),
                    "nclauses_solver": s.nof_clauses(),
                })
            
            stats_list.append(stats)
            
        except Exception as e:
            print(f"Error solving puzzle {i + 1}: {e}")
            stats_list.append({
                "puzzle_id": i + 1,
                "grid_size": "10x10",
                "error": str(e)
            })
    
    # Create DataFrame
    df = pd.DataFrame(stats_list)
    
    return df

def show_solving_time_diff(nonograms):
    df = solve_batch(nonograms)
    df2 = solve_batch(nonograms)

    # Print the difference between solving times of two runs
    diffs = df['solving_time'] - df2['solving_time']
    print("\nDifferences in solving times between two runs (in ms):")
    print(diffs)

    # Print the max difference
    max_diff = diffs.abs().max()
    print(f"\nMaximum difference in solving times between two runs: {max_diff} ms")

    # Plot the distribution of solving time differences
    import matplotlib.pyplot as plt
    import seaborn as sns
    plt.figure(figsize=(10, 6))
    sns.histplot(diffs, bins=30, kde=True)
    plt.title('Distribution of Solving Time Differences Between Two Runs')
    plt.xlabel('Solving Time Difference (ms)')
    plt.ylabel('Frequency')
    plt.show()


if __name__ == "__main__":
    import json
    # Re-generate and solve 1000 nonograms
    nonograms = generate_unique_nonograms(1000, [50])
    with open('unique_solution_nonograms_1000.json', 'w') as f:
        json.dump(nonograms, f, indent=4)
    df = solve_batch(nonograms)

    # CAREFUL: The following code is commented out to prevent overwriting existing files.

    # # Save to CSV
    # output_file = "nonogram_solver_stats.csv"
    # df.to_csv(output_file, index=False)
    # print(f"\nStatistics saved to '{output_file}'")

    # # Show that solving times are not consistent across runs
    # show_solving_time_diff(nonograms)

