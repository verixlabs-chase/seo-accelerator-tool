FROM python:3.12-slim

WORKDIR /app
ENV PYTHONPATH=/app
COPY backend/requirements.txt ./requirements.txt
COPY backend/requirements-dev.txt ./requirements-dev.txt
RUN pip install --no-cache-dir -r requirements-dev.txt

COPY backend/ .
RUN ln -s /app /app/backend
COPY Docs /app/Docs
COPY Docs /Docs
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
