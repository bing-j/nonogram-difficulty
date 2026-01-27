
def show_nonograms_in_console(nonograms):
    for puzzle in nonograms:
        print("Puzzle ID:", puzzle.get('id', 'N/A'))
        row_hints = puzzle['clues']['rows']
        column_hints = puzzle['clues']['columns']
        height = len(row_hints)
        width = len(column_hints)

        # Print column hints
        max_col_hint_len = max(len(hint) for hint in column_hints)
        for i in range(max_col_hint_len):
            line = '   ' * 5 + ' '  # space for row hints
            for ch in column_hints:
                if len(ch) >= max_col_hint_len - i:
                    line += f"{ch[len(ch) - (max_col_hint_len - i)]:>2} "
                else:
                    line += "   "
            print(line)

        # Print row hints and grid
        for r in range(height):
            line = '   ' * (5 - len(row_hints[r])) + ' '.join(f"{num:>2}" for num in row_hints[r]) + ' |'
            # Get the solution
            for c in range(width):
                if puzzle['solution'][r][c] == 1:
                    line += ' █ '
                else:
                    line += ' . ' # empty grid representation
            print(line)
        print("\n")

if __name__ == "__main__":
    import json
    with open('nonograms_6.json', 'r') as f:
        selected_nonograms = json.load(f)
    show_nonograms_in_console(selected_nonograms)