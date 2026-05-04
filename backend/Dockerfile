FROM python:3.12-slim

WORKDIR /app

# Copy everything needed for install
COPY pyproject.toml .
COPY src/ ./src/

# Install dependencies
RUN pip install --no-cache-dir -e ".[dev]"

# Create data directory for SQLite
RUN mkdir -p data

EXPOSE 8000

CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]