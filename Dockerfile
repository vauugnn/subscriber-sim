FROM python:3.12-slim

WORKDIR /app

# Install app dependencies only — no ML libs needed (inference server runs on host)
COPY app_requirements.txt .
RUN pip install --no-cache-dir -r app_requirements.txt

# Copy Streamlit app source and config
COPY app/ /app/
COPY .streamlit/ /app/.streamlit/

# Ensure data directory exists (will be overridden by volume mount)
RUN mkdir -p /app/data

ENV PYTHONPATH=/app

EXPOSE 8501

CMD ["streamlit", "run", "main.py"]
