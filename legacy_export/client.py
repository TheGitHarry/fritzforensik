"""HTTP-Session-Wrapper mit SID-Verwaltung."""
from __future__ import annotations

from dataclasses import dataclass

import requests

from . import auth


@dataclass
class FritzClient:
    base_url: str
    sid: str
    session: requests.Session

    @classmethod
    def login(cls, host: str, username: str, password: str) -> "FritzClient":
        base_url = host if host.startswith(("http://", "https://")) else f"http://{host}"
        base_url = base_url.rstrip("/")
        session = requests.Session()
        result = auth.login(base_url, username, password, session)
        return cls(base_url=base_url, sid=result.sid, session=session)

    def get(self, path: str, **kwargs) -> requests.Response:
        params = dict(kwargs.pop("params", {}) or {})
        params["sid"] = self.sid
        return self.session.get(self.base_url + path, params=params, timeout=30, **kwargs)

    def post(self, path: str, data: dict | None = None, **kwargs) -> requests.Response:
        payload = dict(data or {})
        payload["sid"] = self.sid
        return self.session.post(self.base_url + path, data=payload, timeout=30, **kwargs)

    def close(self) -> None:
        auth.logout(self.base_url, self.sid, self.session)
        self.session.close()

    def __enter__(self) -> "FritzClient":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()
