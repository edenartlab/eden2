FROM python:3.11-slim-bullseye AS python

ARG ENV_FILE=.env

ENV PYTHONUNBUFFERED=1

WORKDIR /tgbot

COPY eve/clients/telegram/client.py .
COPY eve/sdk ./eve/sdk
COPY pyproject.toml .

RUN pip install ".[telegram]" && \
    pip install python-telegram-bot==21.7

RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy the environment file
COPY ${ENV_FILE} .env

ENTRYPOINT ["python", "client.py"]
CMD ["--env", ".env"]