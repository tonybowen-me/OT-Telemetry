FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app

# requirements.txt is a superset of what both services need at runtime
# (fastapi/uvicorn for the lab; + pydantic/PyYAML for PILOT).
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app ./app
COPY lab ./lab
COPY datasets ./datasets

EXPOSE 8000
# Default command runs PILOT; docker-compose overrides it to also run the lab.
# Render provides $PORT; default to 8000 for local `docker run`.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
