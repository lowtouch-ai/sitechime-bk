FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONUNBUFFERED 1

RUN apt-get update && \
    apt-get install -y --no-install-recommends gcc python3-dev libssl-dev netcat-traditional && \
    rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Create logs directory and set permissions
RUN mkdir -p logs && \
    touch logs/.gitkeep && \
    chmod -R 755 logs && \
    chown -R www-data:www-data logs && \
    python manage.py collectstatic --noinput && \
    chmod +x entrypoint.sh

EXPOSE 8000

ENTRYPOINT ["/app/entrypoint.sh"]
CMD ["gunicorn", "--workers=4", "--worker-class=sync", "--timeout=120", "--keep-alive=5", "--worker-connections=1000", "--backlog=2048", "--log-level=info", "--access-logfile=-", "--error-logfile=-", "--bind=0.0.0.0:8000", "cloudcontrol_widget_backend.wsgi:application"]