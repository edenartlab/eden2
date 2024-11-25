# syntax=docker/dockerfile:1
FROM python:3.11-slim-bullseye AS python

ARG ENV_FILE=.env

ENV PYTHONUNBUFFERED 1
WORKDIR /marsbots

COPY eve/clients/discord/client.py .
COPY eve/sdk ./eve/sdk
COPY pyproject.toml .

RUN pip install ".[discord]"

COPY ${ENV_FILE} .env

RUN apt-get update \
    && apt-get install -y git

ENTRYPOINT ["python", "client.py"]
CMD ["--env", ".env"]