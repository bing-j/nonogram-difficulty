import React, { useState, useEffect } from "react";

export default function Timer({ start = 0, running = true, onTimeUpdate }) {
  const [seconds, setSeconds] = useState(start);

  useEffect(() => {
    if (!running) return;

    const interval = setInterval(() => {
      setSeconds((prev) => {
        const newSeconds = prev + 1;
        // Notify parent of time update
        if (onTimeUpdate) {
          onTimeUpdate(newSeconds);
        }
        return newSeconds;
      });
    }, 1000);

    return () => clearInterval(interval);
  }, [running, onTimeUpdate]);

  // Reset timer when start changes
  useEffect(() => {
    setSeconds(start);
  }, [start]);

  const formatTime = (secs) => {
    const mins = Math.floor(secs / 60);
    const secsRemainder = secs % 60;
    return `${mins.toString().padStart(2, "0")}:${secsRemainder.toString().padStart(2, "0")}`;
  };

  return (
    <div className="text-center text-xl font-bold mb-4">
      Time: {formatTime(seconds)}
    </div>
  );
}
