FROM python:3.12-slim

# System deps for WeasyPrint (Cairo/Pango) and Playwright
RUN apt-get update && apt-get install -y --no-install-recommends \
    # WeasyPrint dependencies
    libcairo2 \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    # Playwright Firefox dependencies
    libgtk-3-0 \
    libdbus-glib-1-2 \
    libxt6 \
    libx11-xcb1 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python package
COPY pyproject.toml .
COPY keyword_report/ keyword_report/
RUN pip install --no-cache-dir .

# Install Playwright Firefox browser
RUN playwright install firefox

# Create reports directory
RUN mkdir -p reports

EXPOSE 8080

CMD ["uvicorn", "keyword_report.web:app", "--host", "0.0.0.0", "--port", "8080"]
