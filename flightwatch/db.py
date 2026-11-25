"""Tiny client for Cloudflare D1's HTTP query API."""
import os

import httpx


class D1:
    def __init__(self, account_id=None, database_id=None, api_token=None):
        # .strip() because secrets pasted on a phone often pick up a trailing newline
        self.account_id = (account_id or os.environ["CF_ACCOUNT_ID"]).strip()
        self.database_id = (database_id or os.environ["D1_DATABASE_ID"]).strip()
        self.api_token = (api_token or os.environ["CF_API_TOKEN"]).strip()
        self.url = (
            f"https://api.cloudflare.com/client/v4/accounts/{self.account_id}"
            f"/d1/database/{self.database_id}/query"
        )
        self.http = httpx.Client(
            headers={"Authorization": f"Bearer {self.api_token}"}, timeout=30
        )

    def query(self, sql, params=None):
        """Run one statement and return its rows as dicts."""
        body = {"sql": sql, "params": [p for p in (params or [])]}
        r = self.http.post(self.url, json=body)
        data = r.json()
        if not data.get("success"):
            raise RuntimeError(f"D1 query failed: {data.get('errors')} for: {sql}")
        return data["result"][0].get("results", [])

    def execute(self, sql, params=None):
        self.query(sql, params)
