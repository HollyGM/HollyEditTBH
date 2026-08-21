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

from app_meta import APP_VERSION
from market_policy import (
    BASE_LISTING_SLOTS,
    CUBE_MARKET_UNLOCK_LEVEL,
    HIGH_GRADE_GEAR_BLOCKED,
    LOW_GRADE_GEAR_BLOCKED,
    POLICY_CHECKED_AT,
    STEAM_APP_ID,
    MarketEligibility,
    market_eligibility,
    trade_ship_status,
)

STEAM_MARKET_SEARCH = "https://steamcommunity.com/market/search/"
LISTING_COOLDOWN_HOURS = 8
SNAPSHOT_TTL_SECONDS = 6 * 60 * 60
MARKET_USER_AGENT = f"HollyEditTBH/{APP_VERSION} (+public Steam Community Market snapshot)"

__all__ = [
    "BASE_LISTING_SLOTS", "CUBE_MARKET_UNLOCK_LEVEL", "HIGH_GRADE_GEAR_BLOCKED",
    "LOW_GRADE_GEAR_BLOCKED", "POLICY_CHECKED_AT", "STEAM_APP_ID", "STEAM_MARKET_SEARCH",
    "MARKET_USER_AGENT", "SNAPSHOT_TTL_SECONDS", "LISTING_COOLDOWN_HOURS",
    "MarketEligibility", "MarketQuote", "MarketSnapshot", "market_eligibility",
    "trade_ship_status", "normalize_market_text", "parse_market_search_html",
    "load_market_snapshot", "save_market_snapshot", "fetch_market_snapshot",
    "prefer_snapshot", "quote_for_item", "market_priority",
]


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


def normalize_market_text(value: object) -> str:
    text = html_lib.unescape(str(value or ""))
    text = re.sub(r"\s+", " ", text).strip().casefold()
    text = re.sub(r"[^0-9a-zà-ÿ]+", " ", text)
    return " ".join(text.split())


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


def prefer_snapshot(cached: MarketSnapshot | None, candidate: MarketSnapshot) -> MarketSnapshot:
    """Preserva a fonte mais confiável quando a nova coleta parece truncada.

    Um snapshot completo já armazenado sempre prevalece sobre uma coleta nova
    incompleta. Entre dois snapshots incompletos, usa-se temporariamente o que
    contém mais cotações, sem persistir a resposta parcial sobre o cache.
    """
    if candidate.complete:
        return candidate
    if cached and cached.complete:
        return cached
    if cached and len(cached.quotes) >= len(candidate.quotes):
        return cached
    return candidate


def fetch_market_snapshot(
    cache_path: Path,
    *,
    force: bool = False,
    ttl_seconds: int = SNAPSHOT_TTL_SECONDS,
    max_pages: int = 12,
    page_size: int = 100,
    timeout: int = 15,
) -> MarketSnapshot:
    """Coleta pública e limitada do Steam Market, sem degradar um cache válido.

    Nunca faz login, não usa cookies e respeita um intervalo entre páginas. Um
    cache completo anterior prevalece sobre uma coleta nova truncada; uma
    resposta parcial só é gravada quando não existe cache algum, para que a
    próxima abertura do editor não repita as doze páginas do zero.
    """
    cached = load_market_snapshot(cache_path)
    if cached and cached.is_fresh(ttl_seconds) and not force:
        return cached

    all_quotes: dict[str, MarketQuote] = {}
    total_reported: int | None = None
    complete = False

    try:
        for page in range(max(1, min(max_pages, 20))):
            start = page * page_size
            url = (
                f"{STEAM_MARKET_SEARCH}?appid={STEAM_APP_ID}&start={start}"
                f"&count={page_size}&sort_column=popular&sort_dir=desc"
            )
            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": MARKET_USER_AGENT,
                    "Accept-Language": "en-US,en;q=0.8",
                },
            )
            with urllib.request.urlopen(request, timeout=timeout) as response:
                body = response.read().decode("utf-8", errors="replace")

            rows, reported = parse_market_search_html(body)
            if reported is not None:
                total_reported = reported

            if not rows:
                complete = total_reported is not None and len(all_quotes) >= total_reported
                break

            for quote in rows:
                all_quotes[normalize_market_text(quote.hash_name)] = quote

            if total_reported is not None and len(all_quotes) >= total_reported:
                complete = True
                break
            if len(rows) < page_size:
                complete = total_reported is None or len(all_quotes) >= total_reported
                break
            time.sleep(0.65)
    except Exception:
        if cached:
            return cached
        raise

    candidate = MarketSnapshot(time.time(), list(all_quotes.values()), complete, total_reported)
    if not candidate.quotes:
        if cached:
            return cached
        raise ValueError("Steam Market respondeu sem itens reconhecíveis")

    selected = prefer_snapshot(cached, candidate)
    if selected is candidate and (candidate.complete or cached is None):
        save_market_snapshot(cache_path, candidate)
    return selected


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
    """Ranking signal, not a sale-price or liquidity promise.

    The visible listing count is retained in MarketQuote for context only. It is
    deliberately excluded from the ranking because more active listings can mean
    either demand or simply more competing supply; without sales-volume history,
    treating it as liquidity would be an unsupported inference.
    """
    material_bonus = 1.0 if str(item_type).upper() == "MATERIAL" else 0.0
    enchant_penalty = -1.0 if has_enchantments else 0.0
    if quote:
        return (
            1.0,
            float(quote.price_value),
            material_bonus,
            enchant_penalty,
            float(rarity_rank),
        )
    return (
        0.0,
        0.0,
        material_bonus,
        enchant_penalty,
        float(rarity_rank),
    )
