# Twitter-client

This is  Twitter bot designed to automatically reply to mentions on Twitter. The bot uses Twitter's API to fetch mentions and respond to the tweets mentioning the bot's account.


## Docker Setup
If you prefer to run the bot inside a Docker container, you can follow these steps:

 ### Build the Docker Image
 ```
docker build -f eve/clients/twitter/Dockerfile --build-arg ENV_FILE=eve/clients/twitter/.env -t eve-twitter .

 ```

### Run the Docker Container

After building the image, run the Docker container with the following command:

```
docker run --name eve-twitter eve-twitter


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
 rye sync --features "twitter"
 rye add requests_oauthlib==2.0.0
 rye run python eve/clients/twitter/client.py --env=./eve/clients/twitter/.env
 ```
