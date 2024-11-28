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
docker build --no-cache -t telegram-bot .

 ```
 This will build the Docker image with the tag telegram-bot without using any cached layers.

### Run the Docker Container

After building the image, run the Docker container with the following command:

```
docker run --env-file .env telegram-bot

```

This command will start the bot inside the container, using the environment variables defined in the .env file.

Make sure the .env file contains the required TELEGRAM_TOKEN and EDEN_API_KEY for the bot to work correctly.

## Setup (Without Docker)

 If you don't want to use Docker, you can set up the bot  manually:

 1. Clone the repository

 2. Create a .env file
  Copy the .env.example file to .env and set your 
  TELEGRAM_TOKEN and EDEN_API_KEY in the .env file:

 3. Install dependencies:

  ```
  pip install -r requirements.txt

  ```

 4. Run the bot:
```
  python client.py
```
This will launch the bot and start polling for incoming messages.

## Usage
The bot responds to the following types of interactions:
 - Direct Messages (DMs): The bot responds to users in private conversations.
 - Mentions: If the bot is mentioned in a group chat, it responds accordingly.
 - Replies: If the bot is directly replied to in a group, it responds to the reply.



