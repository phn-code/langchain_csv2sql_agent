# Dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y libpq-dev gcc && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose the standard LangGraph API port
EXPOSE 8123

# Start the LangGraph API server
# --host 0.0.0.0 allows access from outside the container
# --port 8123 is the standard port
CMD ["langgraph", "dev", "--host", "0.0.0.0", "--port", "8123", "--no-browser"]