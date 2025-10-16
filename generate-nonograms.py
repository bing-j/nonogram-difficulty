import numpy as np
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

def generate_nonogram(cell_count: int = 25):
    """
    Generate a random 10x10 nonogram with a specified number of filled cells.
    Returns the grid and the corresponding row and column hints.
    """
    if cell_count < 0 or cell_count > 100:
        raise ValueError("cell_count must be between 0 and 100")
    
    # Create a 10x10 array filled with zeros
    grid = np.zeros((10, 10), dtype=int)

    # Randomly select 25 unique positions to set to 1
    indices = np.random.choice(grid.size, 25, replace=False)
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

def generate_unique_nonograms(num_nonograms: int, densities: list[int]):
    """
    Generate nonograms and filter to those with a unique solution.
    Returns a list of nonograms with unique solutions.
    """
    
    all_nonograms = generate_nonogram_set(num_nonograms, densities)
    unique_nonograms = []
    density_index = 0
    while len(unique_nonograms) < num_nonograms:
        density = densities[density_index % len(densities)]
        density_index += 1
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
        grids = solve_nonogram(puzzle['clues'])
        if len(grids) == 1:
            unique_nonograms.append(puzzle)
            print(f"Found unique solution for puzzle {puzzle['id']} with density {puzzle['density']:.2f}")
    return unique_nonograms

if __name__ == "__main__":
    # import json
    # densities = [25, 50, 75]
    # nonograms = generate_nonogram_set(100, densities)
    # with open('generated_nonograms.json', 'w') as f:
    #     json.dump(nonograms, f, indent=4)
    # print(f"Generated {len(nonograms)} nonograms and saved to 'generated_nonograms.json'")
    import json
    densities = [25, 50, 75]
    unique_nonograms = generate_unique_nonograms(12, densities)
    with open('unique_solution_nonograms.json', 'w') as f:
        json.dump(unique_nonograms, f, indent=4)