"""Current company headlines, independent of the trading-session replay clock."""
import asyncio
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
import json
import logging
import os
from urllib.parse import urlencode, urlsplit
from urllib.request import Request as URLRequest, urlopen
from xml.etree import ElementTree

from fastapi import APIRouter, Request, WebSocket, WebSocketDisconnect
from websockets.asyncio.client import connect

router = APIRouter(prefix="/api/v1/news", tags=["news"])
log = logging.getLogger(__name__)
QUERIES = {
    "AAPL": '"Apple" (stock OR earnings OR shares)',
    "MSFT": '"Microsoft" (stock OR earnings OR shares)',
    "INTC": '"Intel" (stock OR earnings OR shares)',
    "CSCO": '"Cisco" (stock OR earnings OR shares)',
    "CMCSA": '"Comcast" (stock OR earnings OR shares)',
    "FOXA": '("Fox Corporation" OR "FOXA") (stock OR earnings OR shares)',
}
INTERVAL = 60


def now():
    return datetime.now(timezone.utc)


def article(title, url, published, source, symbols):
    parts = urlsplit(url)
    if not title or not symbols or parts.scheme != "https" or not parts.hostname:
        return None
    if published.tzinfo is None or not now() - timedelta(days=7) <= published <= now() + timedelta(minutes=5):
        return None
    return dict(title=title, url=url, published=published.astimezone(timezone.utc).isoformat(),
                source=source, symbols=sorted(symbols))


def fetch_rss(symbol, query):
    params = urlencode(dict(q=query + " when:7d", hl="en-US", gl="US", ceid="US:en"))
    request = URLRequest("https://news.google.com/rss/search?" + params, headers={"User-Agent": "NevAI/1.0"})
    with urlopen(request, timeout=10) as response:
        root = ElementTree.fromstring(response.read(2_000_000))
    if root.find("channel") is None:
        raise ValueError("Invalid RSS response")
    results = []
    for node in root.findall("./channel/item"):
        source = node.findtext("source") or "Google News"
        title = (node.findtext("title") or "").removesuffix(" - " + source).strip()
        try:
            item = article(title, node.findtext("link") or "", parsedate_to_datetime(node.findtext("pubDate") or ""), source, [symbol])
        except (TypeError, ValueError, OverflowError):
            continue
        if item:
            results.append(item)
    return sorted(results, key=lambda item: item["published"], reverse=True)[:12]


class NewsFeed:
    def __init__(self):
        self.feeds = {}
        self.stream_items = {}
        self.checked = None
        self.failed = []
        self.stream = "off"
        self.revision = 0
        self.changed = asyncio.Condition()
        self.tasks = []

    def start(self):
        if not self.tasks:
            self.tasks.append(asyncio.create_task(self.poll()))
            if os.getenv("APCA_API_KEY_ID") and os.getenv("APCA_API_SECRET_KEY"):
                self.stream = "connecting"
                self.tasks.append(asyncio.create_task(self.listen()))

    async def stop(self):
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)

    async def notify(self):
        async with self.changed:
            self.revision += 1
            self.changed.notify_all()

    async def poll(self):
        while True:
            results = await asyncio.gather(*(asyncio.to_thread(fetch_rss, s, q) for s, q in QUERIES.items()), return_exceptions=True)
            self.failed = []
            for symbol, result in zip(QUERIES, results):
                if isinstance(result, Exception):
                    self.failed.append(symbol)
                    log.warning("RSS %s: %s", symbol, type(result).__name__)
                else:
                    self.feeds[symbol] = result
            self.checked = now().isoformat()
            await self.notify()
            await asyncio.sleep(INTERVAL)

    async def listen(self):
        delay = 2
        headers = {"APCA-API-KEY-ID": os.environ["APCA_API_KEY_ID"],
                   "APCA-API-SECRET-KEY": os.environ["APCA_API_SECRET_KEY"]}
        while True:
            try:
                async with connect("wss://stream.data.alpaca.markets/v1beta1/news", additional_headers=headers) as socket:
                    async for raw in socket:
                        for msg in json.loads(raw):
                            kind = msg.get("T")
                            if kind == "error":
                                raise ValueError("Provider rejected subscription")
                            if kind == "success" and msg.get("msg") == "authenticated":
                                await socket.send(json.dumps({"action": "subscribe", "news": list(QUERIES)}))
                            elif kind == "subscription" and msg.get("news"):
                                self.stream = "live"
                                delay = 2
                                await self.notify()
                            elif kind == "n":
                                symbols = QUERIES.keys() & set(msg.get("symbols") or [])
                                item = article(msg.get("headline"), msg.get("url") or "",
                                               datetime.fromisoformat(msg["created_at"]), msg.get("source") or "Alpaca", symbols)
                                if item:
                                    self.stream_items.pop(msg["id"], None)
                                    self.stream_items[msg["id"]] = item
                                    if len(self.stream_items) > 120:
                                        del self.stream_items[next(iter(self.stream_items))]
                                    await self.notify()
            except (OSError, ValueError, KeyError, TimeoutError) as error:
                log.warning("News stream unavailable: %s", type(error).__name__)
            except Exception as error:
                log.warning("News stream disconnected: %s", type(error).__name__)
            self.stream = "retrying"
            await self.notify()
            await asyncio.sleep(delay)
            delay = min(120, delay * 2)

    def snapshot(self):
        combined = {}
        cutoff = (now() - timedelta(days=7)).isoformat()
        for group in [*self.feeds.values(), self.stream_items.values()]:
            for item in group:
                if item["published"] < cutoff:
                    continue
                key = (item["title"].casefold(), item["source"].casefold())
                if key in combined:
                    combined[key]["symbols"] = sorted(set(combined[key]["symbols"]) | set(item["symbols"]))
                else:
                    combined[key] = dict(item)
        return dict(items=sorted(combined.values(), key=lambda i: i["published"], reverse=True),
                    checked=self.checked, failed=self.failed, stream=self.stream, revision=self.revision)


@router.get("")
async def headlines(request: Request):
    feed = request.app.state.news
    feed.start()
    return feed.snapshot()


@router.websocket("/stream")
async def updates(socket: WebSocket):
    await socket.accept()
    feed = socket.app.state.news
    feed.start()
    try:
        while True:
            data = feed.snapshot()
            await socket.send_json(data)
            async with feed.changed:
                try:
                    await asyncio.wait_for(feed.changed.wait_for(lambda: feed.revision != data["revision"]), timeout=20)
                except TimeoutError:
                    pass
    except (WebSocketDisconnect, OSError):
        return
