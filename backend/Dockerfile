FROM python:3.12-slim
WORKDIR /app
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONPATH=/app
RUN apt-get update && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 1001 appuser \
    && useradd  --system --uid 1001 --gid 1001 --no-create-home appuser

COPY backend/requirements.txt .
RUN pip install -r requirements.txt
COPY backend/app ./app
COPY data ./data

# Drop root before the process starts. If a vulnerability allows remote code
# execution, the attacker gets a system user with no home directory and no
# write access outside /app rather than root on the host.
USER appuser

EXPOSE 8000
HEALTHCHECK CMD curl -f http://localhost:8000/health || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
