FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev libssl-dev netcat-traditional dos2unix && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Fix line endings and ensure entrypoint.sh is executable
RUN dos2unix entrypoint.sh && \
    chmod +x entrypoint.sh && \
    mkdir -p logs && \
    chmod -R 755 logs

EXPOSE 8000

# Use shell form instead of exec form for entrypoint to ensure proper execution
ENTRYPOINT ["/bin/sh", "/app/entrypoint.sh"]
CMD ["gunicorn", "--workers=4", "--bind=0.0.0.0:8000", "cloudcontrol_widget_backend.wsgi:application"]