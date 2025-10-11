import React from "react";

export default function Cell({ value, onClick }) {
  const getBackground = () => {
    if (value === 1) return "#333";   // filled
    if (value === 2) return "#eee";   // cross
    return "white";                   // empty
  };

  return (
    <div
      onClick={onClick}
      style={{
        width: 40,
        height: 40,
        margin: 2,
        border: "1px solid #555",
        background: getBackground(),
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: "18px",
        cursor: "pointer",
        userSelect: "none",
      }}
    >
      {value === 2 ? "✕" : ""}
    </div>
  );
}