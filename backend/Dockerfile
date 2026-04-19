FROM python:3.11-slim

# Install Java (required by PySpark) and curl (used for health checks)
RUN apt-get update && \
    apt-get install -y --no-install-recommends openjdk-21-jre-headless curl && \
    rm -rf /var/lib/apt/lists/*

ENV JAVA_HOME=/usr/lib/jvm/java-21-openjdk-amd64
# Tell PySpark workers to use the same Python that runs the backend
ENV PYSPARK_PYTHON=/usr/local/bin/python3
ENV PYSPARK_DRIVER_PYTHON=/usr/local/bin/python3

WORKDIR /app

# Install Python dependencies first (better layer caching)
COPY backend/requirements.txt ./backend/requirements.txt
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install --no-cache-dir -r backend/requirements.txt

# ── Pre-build the sandbox venv with common data/science packages ──
# This avoids slow runtime downloads when users run PySpark / pandas code.
RUN --mount=type=cache,target=/root/.cache/pip \
    python3 -m venv --without-pip /app/sandbox_venv && \
    /app/sandbox_venv/bin/python -c \
        "import ensurepip; ensurepip._main(['--upgrade', '--default-pip'])" && \
    /app/sandbox_venv/bin/pip install --no-cache-dir \
        pyspark \
        pandas \
        numpy \
        matplotlib \
        pyarrow \
        scipy \
        scikit-learn

# Copy backend source
COPY backend/ ./backend/

# /app/backend on PYTHONPATH so "chatbot.*" imports resolve directly
# (uvicorn runs "backend.main:app" from /app, so "backend.*" resolves too)
ENV PYTHONPATH=/app/backend

EXPOSE 8000

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000"]
