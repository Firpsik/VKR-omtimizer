FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends ca-certificates curl \
    && curl -fsSL "https://storage.yandexcloud.net/cloud-certs/CA.pem" \
       -o /usr/local/share/ca-certificates/yandex-cloud-ca.crt \
    && update-ca-certificates \
    && rm -rf /var/lib/apt/lists/*

ENV DB_SSLROOTCERT=/usr/local/share/ca-certificates/yandex-cloud-ca.crt

WORKDIR /app

COPY requirements.cloud.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ src/
COPY data/ data/
COPY sql/ sql/

EXPOSE 8080

CMD ["uvicorn", "src.api.app:app", "--host", "0.0.0.0", "--port", "8080"]
