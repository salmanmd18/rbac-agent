FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps
RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential git && \
    rm -rf /var/lib/apt/lists/*

# Copy only reqs first (cache layer)
COPY requirements.txt .

# Tooling + robust install
RUN python -m pip install --upgrade --no-cache-dir pip setuptools wheel
RUN pip install --no-cache-dir --default-timeout=120 --retries 5 --prefer-binary -r requirements.txt

# Now copy the app
COPY . .

EXPOSE 8000 8501

# Use sh (bash may not exist)
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 & streamlit run streamlit_app.py --server.port 8501 --server.address 0.0.0.0"]
