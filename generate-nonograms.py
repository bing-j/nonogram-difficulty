import random
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd

all_nonograms = []
cell_densities = []
df = pd.DataFrame(columns=["id", "cell_density"])

with open('nonograms10x10.txt', 'r') as file:
    i = 0
    for line in file:
        split_line = line.strip().split('|')
        clues = [list(map(int, clue.split('.'))) for clue in split_line[0].strip().split(';')]
        row_clues, col_clues = clues[:10], clues[10:]
        solution = np.array(list(map(int, split_line[1].strip()))).reshape((10, 10))
        all_nonograms.append({
            "id": i,
            "clues": {
                "rows": row_clues,
                "columns": col_clues
            },
            "solution": solution.tolist(),
        })
        cell_density = np.sum(solution) / 100
        cell_densities.append(cell_density)
        df.loc[i] = i, cell_density
        i += 1

if __name__ == "__main__":
    print(f"Total nonograms loaded: {len(all_nonograms)}")
    nonograms = random.sample(all_nonograms, 12)
    with open('nonograms_sample.json', 'w') as f:
        import json
        json.dump(nonograms, f, indent=4)

    plt.figure(figsize=(10, 6))
    sns.histplot(df, x="cell_density", bins=10, kde=True)
    plt.title('Distribution of Cell Densities in Nonograms')
    plt.xlabel('Cell Density')
    plt.ylabel('Frequency')
    plt.show()

        




