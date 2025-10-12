import React from "react";

export default function Cell({ value, onClick, rightBorder, bottomBorder, isHovered, onMouseEnter, onMouseLeave }) {
  const getBackground = () => {  
    if (value === 1) return "#333";   // filled
    if (value === 2) return "#eee";   // cross
    return "white";                   // empty
  };

  return (
    <div
      onClick={onClick}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      style={{
        width: 40,
        height: 40,
        margin: 2,
        borderLeft: "1px solid black",
        borderTop: "1px solid black",
        borderRight: rightBorder ? "2px solid black" : "1px solid black",
        borderBottom: bottomBorder ? "2px solid black" : "1px solid black",
        background: getBackground(),
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: "18px",
        cursor: "pointer",
        userSelect: "none",
        transition: "background 0.1s ease",
      }}
    >
      {value === 2 ? "✕" : ""}
    </div>
  );
}