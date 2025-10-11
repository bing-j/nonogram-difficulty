import React, { useState, useEffect } from "react";

export default function Timer({ start = 0, onTimeUp }) {
  const [seconds, setSeconds] = useState(start);

  useEffect(() => {
    const interval = setInterval(() => {
      setSeconds((prev) => prev + 1);
    }, 1000);

    return () => clearInterval(interval); 
  }, []);

  return (
    <div className="text-center text-xl font-bold mb-4">
      Time: {Math.floor(seconds / 60)
        .toString()
        .padStart(2, "0")}
      :
      {(seconds % 60).toString().padStart(2, "0")}
    </div>
  );
}