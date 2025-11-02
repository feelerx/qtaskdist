FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY circuit_processor.py .
COPY simulator_worker.py .
COPY backend_worker.py .
COPY models.py .

# Create a non-root user
RUN useradd -m -u 1000 quantum && chown -R quantum:quantum /app
USER quantum

# Default command (can be overridden in docker-compose)
CMD ["python", "simulator_worker.py"]