FROM python:3.11-slim
WORKDIR /app
COPY backend/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY backend/alembic ./alembic
COPY backend/tests ./tests
COPY backend/alembic.ini backend/pytest.ini ./
COPY fixtures ./fixtures
COPY scripts ./scripts
EXPOSE 8000
