FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY cifs_exporter/ ./cifs_exporter/

RUN useradd --create-home --uid 1000 scanner
USER scanner

EXPOSE 9877

ENTRYPOINT ["python", "-m", "cifs_exporter.main"]
