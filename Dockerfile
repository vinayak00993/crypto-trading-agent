FROM python:3.11-slim

WORKDIR /app

# Copy project files
COPY pyproject.toml .
COPY configs/ configs/
COPY src/ src/
COPY README.md .
COPY .env.example .

# Install dependencies (including scikit-learn for ML model)
RUN pip install --no-cache-dir \
    ccxt pandas numpy pydantic pydantic-settings pyyaml \
    python-dotenv structlog rich apscheduler flask \
    scikit-learn

# Create necessary directories
RUN mkdir -p logs data/historical data/cache data/ml_learner

ENV PYTHONPATH=/app/src

# Expose dashboard port
EXPOSE 5555

# Start the agent with live dashboard
CMD ["python", "-m", "agent.live"]
