import os
import argparse
import re
import time
import logging
import requests
from dotenv import load_dotenv
from requests_oauthlib import OAuth1Session
# from eve.sdk.eden import EdenClient

from dotenv import load_dotenv
load_dotenv("eve/agents/abraham/.env")


class X:
    def __init__(self):
        """Initializes an X/Twitter session."""
        
        self._load_env_vars()
        self.last_processed_id = None
        self.oauth = self._init_oauth_session()

    def _load_env_vars(self):
        """Loads environment variables."""
        
        self.user_id = os.getenv("CLIENT_TWITTER_USER_ID")
        self.bearer_token = os.getenv("CLIENT_TWITTER_BEARER_TOKEN")
        self.consumer_key = os.getenv("CLIENT_TWITTER_CONSUMER_KEY")
        self.consumer_secret = os.getenv("CLIENT_TWITTER_CONSUMER_SECRET")
        self.access_token = os.getenv("CLIENT_TWITTER_ACCESS_TOKEN")
        self.access_token_secret = os.getenv("CLIENT_TWITTER_ACCESS_TOKEN_SECRET")

    def _init_oauth_session(self):
        """Initializes OAuth1 session."""
        
        return OAuth1Session(
            self.consumer_key,
            client_secret=self.consumer_secret,
            resource_owner_key=self.access_token,
            resource_owner_secret=self.access_token_secret
        )

    def _make_request(self, method, url, **kwargs):
        """Generic request handler with error handling and retries."""
        try:
            if method.lower() == 'get':
                response = requests.get(url, **kwargs)
            else:
                response = self.oauth.post(url, **kwargs)
            
            response.raise_for_status()
            return response
        except requests.exceptions.HTTPError as e:
            if response.status_code == 429:
                logging.error("Rate limit exceeded. Sleeping for 15 minutes before retrying...")
                time.sleep(900)
                return self._make_request(method, url, **kwargs)
            logging.error(f"HTTP error occurred: {e}")
        except requests.RequestException as e:
            logging.error(f"Request failed: {e}")
        return None

    def fetch_mentions(self):
        """Fetches the latest mentions of the user."""
        params = {
            "expansions": "author_id",
            "user.fields": "username",
            "max_results": 5
        }
        if self.last_processed_id:
            params["since_id"] = self.last_processed_id


        print("ok", self.user_id)
        response = self._make_request(
            'get',
            f"https://api.twitter.com/2/users/{self.user_id}/mentions",
            headers={"Authorization": f"Bearer {self.bearer_token}"},
            params=params
        )
        return response.json() if response else {}

    def get_newest_tweet(self, data):
        """Gets the newest tweet from the data."""
        
        tweets = [tweet for tweet in data.get("data", []) if tweet["author_id"] != self.user_id]
        return max(tweets, key=lambda tweet: tweet["id"]) if tweets else None

    def tweet_media(self, media_url):
        """Uploads media to Twitter and returns the media ID."""
        image_response = self._make_request('get', media_url)
        if not image_response:
            return None

        upload_response = self._make_request(
            'post',
            "https://upload.twitter.com/1.1/media/upload.json",
            files={"media": image_response.content}
        )
        return upload_response.json().get("media_id_string") if upload_response else None

    def reply_to_tweet(self, tweet_text, tweet_id):
        """Replies to a tweet with media content."""
        media_url = "https://res.cloudinary.com/prdg34ew78adsg/image/upload/v1732713849/creations/h8oh82rzapnnile2yjms.jpg"
        media_id = self.tweet_media(media_url)
        
        if not media_id:
            logging.error("Media upload was unsuccessful. Cannot reply with media.")
            return

        response = self._make_request(
            'post',
            "https://api.twitter.com/2/tweets",
            json={
                "text": tweet_text,
                "media": {"media_ids": [media_id]},
                "reply": {"in_reply_to_tweet_id": tweet_id},
            }
        )
        if response:
            logging.info("Reply tweet sent successfully")

    def post_tweet(self, tweet_text, media_url=None):
        """Posts a tweet with or without media content."""
        media_id = self.tweet_media(media_url) if media_url else None
        
        if media_url and not media_id:
            logging.error("Media upload was unsuccessful. Cannot post tweet with media.")
            return

        response = self._make_request(
            'post',
            "https://api.twitter.com/2/tweets",
            json={
                "text": tweet_text,
                "media": {"media_ids": [media_id]} if media_id else None,
            }
        )
        if response:
            logging.info("Tweet sent successfully")


X_client = X()