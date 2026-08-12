from __future__ import annotations

import time
import urllib.request
from pathlib import Path

from market_intelligence import (
    MarketQuote,
    MarketSnapshot,
    SNAPSHOT_TTL_SECONDS,
    STEAM_APP_ID,
    STEAM_MARKET_SEARCH,
    load_market_snapshot,
    normalize_market_text,
    parse_market_search_html,
    save_market_snapshot,
)


def prefer_snapshot(cached: MarketSnapshot | None, candidate: MarketSnapshot) -> MarketSnapshot:
    """Preserva um snapshot anterior quando a nova coleta parece truncada.

    Respostas incompletas ainda podem ser usadas quando não há cache, mas nunca
    substituem silenciosamente um cache mais completo já existente.
    """
    if candidate.complete:
        return candidate
    if cached and len(cached.quotes) >= len(candidate.quotes):
        return cached
    return candidate


def fetch_market_snapshot_guarded(
    cache_path: Path,
    *,
    force: bool = False,
    ttl_seconds: int = SNAPSHOT_TTL_SECONDS,
    max_pages: int = 12,
    page_size: int = 100,
    timeout: int = 15,
) -> MarketSnapshot:
    """Atualiza o snapshot público do Steam Market sem degradar um cache válido."""
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
                    "User-Agent": "HollyEditTBH/3.3.1 (+public Steam Community Market snapshot)",
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
    if selected is candidate and candidate.complete:
        save_market_snapshot(cache_path, candidate)
    return selected
