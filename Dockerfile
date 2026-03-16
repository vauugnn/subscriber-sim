FROM python:3.12-slim

WORKDIR /app

# Install app dependencies only — no ML libs needed (inference server runs on host)
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy Streamlit app source and config
COPY app/ /app/
COPY .streamlit/ /app/.streamlit/

# Ensure data directory exists (will be overridden by volume mount)
RUN mkdir -p /app/data

ENV PYTHONPATH=/app

EXPOSE 8501

# Render (and other PaaS) injects $PORT at runtime. Fall back to 8501 for local Docker.
CMD ["sh", "-c", "streamlit run main.py --server.port ${PORT:-8501} --server.address 0.0.0.0"]
