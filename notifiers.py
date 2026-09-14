"""Troque a implementacao mantendo send(title, message) -> None."""
import os
from typing import Protocol
import requests


class Notifier(Protocol):
    def send(self, title: str, message: str) -> None: ...


class Pushover:
    def __init__(self):
        self.token = os.environ.get("PUSHOVER_APP_TOKEN")
        self.user = os.environ.get("PUSHOVER_USER_KEY")
        if not self.token or not self.user:
            raise ValueError("Configure PUSHOVER_APP_TOKEN e PUSHOVER_USER_KEY")

    def send(self, title, message):
        response = requests.post(
            "https://api.pushover.net/1/messages.json",
            data={"token": self.token, "user": self.user,
                  "title": title, "message": message}, timeout=30,
        )
        response.raise_for_status()
        if response.json().get("status") != 1:
            raise RuntimeError("Pushover nao confirmou o recebimento")
