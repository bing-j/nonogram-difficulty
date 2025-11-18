import React from "react";

export default function Cell({ value, onClick, onRightClick, rightBorder, bottomBorder, onMouseEnter, onMouseLeave, isHighlighted }) {
  // Map backend values to visuals
  const getBackground = () => {  
    if (value === 1) return "#333";   // filled
    if (value === -1) return "#eee";  // unknown (cross)
    return "#fff";                     // empty
  };

  const handleContextMenu = (e) => {
    e.preventDefault(); // Prevent browser context menu
    if (onRightClick) {
      onRightClick();
    }
  };

  return (
    <div
      onClick={onClick}
      onContextMenu={handleContextMenu}
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      style={{
        width: 40,
        height: 40,
        margin: 2,
        borderLeft: "1px solid black",
        borderTop: "1px solid black",
        borderRight: rightBorder ? "3px solid black" : "1px solid black",
        borderBottom: bottomBorder ? "3px solid black" : "1px solid black",
        background: getBackground(),
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        fontSize: 18,
        cursor: "pointer",
        userSelect: "none",
        transition: "background 0.1s ease",
        boxShadow: isHighlighted ? "0 0 0 5px #8E24AA, 0 0 15px rgba(142, 36, 170, 0.8)" : "none",
        position: "relative",
        zIndex: isHighlighted ? 10 : 1,
      }}
    >
      {value === -1 ? "✕" : ""}
    </div>
  );
}
