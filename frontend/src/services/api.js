const BASE_URL = "http://localhost:8000";

export async function createPuzzle(rowClues, colClues) {
  const res = await fetch(`${BASE_URL}/puzzles`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ row_clues: rowClues, col_clues: colClues })
  });
  return await res.json();
}

export async function getBoard(sessionId) {
  const res = await fetch(`${BASE_URL}/sessions/${sessionId}/state`);
  return await res.json();
}

export async function makeMove(sessionId, r, c, value) {
  const res = await fetch(`${BASE_URL}/sessions/${sessionId}/move`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ r, c, value })
  });
  return await res.json();
}

export async function checkBoard(sessionId) {
  const res = await fetch(`${BASE_URL}/sessions/${sessionId}/check`, { method: "POST" });
  return await res.json();
}

export async function resetBoard(sessionId) {
  const res = await fetch(`${BASE_URL}/sessions/${sessionId}/reset`, { method: "POST" });
  return await res.json();
}

export async function endSession(sessionId) {
  const res = await fetch(`${BASE_URL}/sessions/${sessionId}/end`, { method: "POST" });
  return await res.json();
}

export async function downloadLogs(sessionId, format = "json") {
  const validFormats = ["json", "zip", "ndjson"];
  if (!validFormats.includes(format)) format = "json";

  const res = await fetch(`${BASE_URL}/sessions/${sessionId}/log/download.${format}`, {
    method: "GET",
  });

  if (!res.ok) throw new Error("Failed to download logs");

  const blob = await res.blob();
  const url = window.URL.createObjectURL(blob);

  const a = document.createElement("a");
  a.href = url;
  a.download = `nonogram_logs_${sessionId}.${format}`;
  document.body.appendChild(a);
  a.click();
  a.remove();
  window.URL.revokeObjectURL(url);
}

export async function startThreePuzzleSession() {
  const res = await fetch(`${BASE_URL}/session/start_three`, {
    method: "POST",
  });
  return await res.json();
}

export async function startTutorialSession() {
  const res = await fetch(`${BASE_URL}/session/start_tutorial`, {
    method: "POST",
  });
  return await res.json();
}

export async function startWarmupSession() {
  const res = await fetch(`${BASE_URL}/session/start_warmup`, {
    method: "POST",
  });
  return await res.json();
}

export async function getSurvey(sessionId, surveyType) {
  const res = await fetch(`${BASE_URL}/sessions/${sessionId}/survey/${surveyType}`);
  return await res.json();
}

export async function submitSurvey(sessionId, surveyType, answers) {
  const res = await fetch(`${BASE_URL}/sessions/${sessionId}/survey_submit`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ survey_type: surveyType, answers })
  });
  return await res.json();
}

export async function getHint(sessionId) {
  const res = await fetch(`${BASE_URL}/sessions/${sessionId}/hint`);
  return await res.json();
}

export async function getSessionLog(sessionId) {
  const res = await fetch(`${BASE_URL}/sessions/${sessionId}/log`);
  return await res.json();
}

export async function advancePuzzle(sessionId) {
  const res = await fetch(`${BASE_URL}/sessions/${sessionId}/advance`, {
    method: "POST",
  });
  return await res.json();
}
