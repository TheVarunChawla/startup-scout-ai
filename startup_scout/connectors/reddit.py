"""Reddit connector.

Uses Reddit's "Application Only OAuth" (client_credentials grant) for
read-only access to public subreddit listings - no user login or
password needed, just a free app registered at
https://www.reddit.com/prefs/apps.

Reads REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET from environment
variables (never from config.yaml) so credentials never end up in
version control. If either is missing, logs a warning and returns []
rather than failing the whole run - same pattern as Product Hunt.
"""
from __future__ import annotations

import logging
import os

import requests

from startup_scout.connectors.base import BaseConnector
from startup_scout.models import RawStartup

logger = logging.getLogger(__name__)

TOKEN_URL = "https://www.reddit.com/api/v1/access_token"
LISTING_URL_TEMPLATE = "https://oauth.reddit.com/r/{subreddit}/{listing}"
USER_AGENT = "startup-scout-ai/0.1 (personal use script)"

DEFAULT_SUBREDDITS = ["startups", "SideProject", "Entrepreneur"]


class RedditConnector(BaseConnector):
    name = "reddit_startups"

    def fetch(self) -> list[RawStartup]:
        client_id = os.environ.get("REDDIT_CLIENT_ID")
        client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
        if not client_id or not client_secret:
            logger.warning(
                "REDDIT_CLIENT_ID/REDDIT_CLIENT_SECRET not set - skipping Reddit. "
                "Create a free app at https://www.reddit.com/prefs/apps"
            )
            return []

        token = self._get_access_token(client_id, client_secret)
        if not token:
            return []

        subreddits = self.settings.get("subreddits", DEFAULT_SUBREDDITS)
        listing = self.settings.get("listing", "new")
        max_results = int(self.settings.get("max_results", 15))

        results: list[RawStartup] = []
        for subreddit in subreddits:
            results.extend(self._fetch_subreddit(subreddit, listing, token, max_results))
        return results

    def _get_access_token(self, client_id: str, client_secret: str) -> str | None:
        try:
            resp = requests.post(
                TOKEN_URL,
                data={"grant_type": "client_credentials"},
                auth=(client_id, client_secret),
                headers={"User-Agent": USER_AGENT},
                timeout=15,
            )
            resp.raise_for_status()
            return resp.json().get("access_token")
        except Exception:
            logger.exception("Reddit: failed to obtain access token")
            return None

    def _fetch_subreddit(self, subreddit: str, listing: str, token: str, limit: int) -> list[RawStartup]:
        url = LISTING_URL_TEMPLATE.format(subreddit=subreddit, listing=listing)
        try:
            resp = requests.get(
                url,
                params={"limit": limit},
                headers={"Authorization": f"Bearer {token}", "User-Agent": USER_AGENT},
                timeout=15,
            )
            resp.raise_for_status()
        except Exception:
            logger.exception("Reddit: failed to fetch r/%s", subreddit)
            return []

        children = resp.json().get("data", {}).get("children", [])
        results: list[RawStartup] = []
        for child in children:
            post = child.get("data", {})
            title = (post.get("title") or "").strip()
            if not title or post.get("stickied"):
                continue
            permalink = post.get("permalink", "")
            url_field = post.get("url") or f"https://reddit.com{permalink}"
            results.append(
                RawStartup(
                    source=self.name,
                    name=title,
                    url=url_field,
                    description=post.get("selftext") or title,
                    tags=["reddit", f"r/{subreddit}"],
                    raw_meta={
                        "score": post.get("score"),
                        "num_comments": post.get("num_comments"),
                        "author": post.get("author"),
                        "permalink": f"https://reddit.com{permalink}",
                    },
                )
            )
        return results
