import sys
sys.path.append("../..")
import os
import json
import requests
import instructor
from openai import OpenAI


NEWSAPI_API_KEY = os.environ['NEWSAPI_API_KEY']
print(NEWSAPI_API_KEY)

client = instructor.from_openai(OpenAI())


async def news(args: dict, user: str = None):
    category = args['subject']
    url = f'https://newsapi.org/v2/top-headlines?country=us&category={category}&apiKey={NEWSAPI_API_KEY}'

    response = requests.get(url)
    news = response.json()
    articles = [a for a in news['articles'] if a['title'] != "[Removed]"]

    headline = articles[0]
    print(json.dumps(articles, indent=2))
    
    print(json.dumps(headline, indent=2))

    print(headline['content'])

    news_summary = "# News Summary:\n\n"
    for article in articles:
        news_summary += f"Title: {article['title']}\nDescription: {article['description']}\n\n"

    print(news_summary)

    return [news_summary]
