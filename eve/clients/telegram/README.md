# Telegram-client

This is a Python-based Telegram bot that interacts with users on Telegram. The bot responds to user messages, mentions, and replies in private chats and groups. It integrates with the Eden API and supports sending both text messages and media as responses.

## Requirements
 - Python 3.8+
 - Eden API Client
 - Telegram Token

## Docker Setup
If you prefer to run the bot inside a Docker container, you can follow these steps:

 ### Build the Docker Image
 ```
docker build -f eve/clients/telegram/Dockerfile --build-arg ENV_FILE=eve/clients/telegram/.env -t eve-telegram .

 ```

### Run the Docker Container

After building the image, run the Docker container with the following command:

```
docker run --name eve-telegram eve-telegram


```

This command will start the bot inside the container, using the environment variables defined in the .env file.

Make sure the .env file contains the required TELEGRAM_TOKEN and EDEN_API_KEY for the bot to work correctly.

## Setup (Without Docker)

 If you don't want to use Docker, you can set up the bot  manually:

 1. Clone the repository
  ```
  git clone https://github.com/edenartlab/eve.git
  cd eve
  rye sync
  ```

 2. Running locally:

  ```
 rye sync --features "telegram"
 rye add python-telegram-bot==21.7
 rye run python eve/clients/telegram/client.py --env=./eve/clients/telegram/.env
 ```

## Usage
The bot responds to the following types of interactions:
 - Direct Messages (DMs): The bot responds to users in private conversations.
 - Mentions: If the bot is mentioned in a group chat, it responds accordingly.
 - Replies: If the bot is directly replied to in a group, it responds to the reply.



