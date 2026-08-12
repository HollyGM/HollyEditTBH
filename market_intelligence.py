from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import html as html_lib
import json
import os
from pathlib import Path
import re
import time
from typing import Mapping
from urllib.parse import unquote
import urllib.request

STEAM_APP_ID = 3678970
STEAM_MARKET_SEARCH = "https://steamcommunity.com/market/search/"
BASE_LISTING_SLOTS = 4
LISTING_COOLDOWN_HOURS = 8
LOW_GRADE_GEAR_BLOCKED = {"COMMON", "UNCOMMON", "RARE"}
HIGH_GRADE_GEAR_BLOCKED = {"CELESTIAL", "DIVINE", "COSMIC"}
POLICY_CHECKED_AT = "2026-07-06"
SNAPSHOT_TTL_SECONDS = 6 * 60 * 60


@dataclass(frozen=True)
class MarketQuote:
    hash_name: str
    sell_listings: int
    price_text: str
    price_value: float
    listing_url: str


@dataclass
class MarketSnapshot:
    captured_at: float
    quotes: list[MarketQuote]
    complete: bool
    total_reported: int | None
    source: str = "steam_community_market"

    def is_fresh(self, ttl_seconds: int = SNAPSHOT_TTL_SECONDS) -> bool:
        return time.time() - self.captured_at <= ttl_seconds


@dataclass(frozen=True)
class MarketEligibility:
    allowed: bool
    reason: str
    policy_checked_at: str = POLICY_CHECKED_AT


def normalize_market_text(value: object) -> str:
    text = html_lib.unescape(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip().casefold()
    text = re.sub(r"[^0-9a-zà-ÿ]+", " ", text)
    return " ".join(text.split())


def market_eligibility(item_type: str, rarity: str, *, is_soulstone: bool = False) -> MarketEligibility:
    kind = str(item_type or "").upper()
    grade = str(rarity or "").upper()
    if kind == "GEAR" and grade in LOW_GRADE_GEAR_BLOCKED:
        return MarketEligibility(False, f"equipamento {grade} ou inferior não é elegível pela política conhecida")
    if kind == "GEAR" and grade in HIGH_GRADE_GEAR_BLOCKED and not is_soulstone:
        return MarketEligibility(False, f"equipamento {grade} permanece bloqueado pela última política oficial confirmada")
    return MarketEligibility(True, "pré-candidato; a confirmação final continua sendo feita pelo Navio de Trocas")


def _strip_tags(value: str) -> str:
    value = re.sub(r"<script\b.*?</script>", "", value, flags=re.I | re.S)
    value = re.sub(r"<style\b.*?</style>", "", value, flags=re.I | re.S)
    return html_lib.unescape(re.sub(r"<[^>]+>", "", value)).strip()


def _parse_number(text: str) -> float:
    value = re.sub(r"[^0-9,.\-]", "", text or "")
    if not value:
        return 0.0
    last_comma = value.rfind(",")
    last_dot = value.rfind(".")
    decimal = None
    if last_comma >= 0 or last_dot >= 0:
        candidate = "," if last_comma > last_dot else "."
        pos = value.rfind(candidate)
        if len(value) - pos - 1 in (1, 2):
            decimal = candidate
    if decimal:
        other = "." if decimal == "," else ","
        value = value.replace(other, "").replace(decimal, ".")
    else:
        value = value.replace(",", "").replace(".", "")
    try:
        return max(0.0, float(value))
    except ValueError:
        return 0.0


def parse_market_search_html(page_html: str) -> tuple[list[MarketQuote], int | None]:
    total_match = re.search(r"Found\s+([\d,.]+)\s+results", page_html, flags=re.I)
    total_reported = None
    if total_match:
        digits = re.sub(r"\D", "", total_match.group(1))
        total_reported = int(digits) if digits else None

    anchor_pattern = re.compile(
        r'<a[^>]+class="[^"]*market_listing_row_link[^"]*"[^>]+href="([^"]+)"[^>]*>(.*?)</a>',
        flags=re.I | re.S,
    )
    quotes: list[MarketQuote] = []
    seen: set[str] = set()
    for href, block in anchor_pattern.findall(page_html):
        name_match = re.search(r'class="[^"]*market_listing_item_name[^"]*"[^>]*>(.*?)</span>', block, flags=re.I | re.S)
        qty_match = re.search(r'class="[^"]*market_listing_num_listings_qty[^"]*"[^>]*>(.*?)</span>', block, flags=re.I | re.S)
        price_match = re.search(r'class="[^"]*(?:market_listing_price_with_fee|normal_price)[^"]*"[^>]*>(.*?)</span>', block, flags=re.I | re.S)
        if not name_match:
            path_match = re.search(r"/market/listings/\d+/(.+?)(?:\?|$)", href)
            name = unquote(path_match.group(1)) if path_match else ""
        else:
            name = _strip_tags(name_match.group(1))
        normalized_name = normalize_market_text(name)
        if not name or normalized_name in seen:
            continue
        seen.add(normalized_name)
        qty_text = _strip_tags(qty_match.group(1)) if qty_match else "0"
        qty_digits = re.sub(r"\D", "", qty_text)
        quantity = int(qty_digits) if qty_digits else 0
        price_text = _strip_tags(price_match.group(1)) if price_match else ""
        quotes.append(MarketQuote(name, quantity, price_text, _parse_number(price_text), html_lib.unescape(href)))
    return quotes, total_reported


def _snapshot_to_json(snapshot: MarketSnapshot) -> dict:
    return {
        "captured_at": snapshot.captured_at,
        "captured_at_iso": datetime.fromtimestamp(snapshot.captured_at, tz=timezone.utc).isoformat(),
        "complete": snapshot.complete,
        "total_reported": snapshot.total_reported,
        "source": snapshot.source,
        "quotes": [asdict(quote) for quote in snapshot.quotes],
    }


def _snapshot_from_json(raw: Mapping) -> MarketSnapshot:
    return MarketSnapshot(
        captured_at=float(raw.get("captured_at") or 0),
        complete=bool(raw.get("complete")),
        total_reported=int(raw["total_reported"]) if raw.get("total_reported") is not None else None,
        source=str(raw.get("source") or "steam_community_market"),
        quotes=[
            MarketQuote(
                hash_name=str(row.get("hash_name") or ""),
                sell_listings=max(0, int(row.get("sell_listings") or 0)),
                price_text=str(row.get("price_text") or ""),
                price_value=max(0.0, float(row.get("price_value") or 0.0)),
                listing_url=str(row.get("listing_url") or ""),
            )
            for row in raw.get("quotes", [])
            if isinstance(row, Mapping) and row.get("hash_name")
        ],
    )


def load_market_snapshot(path: Path) -> MarketSnapshot | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
        return _snapshot_from_json(raw) if isinstance(raw, Mapping) else None
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return None


def save_market_snapshot(path: Path, snapshot: MarketSnapshot) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    try:
        temp.write_text(json.dumps(_snapshot_to_json(snapshot), ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()


def fetch_market_snapshot(
    cache_path: Path,
    *,
    force: bool = False,
    ttl_seconds: int = SNAPSHOT_TTL_SECONDS,
    max_pages: int = 12,
    page_size: int = 100,
    timeout: int = 15,
) -> MarketSnapshot:
    """Bounded public Steam Market refresh; never logs in or bypasses throttling."""
    cached = load_market_snapshot(cache_path)
    if cached and cached.is_fresh(ttl_seconds) and not force:
        return cached

    all_quotes: dict[str, MarketQuote] = {}
    total_reported: int | None = None
    complete = False
    try:
        for page in range(max(1, min(max_pages, 20))):
            start = page * page_size
            url = f"{STEAM_MARKET_SEARCH}?appid={STEAM_APP_ID}&start={start}&count={page_size}&sort_column=popular&sort_dir=desc"
            req = urllib.request.Request(
                url,
                headers={
                    "User-Agent": "HollyEditTBH/3.x (+public Steam Community Market snapshot)",
                    "Accept-Language": "en-US,en;q=0.8",
                },
            )
            with urllib.request.urlopen(req, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")
            rows, reported = parse_market_search_html(body)
            if reported is not None:
                total_reported = reported
            if not rows:
                complete = page > 0
                break
            for quote in rows:
                all_quotes[normalize_market_text(quote.hash_name)] = quote
            if len(rows) < page_size or (total_reported is not None and len(all_quotes) >= total_reported):
                complete = True
                break
            time.sleep(0.65)
    except Exception:
        if cached:
            return cached
        raise

    snapshot = MarketSnapshot(time.time(), list(all_quotes.values()), complete, total_reported)
    if not snapshot.quotes:
        if cached:
            return cached
        raise ValueError("Steam Market respondeu sem itens reconhecíveis")
    save_market_snapshot(cache_path, snapshot)
    return snapshot


def quote_for_item(snapshot: MarketSnapshot | None, item_name: str, rarity: str) -> MarketQuote | None:
    if not snapshot:
        return None
    base = normalize_market_text(item_name)
    grade = normalize_market_text(rarity)
    if not base:
        return None
    candidates: list[tuple[int, MarketQuote]] = []
    for quote in snapshot.quotes:
        normalized = normalize_market_text(quote.hash_name)
        if base not in normalized:
            continue
        score = (2 if normalized.startswith(base) else 0) + (2 if grade and grade in normalized else 0)
        candidates.append((score, quote))
    if not candidates:
        return None
    best_score = max(score for score, _quote in candidates)
    best = [quote for score, quote in candidates if score == best_score]
    return best[0] if len(best) == 1 else None


def market_priority(quote: MarketQuote | None, *, rarity_rank: int, item_type: str, has_enchantments: bool) -> tuple[float, ...]:
    """Ranking signal, not a sale-price promise. Enchantments never increase sale priority."""
    if quote:
        return (
            1.0,
            float(quote.price_value),
            float(min(quote.sell_listings, 10_000)),
            1.0 if str(item_type).upper() == "MATERIAL" else 0.0,
            -1.0 if has_enchantments else 0.0,
            float(rarity_rank),
        )
    return (
        0.0,
        0.0,
        0.0,
        1.0 if str(item_type).upper() == "MATERIAL" else 0.0,
        -1.0 if has_enchantments else 0.0,
        float(rarity_rank),
    )
