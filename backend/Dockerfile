FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# LightGBM's Linux wheel needs the OpenMP runtime; no model is fitted here.
RUN apt-get update \
    && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml uv.lock* ./
COPY backend ./backend

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -c backend/constraints-ci.txt ".[dev]"

CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
