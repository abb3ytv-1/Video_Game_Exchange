FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV DATABASE_URL=postgresql://gameuser:passgame@postgres:5432/videogameexchange

# Set working directory
WORKDIR /app

# Install system dependencies needed for psycopg2 and general builds
RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        build-essential \
        gcc \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

# Copy dependency file
COPY requirements.txt .

# Install Python dependencies
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Expose port FastAPI runs on
EXPOSE 8000

# Start FastAPI using uvicorn
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
