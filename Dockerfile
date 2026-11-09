FROM python:3.13-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HUB_DATA_DIR=/data
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY hub ./hub
RUN useradd --uid 10001 --create-home hub && mkdir -p /data && chown hub:hub /data
USER hub
EXPOSE 8090
CMD ["uvicorn", "hub.app:app", "--host", "0.0.0.0", "--port", "8090", "--no-proxy-headers"]
