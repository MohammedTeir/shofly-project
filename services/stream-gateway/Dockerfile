FROM python:3.12-slim
WORKDIR /app
COPY services/stream-gateway/requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/stream-gateway/app.py app.py
RUN mkdir -p /data
EXPOSE 8080
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080", "--no-access-log", "--proxy-headers"]
