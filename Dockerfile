# Cloud Run image: FastAPI floor + ADK crew.
# Scale to zero. Vertex + ADC at runtime. Do not bake project ids or keys.

FROM python:3.12-slim-bookworm
WORKDIR /app
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app/backend \
    ONECREW_HOST=0.0.0.0 \
    ONECREW_PORT=8080 \
    GEMINI_MODEL=gemini-2.5-flash \
    GOOGLE_GENAI_USE_VERTEXAI=true

COPY backend/requirements.txt /app/backend/requirements.txt
RUN pip install --no-cache-dir -r /app/backend/requirements.txt

COPY backend /app/backend
COPY sample_data /app/sample_data

EXPOSE 8080
CMD ["python", "-m", "onecrew"]
