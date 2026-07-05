FROM python:3.12-slim

WORKDIR /app

COPY pyproject.toml ./
COPY app ./app
COPY alembic ./alembic
COPY alembic.ini ./
RUN pip install --no-cache-dir .

COPY entrypoint.sh /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]
