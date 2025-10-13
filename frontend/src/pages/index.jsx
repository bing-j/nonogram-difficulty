import Link from "next/link";
import puzzles from "@/data/nonograms.json";

export default function PuzzleListPage() {
  return (
    <main
      style={{
        padding: "2rem",
        maxWidth: 600,
        margin: "0 auto",
        fontFamily: "system-ui, sans-serif",
      }}
    >
      <h1
        style={{
          fontSize: "2rem",
          fontWeight: "bold",
          textAlign: "center",
          marginBottom: "1.5rem",
          color: "#2d3436",
        }}
      >
        Choose a Puzzle
      </h1>

      <ul style={{ listStyle: "none", padding: 0 }}>
        {puzzles.map((puzzle) => (
          <li
            key={puzzle.id}
            style={{
              marginBottom: "0.75rem",
            }}
          >
            <Link
              href={`/puzzles/${puzzle.id}`}
              style={{
                display: "block",
                padding: "0.75rem 1rem",
                borderRadius: "10px",
                backgroundColor: "#f1f2f6",
                color: "#2d3436",
                textDecoration: "none",
                fontSize: "1.1rem",
                fontWeight: 500,
                transition: "all 0.2s ease",
              }}
              onMouseEnter={(e) =>
                (e.target.style.backgroundColor = "#dfe6e9")
              }
              onMouseLeave={(e) =>
                (e.target.style.backgroundColor = "#f1f2f6")
              }
            >
              Puzzle {puzzle.id}
            </Link>
          </li>
        ))}
      </ul>
    </main>
  );
}
