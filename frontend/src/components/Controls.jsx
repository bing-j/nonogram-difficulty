import React from "react";

export default function Controls({ onReset, onSubmit, grid }) {
  return (
    <div className="flex justify-center gap-8">
      <button
        onClick={onReset}
        className="px-4 py-2 bg-[#FFD3AC] mt-8 font-bold rounded-lg hover:cursor-pointer"
      >
        Reset
      </button>
      <button
        onClick={onSubmit}
        className="px-4 py-2 bg-[#4169E1] mt-8 text-white font-bold rounded-lg hover:cursor-pointer"
      >
        Submit Answer
      </button>
    </div>
  );
}
