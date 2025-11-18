import React from "react";

export default function HintModal({ hint, isOpen, onClose }) {
  if (!isOpen || !hint) return null;

  return (
    <div
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        bottom: 0,
        backgroundColor: "rgba(0, 0, 0, 0.5)",
        display: "flex",
        justifyContent: "center",
        alignItems: "center",
        zIndex: 1000,
      }}
      onClick={onClose}
    >
      <div
        style={{
          backgroundColor: "white",
          padding: "2rem",
          borderRadius: "8px",
          maxWidth: "400px",
          width: "90%",
          boxShadow: "0 4px 6px rgba(0, 0, 0, 0.1)",
        }}
        onClick={(e) => e.stopPropagation()}
      >
        <p style={{ marginBottom: "1.5rem", fontSize: "1.1rem", textAlign: "center" }}>
          💡 Hint: Check <strong>Row {hint.r + 1}, Column {hint.c + 1}</strong>. This cell doesn't match the solution.
        </p>
        <button
          onClick={onClose}
          style={{
            width: "100%",
            padding: "0.75rem 2rem",
            backgroundColor: "#4169E1",
            color: "white",
            border: "none",
            borderRadius: "4px",
            cursor: "pointer",
            fontWeight: "bold",
            fontSize: "1rem",
          }}
        >
          Got it
        </button>
      </div>
    </div>
  );
}

