FROM python:3.12-slim

WORKDIR /app

# Install system deps for confluent-kafka
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    librdkafka-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose ports: 9000 (TCP broker), 8080 (Query API)
EXPOSE 9000 8080

CMD ["python", "main.py"]
