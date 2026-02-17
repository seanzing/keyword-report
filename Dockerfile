FROM python:3.12-slim

WORKDIR /app

# --- Heavy, rarely-changing layers first (cached between deploys) ---

# WeasyPrint system deps (Cairo/Pango)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf-2.0-0 \
    libffi-dev \
    shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

# Install Python deps (only re-runs when pyproject.toml changes)
COPY pyproject.toml .
RUN mkdir -p keyword_report && touch keyword_report/__init__.py \
    && pip install --no-cache-dir . \
    && rm -rf keyword_report

# Install Playwright Firefox (only re-runs when pip deps change)
RUN playwright install --with-deps firefox

# --- Fast layer: copy application code (changes every push) ---
COPY keyword_report/ keyword_report/

# Create reports directory
RUN mkdir -p reports

ENV PORT=8080
EXPOSE ${PORT}

CMD uvicorn keyword_report.web:app --host 0.0.0.0 --port $PORT
