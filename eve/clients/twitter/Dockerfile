FROM python:3.11-slim-bullseye AS python

ARG ENV_FILE=.env

ENV PYTHONUNBUFFERED=1

WORKDIR /xbot

COPY eve/clients/twitter/client.py .
COPY eve/sdk ./eve/sdk
COPY pyproject.toml .

RUN pip install ".[twitter]" && \
    pip install requests_oauthlib==2.0.0

RUN apt-get update && \
    apt-get install -y --no-install-recommends git && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

# Copy the environment file
COPY ${ENV_FILE} .env

ENTRYPOINT ["python", "client.py"]
CMD ["--env", ".env"]