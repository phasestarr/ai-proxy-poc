# Purpose:
# - Build and package the FastAPI backend for containerized execution.
#
# Current responsibilities:
# - Install Python dependencies
# - Copy application code
# - Launch the FastAPI app through Uvicorn
#
# Notes:
# - Version pins are supplied through Docker build args from the repo-root .env.
# - Keep dependency layers cache-friendly when possible.

ARG PYTHON_VERSION=3.13.12
FROM python:${PYTHON_VERSION}-slim

ARG PIP_VERSION=25.3

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV PYTHONFAULTHANDLER=1

WORKDIR /app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip==${PIP_VERSION} \
    && python -m pip install --no-cache-dir -r requirements.txt

COPY app ./app

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--log-level", "debug", "--access-log"]
