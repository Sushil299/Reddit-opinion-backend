# -*- coding: utf-8 -*-
"""Backend

Automatically generated by Colab.

Original file is located at
    https://colab.research.google.com/drive/12kIA47N7HFmmNa2LvqkQejdrhWG9iCZG
"""

import asyncpraw
import pandas as pd
from datetime import datetime, timedelta
import re
import asyncio
import nest_asyncio
import requests
import os
from fastapi import FastAPI
from google.generativeai import configure, GenerativeModel

nest_asyncio.apply()

# Load API keys from environment variables
REDDIT_CLIENT_ID = os.getenv("REDDIT_CLIENT_ID")
REDDIT_CLIENT_SECRET = os.getenv("REDDIT_CLIENT_SECRET")
NEWS_API_KEY = os.getenv("NEWS_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Configurable time period for fetching posts (in days)
DAYS_BACK = 120  # Change this value to adjust the time range

# Minimum engagement thresholds
Num_Posts = 50 #Number of Posts to be scraped - Lower number since using paid version
MIN_UPVOTES = 100
MIN_COMMENTS = 10
MIN_COMMENT_UPVOTES = 20
MIN_COMMENT_LENGTH = 30

# Initialize asyncpraw client
reddit = asyncpraw.Reddit(
    client_id=REDDIT_CLIENT_ID,
    client_secret=REDDIT_CLIENT_SECRET,
    user_agent="StockScraper"
)

# Configure Gemini Flash API
configure(api_key=GEMINI_API_KEY)
gemini_model = GenerativeModel("gemini-1.5-flash")

# FastAPI app instance
app = FastAPI()

# Relevant Stock Market Subreddits
subreddits = ["IndianStockMarket", "DalalStreetTalks", "StockMarketIndia", "IndianStreetBets", "NSEBets", "ShareMarketupdates"]

# Keywords to filter out low-effort posts
low_effort_keywords = ["meme", "joke", "funny", "shitpost", "lol", "haha", "troll"]

# Define time threshold
days_ago = datetime.utcnow() - timedelta(days=DAYS_BACK)

# Function to clean text
def clean_text(text):
    text = re.sub(r'\s+', ' ', text).strip()  # Remove extra spaces and newlines
    return text

# Function to fetch stock-related news using NewsAPI
def fetch_news(stock_ticker):
    url = f"https://newsapi.org/v2/everything?q={stock_ticker}&sortBy=publishedAt&apiKey={NEWS_API_KEY}"
    response = requests.get(url)

    if response.status_code == 200:
        news_data = response.json()
        articles = news_data.get("articles", [])

        combined_text = " ".join([clean_text(article["title"] + " " + (article["description"] or "") + " " + (article["content"] or "")) for article in articles[:10]])
        return combined_text
    else:
        return ""

# Function to analyze sentiment & summarize using Gemini Flash 1.5
def analyze_sentiment_and_summarize(text, stock_name):
    try:
        trimmed_text = text[:8000]  # Increase input limit for more detailed summaries
        prompt = (f"The broader discussion related to {stock_name} should be summarized with a focus on key trends, opinions, and risks. "
                  "Make sure to analyze posts and comments together for a more informed perspective. "
                  "If there is no relevant discussion specifically about {stock_name}, then summarize the discussions about its peer companies or industry trends. "
                  "If no such discussions exist, clearly state that this stock is not widely discussed, and no insights are available.")
        response = gemini_model.generate_content(f"{prompt} {trimmed_text}")
        return response.text if response and hasattr(response, 'text') else "No response from Gemini."
    except Exception as e:
        return f"Error in sentiment analysis: {str(e)}"

# Function to fetch relevant Reddit discussions asynchronously
async def fetch_reddit_posts(stock_name):
    posts = []
    for subreddit in subreddits:
        sub = await reddit.subreddit(subreddit)
        async for submission in sub.search(stock_name, limit=Num_Posts, time_filter="month"):
            if (submission.score >= MIN_UPVOTES and submission.num_comments >= MIN_COMMENTS and
                not any(keyword in submission.title.lower() for keyword in low_effort_keywords)):

                comments = []
                submission.comment_sort = 'top'
                await submission.load()
                for comment in submission.comments:
                    if hasattr(comment, "body") and len(comment.body) >= MIN_COMMENT_LENGTH and comment.score >= MIN_COMMENT_UPVOTES:
                        comments.append(clean_text(comment.body))

                post_details = {
                    "title": clean_text(submission.title),
                    "content": clean_text(submission.selftext),
                    "comments": " ".join(comments),
                    "upvotes": submission.score,
                    "num_comments": submission.num_comments,
                    "url": submission.url
                }
                posts.append(post_details)
    return posts

# Function to analyze Reddit discussions combined
def analyze_combined_reddit_discussions(posts, stock_name):
    combined_text = " ".join([post["title"] + " " + post["content"] + " " + post["comments"] for post in posts])
    summary = analyze_sentiment_and_summarize(combined_text, stock_name)
    return f"## Reddit Discussion Summary\n\n**{summary}**\n"

# Function to analyze combined news articles
def analyze_combined_news_articles(news_text, stock_name):
    summary = analyze_sentiment_and_summarize(news_text, stock_name)
    return f"## News Summary\n\n**{summary}**\n"

@app.get("/analyze_stock/{stock_name}")
async def analyze_stock(stock_name: str):
    reddit_posts = await fetch_reddit_posts(stock_name)
    news_text = fetch_news(stock_name)

    reddit_summary = analyze_combined_reddit_discussions(reddit_posts, stock_name)
    news_summary = analyze_combined_news_articles(news_text, stock_name)

    return {"reddit_summary": reddit_summary, "news_summary": news_summary}

@app.get("/health")
def health_check():
    return {"status": "API is running"}