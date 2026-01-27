import pandas as pd
import seaborn as sns
import matplotlib.pyplot as plt

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
    plt.figure(figsize=(10, 8))
    sns.heatmap(correlation_matrix, annot=True, fmt=".2f", cmap="coolwarm")
    plt.title("Correlation Matrix of Nonogram Solver Statistics")
    plt.show()

    # Plot the distribution of conflicts
    plt.figure(figsize=(10, 6))
    sns.histplot(df['conflicts'], bins=30, kde=True)
    plt.title('Distribution of Conflicts')
    plt.xlabel('Number of Conflicts')
    plt.ylabel('Frequency')
    plt.show()
    

    # Select six representative puzzles

    # CAREFUL: The following code is commented out to prevent overwriting existing files.
    
    selected_puzzles_df = select_six(df)
    selected_puzzles_df = selected_puzzles_df.reset_index(drop=True)
    print("\nSelected Six Representative Puzzles:")
    print(selected_puzzles_df)
    selected_puzzles_df.to_csv("selected_six_nonogram_stats.csv", index=True)  # The index will be the id used in the nonogram file

    import json
    selected_ids = selected_puzzles_df['puzzle_id'].tolist()
    puzzles = json.load(open('unique_solution_nonograms_1000.json', 'r'))
    selected_puzzles = [p for p in puzzles if p['id'] in selected_ids]
    # overwrite ids to be 0-5
    for i in range(len(selected_puzzles)):
        selected_puzzles[i]['id'] = [i]
    with open('nonograms_6.json', 'w') as f:
        json.dump(selected_puzzles, f, indent=4)