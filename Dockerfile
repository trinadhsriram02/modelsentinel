FROM python:3.11-slim

WORKDIR /app

COPY requirements_hf.txt .

RUN pip install --no-cache-dir -r requirements_hf.txt

COPY src/ ./src/

EXPOSE 7860

CMD ["uvicorn", "src.api.main:app", "--host", "0.0.0.0", "--port", "7860"]