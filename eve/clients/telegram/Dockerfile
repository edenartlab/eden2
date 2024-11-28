FROM python:3.11-slim

WORKDIR /tgbot

RUN apt-get update && apt-get install -y git

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

COPY client.py .

ENV PYTHONUTF8=1

CMD ["python", "client.py"]
