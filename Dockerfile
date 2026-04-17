FROM python:3.12-slim
WORKDIR /app
COPY app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY app/generator.py .
USER 1000:1000
CMD ["python", "-u", "generator.py"]
