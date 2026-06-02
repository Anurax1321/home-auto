# Container image for the home-auto service. Use this once Docker is available
# (enable WSL integration in Docker Desktop, or run on your NAS/PC directly).

FROM python:3.12-slim

WORKDIR /app

# Install dependencies first so this layer caches across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application source.
COPY src/ ./src/

# Run as a non-root user to limit blast radius if the web surface is compromised.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

# The dashboard listens on 8080 by default.
EXPOSE 8080

# `python -m home_auto` starts the scheduler loop + dashboard together.
ENV PYTHONPATH=/app/src
CMD ["python", "-m", "home_auto"]
