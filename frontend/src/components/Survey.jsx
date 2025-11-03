import React, { useState } from "react";

export default function Survey({ questions, onSubmit }) {
  const [answers, setAnswers] = useState({});
  const [errors, setErrors] = useState({});

  const handleChange = (questionId, value) => {
    setAnswers(prev => ({ ...prev, [questionId]: value }));
    // Clear error when user makes a change
    if (errors[questionId]) {
      setErrors(prev => ({ ...prev, [questionId]: null }));
    }
  };

  const handleSubmit = (e) => {
    e.preventDefault();
    
    // Validate required questions
    const newErrors = {};
    questions.forEach(q => {
      if (!answers[q.id]) {
        newErrors[q.id] = "This question is required";
      }
    });

    if (Object.keys(newErrors).length > 0) {
      setErrors(newErrors);
      return;
    }

    onSubmit(answers);
  };

  const renderQuestion = (question) => {
    const { id, prompt, type, options, min, max, allow_free_text } = question;

    if (type === "single") {
      return (
        <div key={id} style={{ marginBottom: "2rem" }}>
          <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: 500 }}>
            {prompt}
          </label>
          {options.map((opt) => (
            <label
              key={opt.value}
              style={{ display: "block", marginBottom: "0.5rem", cursor: "pointer" }}
            >
              <input
                type="radio"
                name={id}
                value={opt.value}
                checked={answers[id] === opt.value}
                onChange={(e) => handleChange(id, e.target.value)}
                style={{ marginRight: "0.5rem" }}
              />
              {opt.label}
            </label>
          ))}
          {errors[id] && <p style={{ color: "red", fontSize: "0.9rem", marginTop: "0.25rem" }}>{errors[id]}</p>}
        </div>
      );
    }

    if (type === "multi") {
      const handleMultiChange = (value, checked) => {
        const current = answers[id] || [];
        if (checked) {
          handleChange(id, [...current, value]);
        } else {
          handleChange(id, current.filter(v => v !== value));
        }
      };

      return (
        <div key={id} style={{ marginBottom: "2rem" }}>
          <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: 500 }}>
            {prompt}
          </label>
          {options.map((opt) => (
            <label
              key={opt.value}
              style={{ display: "block", marginBottom: "0.5rem", cursor: "pointer" }}
            >
              <input
                type="checkbox"
                value={opt.value}
                checked={(answers[id] || []).includes(opt.value)}
                onChange={(e) => handleMultiChange(opt.value, e.target.checked)}
                style={{ marginRight: "0.5rem" }}
              />
              {opt.label}
            </label>
          ))}
          {allow_free_text && (
            <input
              type="text"
              placeholder="Other (please specify)"
              value={answers[`${id}_other`] || ""}
              onChange={(e) => handleChange(`${id}_other`, e.target.value)}
              style={{
                marginTop: "0.5rem",
                padding: "0.5rem",
                width: "100%",
                border: "1px solid #ccc",
                borderRadius: "4px"
              }}
            />
          )}
          {errors[id] && <p style={{ color: "red", fontSize: "0.9rem", marginTop: "0.25rem" }}>{errors[id]}</p>}
        </div>
      );
    }

    if (type === "scale") {
      return (
        <div key={id} style={{ marginBottom: "2rem" }}>
          <label style={{ display: "block", marginBottom: "1rem", fontWeight: 500 }}>
            {prompt}
          </label>
          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            <span style={{ fontSize: "0.9rem" }}>{min}</span>
            <input
              type="range"
              min={min}
              max={max}
              value={answers[id] || min}
              onChange={(e) => handleChange(id, parseInt(e.target.value))}
              style={{ flex: 1 }}
            />
            <span style={{ fontSize: "0.9rem" }}>{max}</span>
            <span style={{ fontSize: "1.2rem", fontWeight: "bold", minWidth: "2rem", textAlign: "center" }}>
              {answers[id] || min}
            </span>
          </div>
          {errors[id] && <p style={{ color: "red", fontSize: "0.9rem", marginTop: "0.25rem" }}>{errors[id]}</p>}
        </div>
      );
    }

    if (type === "text") {
      return (
        <div key={id} style={{ marginBottom: "2rem" }}>
          <label style={{ display: "block", marginBottom: "0.5rem", fontWeight: 500 }}>
            {prompt}
          </label>
          <textarea
            value={answers[id] || ""}
            onChange={(e) => handleChange(id, e.target.value)}
            rows={allow_free_text ? 4 : 2}
            style={{
              width: "100%",
              padding: "0.5rem",
              border: "1px solid #ccc",
              borderRadius: "4px",
              fontSize: "1rem",
              fontFamily: "inherit"
            }}
            placeholder={allow_free_text ? "Your answer..." : ""}
          />
          {errors[id] && <p style={{ color: "red", fontSize: "0.9rem", marginTop: "0.25rem" }}>{errors[id]}</p>}
        </div>
      );
    }

    return null;
  };

  return (
    <div style={{
      maxWidth: "600px",
      margin: "0 auto",
      padding: "2rem",
      backgroundColor: "#f9f9f9",
      borderRadius: "8px"
    }}>
      <form onSubmit={handleSubmit}>
        {questions.map(renderQuestion)}
        <button
          type="submit"
          style={{
            width: "100%",
            padding: "1rem",
            backgroundColor: "#4169E1",
            color: "white",
            border: "none",
            borderRadius: "4px",
            fontSize: "1.1rem",
            fontWeight: "bold",
            cursor: "pointer",
            marginTop: "1rem"
          }}
        >
          Continue
        </button>
      </form>
    </div>
  );
}

