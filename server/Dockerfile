FROM python:3.12-slim

WORKDIR /app

# Install dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy server code
COPY server.py .

# Create uploads directory
RUN mkdir -p /app/uploads

# Environment variables (can be overridden in docker-compose)
ENV RDM_HOST=0.0.0.0
ENV RDM_PORT=8765
ENV RDM_UPLOAD_DIR=/app/uploads
ENV RDM_MAX_FILE_SIZE_MB=500
ENV RDM_ROOM_EXPIRY_SECONDS=14400

EXPOSE 8765

CMD ["python", "server.py"]
