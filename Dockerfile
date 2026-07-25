FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY api ./api
COPY web ./web
COPY src ./src
COPY data ./data
COPY assets ./assets

ENV PYTHONUNBUFFERED=1
ENV PORT=8000

CMD ["python", "-m", "api.run"]
