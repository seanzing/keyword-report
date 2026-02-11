FROM python:3.12-slim

WORKDIR /app

# Install Python package first (so playwright CLI is available)
COPY pyproject.toml .
COPY keyword_report/ keyword_report/
RUN pip install --no-cache-dir .

# Let Playwright install Firefox + its exact system deps
RUN playwright install --with-deps firefox

# WeasyPrint system deps (Cairo/Pango) — use libgdk-pixbuf-2.0-0 for Trixie compat
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Create reports directory
RUN mkdir -p reports

ENV PORT=8080
EXPOSE ${PORT}

CMD uvicorn keyword_report.web:app --host 0.0.0.0 --port $PORT
