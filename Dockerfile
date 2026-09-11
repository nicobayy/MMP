FROM python:3.12-slim
WORKDIR /app
COPY requirements-lock.txt .
RUN pip install --no-cache-dir -r requirements-lock.txt
COPY config/ config/
COPY src/ src/
COPY scripts/ scripts/
COPY .env.example .env.example
RUN useradd -m -u 10001 mmp && chown -R mmp:mmp /app
USER mmp
# DB & cache hidup di volume agar histori tak hilang tiap rebuild
VOLUME ["/app/data"]
HEALTHCHECK --interval=5m --timeout=30s --retries=2 CMD python -c "import yaml;yaml.safe_load(open('config/mmp_config.yaml'));print('ok')"
CMD ["python", "scripts/run_scan.py", "--help"]
