import asyncio
from datetime import datetime

import yfinance as yf

from modules.retry_utils import run_with_exponential_backoff


async def _get_av_sentiment(symbol):
    """Fetch Alpha Vantage sentiment, non-blocking. Returns {} on failure."""
    try:
        from modules.alpha_vantage import AlphaVantageProvider, get_remaining_budget

        if get_remaining_budget() < 3:
            return {}

        av = AlphaVantageProvider()
        return await asyncio.to_thread(av.get_stock_sentiment, symbol)
    except Exception as exc:
        print(f"AV sentiment fetch skipped for {symbol}: {exc}")
        return {}


async def get_stock_news(symbol):
    """
    Fetch latest news for a stock symbol with Alpha Vantage sentiment enrichment.
    Yahoo provides the articles, AV provides sentiment scoring.
    """
    try:
        ticker = yf.Ticker(symbol)

        # Fetch Yahoo news and AV sentiment in parallel
        yahoo_task = run_with_exponential_backoff(
            lambda: asyncio.to_thread(lambda: ticker.news),
            context=f"yfinance news for {symbol}",
        )
        av_task = _get_av_sentiment(symbol)

        raw_news, sentiment_map = await asyncio.gather(yahoo_task, av_task)

        if not raw_news:
            return []

        # Extract aggregate symbol sentiment
        agg_sentiment = sentiment_map.get("__symbol__", {})

        processed_news = []
        for item in raw_news[:10]:
            content = item.get("content", item)
            title = content.get("title", "No Title")

            provider_data = content.get("provider", {})
            if isinstance(provider_data, dict):
                publisher = provider_data.get("displayName", "News")
            else:
                publisher = str(provider_data)

            link = (
                content.get("clickThroughUrl", {}).get("url")
                or content.get("canonicalUrl", {}).get("url")
                or content.get("link")
            )

            try:
                pub_date = content.get("pubDate")
                if pub_date:
                    dt = datetime.fromisoformat(pub_date.replace("Z", "+00:00"))
                    published_at = dt.strftime("%Y-%m-%d %H:%M")
                else:
                    ts = content.get("providerPublishTime", 0)
                    if ts > 0:
                        published_at = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M")
                    else:
                        published_at = "Recent"
            except Exception:
                published_at = "Recent"

            related_tickers = content.get("relatedTickers") or item.get("relatedTickers") or []

            # --- Sentiment Enrichment ---
            # Try exact title match first, then fall back to aggregate
            article_sentiment = sentiment_map.get(title, agg_sentiment)
            sentiment_score = article_sentiment.get("score")
            sentiment_label = article_sentiment.get("label")

            processed_news.append(
                {
                    "id": item.get("id"),
                    "title": title,
                    "publisher": publisher,
                    "link": link,
                    "published": published_at,
                    "related_tickers": related_tickers,
                    "sentiment_score": sentiment_score,
                    "sentiment_label": sentiment_label,
                }
            )

        return processed_news
    except Exception as exc:
        print(f"Error fetching news for {symbol}: {exc}")
        return []
