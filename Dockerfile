FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY config/ config/
COPY src/ src/
COPY scripts/ scripts/
COPY dashboard/ dashboard/
COPY .env.example .env.example
# DB & cache hidup di volume agar histori tak hilang tiap rebuild
VOLUME ["/app/data"]
CMD ["python", "scripts/run_scan.py", "--help"]
