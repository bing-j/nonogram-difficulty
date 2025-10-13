import React from "react";

export default function Controls({ onReset, onSubmit, grid }) {
  return (
    <div className="flex justify-center gap-8">
      <button
        onClick={onReset}
        className="px-4 py-2 bg-red-500 mt-8 text-white font-bold rounded-lg hover:bg-red-600 transition-colors"
      >
        Reset
      </button>
      <button
        onClick={onSubmit}
        className="px-4 py-2 bg-green-500 mt-8 text-white font-bold rounded-lg hover:bg-green-600 transition-colors"
      >
        Submit Answer
      </button>
    </div>
  );
}
