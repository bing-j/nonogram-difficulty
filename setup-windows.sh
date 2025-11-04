#!/bin/bash
python -m venv .venv

source ".venv\Scripts\activate"

pip install -r backend/requirements.txt

# Function to be executed upon receiving SIGINT
cleanup() {
    echo "Caught SIGINT. Cleaning up..."
    kill $server_pid1 $server_pid2  # Terminates both server processes
    exit
}

# Set up the trap
trap cleanup SIGINT

# Start the Uvicorn server in the background
uvicorn backend.main:app --reload --port 8000 &
server_pid1=$!  # Get the process ID of the last backgrounded command

# Start the npm server in the background
cd frontend && npm ci && npm run dev && sleep 10 && start http://localhost:3000/ &
server_pid2=$!  # Get the process ID of the last backgrounded command

# Wait indefinitely. The cleanup function will handle interruption and cleanup.
wait