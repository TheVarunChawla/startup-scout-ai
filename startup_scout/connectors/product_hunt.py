"""Product Hunt connector.

Product Hunt's v2 API is GraphQL and requires an OAuth developer token
(free to obtain at https://api.producthunt.com/v2/docs). We read the
token from the PRODUCT_HUNT_TOKEN environment variable rather than
config.yaml, so credentials never end up in version control.

If no token is configured, this connector logs a warning and returns an
empty list rather than failing the whole run - see BaseConnector.safe_fetch.
"""
from __future__ import annotations

import logging
import os

import requests

from startup_scout.connectors.base import BaseConnector
from startup_scout.models import RawStartup

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://api.producthunt.com/v2/api/graphql"

QUERY = """
query TodayPosts($first: Int!) {
  posts(order: RANKING, first: $first) {
    edges {
      node {
        id
        name
        tagline
        description
        url
        website
        votesCount
        topics {
          edges { node { name } }
        }
      }
    }
  }
}
"""


class ProductHuntConnector(BaseConnector):
    name = "product_hunt"

    def fetch(self) -> list[RawStartup]:
        token = os.environ.get("PRODUCT_HUNT_TOKEN")
        if not token:
            logger.warning(
                "PRODUCT_HUNT_TOKEN not set - skipping Product Hunt. "
                "Get a token at https://api.producthunt.com/v2/docs"
            )
            return []

        max_results = int(self.settings.get("max_results", 20))
        headers = {"Authorization": f"Bearer {token}"}
        resp = requests.post(
            GRAPHQL_URL,
            json={"query": QUERY, "variables": {"first": max_results}},
            headers=headers,
            timeout=15,
        )
        resp.raise_for_status()
        payload = resp.json()
        edges = payload.get("data", {}).get("posts", {}).get("edges", [])

        results: list[RawStartup] = []
        for edge in edges:
            node = edge.get("node", {})
            name = (node.get("name") or "").strip()
            if not name:
                continue
            topics = [
                t["node"]["name"]
                for t in node.get("topics", {}).get("edges", [])
                if t.get("node", {}).get("name")
            ]
            results.append(
                RawStartup(
                    source=self.name,
                    name=name,
                    url=node.get("website") or node.get("url") or "",
                    description=node.get("description") or node.get("tagline") or "",
                    tags=["product-hunt"] + topics,
                    raw_meta={
                        "votes": node.get("votesCount"),
                        "ph_id": node.get("id"),
                    },
                )
            )
        return results
