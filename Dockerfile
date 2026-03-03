FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install Python dependencies from project metadata.
COPY pyproject.toml README.md /app/
COPY src /app/src
RUN pip install --upgrade pip && pip install .

# Runtime files needed by web entry and source runtime.
COPY web_app.py source.py /app/

RUN mkdir -p /app/output

EXPOSE 8000

CMD ["uvicorn", "web_app:app", "--host", "0.0.0.0", "--port", "8000"]
