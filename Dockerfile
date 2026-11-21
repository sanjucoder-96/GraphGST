FROM python:3.11-slim

WORKDIR /app

# Install system deps first so pip cache survives code edits
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Then copy the app
COPY . .

EXPOSE 8000

CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
