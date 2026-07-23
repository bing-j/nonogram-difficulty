import os

import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 10,
    "axes.spines.top": False,
    "axes.spines.right": False,
    "axes.grid": True,
    "grid.color": "#cccccc",
    "grid.linewidth": 0.6,
    "grid.linestyle": "-",
    "axes.axisbelow": True,
})

OUTPUT_DIR = os.path.join("outputs", "figures", "solver_stats_diagnostics")


def select_six(df: pd.DataFrame) -> pd.DataFrame:
    """Select six puzzles from the 1000 based on defining characteristics."""

    # Drop the outliers in number of conflicts
    filtered_df = df[df['conflicts'] < df['conflicts'].quantile(0.95)]

    # Pick the puzzles with the lowest, median, and highest number of conflicts
    lowest_conflicts = filtered_df.nsmallest(2, 'conflicts')
    median_conflicts = filtered_df.iloc[(filtered_df['conflicts'] - filtered_df['conflicts'].median()).abs().argsort()[:2]]
    highest_conflicts = filtered_df.nlargest(2, 'conflicts')
    selected = pd.concat([lowest_conflicts, median_conflicts, highest_conflicts])
    return selected


if __name__ == "__main__":
    os.makedirs(OUTPUT_DIR, exist_ok=True)

    # Load solver statistics from CSV
    df = pd.read_csv("nonogram_solver_stats.csv")

    # Display basic statistics
    print("Solver Statistics Summary:")
    print(df.describe())

    # Analyze correlations between different metrics
    correlation_matrix = df.drop(columns=['puzzle_id']).corr()
    print("\nCorrelation Matrix:")
    print(correlation_matrix)

    # Display the correlation matrix in a heatmap
    fig = plt.figure(figsize=(10, 8))
    sns.heatmap(correlation_matrix, annot=True, fmt=".2f", cmap="RdBu_r")
    fig.savefig(os.path.join(OUTPUT_DIR, "solver_stats_correlation_matrix.png"), bbox_inches="tight")
    plt.show()

    # Plot the distribution of conflicts
    fig = plt.figure(figsize=(10, 6))
    sns.histplot(df['conflicts'], discrete=True, kde=True)
    plt.xlabel('Number of Conflicts')
    plt.ylabel('Frequency')
    fig.savefig(os.path.join(OUTPUT_DIR, "solver_stats_conflicts_distribution.png"), bbox_inches="tight")
    plt.show()


    # Select six representative puzzles

    # CAREFUL: The following code is commented out to prevent overwriting existing files.
    
    # selected_puzzles_df = select_six(df)
    # selected_puzzles_df = selected_puzzles_df.reset_index(drop=True)
    # print("\nSelected Six Representative Puzzles:")
    # print(selected_puzzles_df)
    # selected_puzzles_df.to_csv("selected_six_nonogram_stats.csv", index=True)  # The index will be the id used in the nonogram file

    # import json
    # selected_ids = selected_puzzles_df['puzzle_id'].tolist()
    # puzzles = json.load(open('unique_solution_nonograms_1000.json', 'r'))
    # print(len(puzzles))
    # selected_puzzles = [p for p in puzzles if p['id'] in selected_ids]
    # print(len(selected_puzzles))
    # # overwrite ids to be 0-5
    # for i in range(len(selected_puzzles)):
    #     selected_puzzles[i]['id'] = i
    # with open('nonograms_6.json', 'w') as f:
    #     json.dump(selected_puzzles, f, indent=4)