FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

ENV SENTRA_HOST=0.0.0.0
ENV SENTRA_PORT=8050

EXPOSE 8050

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8050"]
