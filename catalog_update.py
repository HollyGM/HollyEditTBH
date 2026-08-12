from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import time
from typing import Callable, Iterable, Mapping


@dataclass(frozen=True)
class CatalogValidation:
    ok: bool
    reason: str
    count: int
    previous_count: int


def catalog_fingerprint(rows: Iterable[Mapping]) -> str:
    digest = hashlib.sha256()
    for row in sorted(rows, key=lambda value: int(value.get("ItemKey") or 0)):
        digest.update(
            (
                f"{row.get('ItemKey')}|{row.get('Name')}|{row.get('Rarity')}|"
                f"{row.get('Type')}|{','.join(map(str, row.get('StatTypes') or []))}\n"
            ).encode("utf-8", errors="replace")
        )
    return digest.hexdigest()


def validate_catalog_candidate(
    rows: list[dict],
    previous_rows: list[dict] | None = None,
    *,
    absolute_minimum: int = 1000,
    regression_ratio: float = 0.90,
) -> CatalogValidation:
    previous_rows = previous_rows or []
    previous_count = len(previous_rows)
    if len(rows) < absolute_minimum:
        return CatalogValidation(False, f"catálogo parcial: apenas {len(rows)} itens", len(rows), previous_count)

    keys: list[int] = []
    invalid = 0
    types: set[str] = set()
    rarities: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            invalid += 1
            continue
        try:
            key = int(row.get("ItemKey") or 0)
        except (TypeError, ValueError):
            key = 0
        if key <= 0 or not str(row.get("Name") or "").strip():
            invalid += 1
        keys.append(key)
        types.add(str(row.get("Type") or "").upper())
        rarities.add(str(row.get("Rarity") or "").upper())

    if invalid:
        return CatalogValidation(False, f"{invalid} registro(s) inválido(s)", len(rows), previous_count)
    if len(keys) != len(set(keys)):
        return CatalogValidation(False, "ItemKey duplicado no catálogo recebido", len(rows), previous_count)
    if not {"GEAR", "MATERIAL"}.issubset(types):
        return CatalogValidation(False, "catálogo recebido não contém os tipos básicos esperados", len(rows), previous_count)
    if len({rarity for rarity in rarities if rarity}) < 6:
        return CatalogValidation(False, "catálogo recebido perdeu diversidade de raridades", len(rows), previous_count)
    if previous_count >= absolute_minimum and len(rows) < int(previous_count * regression_ratio):
        return CatalogValidation(
            False,
            f"regressão de catálogo: {previous_count} → {len(rows)} itens",
            len(rows),
            previous_count,
        )
    return CatalogValidation(True, "catálogo íntegro", len(rows), previous_count)


def atomic_write_catalog(cache_file: Path, rows: list[dict], *, source_url: str) -> None:
    cache_file.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "downloadedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": source_url,
        "count": len(rows),
        "fingerprint": catalog_fingerprint(rows),
        "items": rows,
    }
    temp = cache_file.with_suffix(cache_file.suffix + ".tmp")
    try:
        temp.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        os.replace(temp, cache_file)
    finally:
        if temp.exists():
            temp.unlink()


def safe_download_catalog(
    progress,
    *,
    previous_rows: list[dict],
    cache_file: Path,
    base_url: str,
    fetch_url: Callable[[str, int], bytes],
    parse_embedded_items: Callable[[str], list[dict]],
) -> list[dict]:
    source_url = f"{base_url.rstrip('/')}/items"
    progress.put(("status", "Atualizando catálogo de itens com validação de integridade..."))
    page = fetch_url(source_url, 20).decode("utf-8", errors="replace")
    rows = parse_embedded_items(page)
    result = validate_catalog_candidate(rows, previous_rows)
    if not result.ok:
        raise ValueError(
            f"{result.reason}. O catálogo anterior foi preservado "
            f"({result.previous_count} itens)."
        )
    atomic_write_catalog(cache_file, rows, source_url=source_url)
    progress.put(("status", f"Catálogo validado: {len(rows)} itens"))
    return rows
