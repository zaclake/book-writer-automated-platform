# Use Python 3.11 slim image
FROM python:3.11-slim

# Set environment variables
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app

# Set work directory
WORKDIR /app

# Install system dependencies including tini
RUN apt-get update && apt-get install -y \
    gcc \
    tini \
    && rm -rf /var/lib/apt/lists/*

# Copy backend requirements and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy only the backend code to /app (not the entire project)
COPY . .

# Ensure start.sh has execute permissions
RUN chmod +x start.sh

# Create necessary directories first (as root)
RUN mkdir -p temp_projects logs

# Create non-root user and change ownership
RUN adduser --disabled-password --gecos '' appuser && \
    chown -R appuser:appuser /app

# Switch to non-root user
USER appuser

# Expose port
EXPOSE 8000

# Command to run the application with tini and start script
ENTRYPOINT ["tini", "--"]
CMD ["./start.sh"] 