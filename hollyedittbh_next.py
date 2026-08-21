#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import queue
import threading
import time
from tkinter import Tk

import tbh_save_editor as legacy
from catalog_update import safe_download_catalog
from intelligence_engine import optimal_unique_assignment, score_item
from market_intelligence import (
    BASE_LISTING_SLOTS,
    fetch_market_snapshot,
    load_market_snapshot,
    market_eligibility,
    market_priority,
    quote_for_item,
)

PROFILE_FILE = legacy.RESOURCE_DIR / "hero_profiles.json"
MARKET_CACHE_FILE = legacy.USER_DATA_DIR / "steam_market_snapshot.json"

THEME = legacy.THEME

RARITY_FOREGROUNDS = {
    "COMMON": "#B6C2D2",
    "UNCOMMON": "#75DB9A",
    "RARE": "#71B7FF",
    "LEGENDARY": "#FFD166",
    "IMMORTAL": "#C59BFF",
    "ARCANA": "#F49BFF",
    "BEYOND": "#67E8F9",
    "CELESTIAL": "#A5F3FC",
    "DIVINE": "#FFB86B",
    "COSMIC": "#FFF1C7",
}

def _load_profiles() -> dict:
    try:
        raw = json.loads(PROFILE_FILE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except (OSError, ValueError, json.JSONDecodeError):
        return {}


def _version_tuple(value: object) -> tuple[int, ...]:
    parts = []
    for chunk in str(value or "").split("."):
        try:
            parts.append(int(chunk))
        except ValueError:
            return ()
    return tuple(parts)


class EnhancedProEditor(legacy.ProEditor):
    def __init__(self, root: Tk) -> None:
        self.hero_profiles = _load_profiles()
        self.market_snapshot = load_market_snapshot(MARKET_CACHE_FILE)
        self.intel_jobs: queue.Queue = queue.Queue()
        self._last_catalog_auto_refresh = 0.0
        self._last_market_auto_refresh = 0.0
        super().__init__(root)
        self._configure_rarity_tags()
        self.root.after(350, self._poll_intelligence_jobs)
        self.root.after(1200, self.refresh_intelligence_sources)

    def _configure_rarity_tags(self) -> None:
        for tree_name in ("inventory_tree", "stash_tree", "trading_tree", "all_tree"):
            tree = getattr(self, tree_name, None)
            if tree is None:
                continue
            for rarity, color in RARITY_FOREGROUNDS.items():
                tree.tag_configure(f"rarity_{rarity}", foreground=color)

    def _apply_rarity_tags(self) -> None:
        reverse = {label: rarity for rarity, label in legacy.RARITY_LABELS.items()}
        for tree_name in ("inventory_tree", "stash_tree", "trading_tree", "all_tree"):
            tree = getattr(self, tree_name, None)
            if tree is None:
                continue
            for iid in tree.get_children():
                values = tree.item(iid, "values")
                if len(values) < 4:
                    continue
                rarity = reverse.get(str(values[3]), str(values[3]).upper())
                if rarity in RARITY_FOREGROUNDS:
                    tree.item(iid, tags=(f"rarity_{rarity}",))

    def refresh_all(self) -> None:
        super().refresh_all()
        self._configure_rarity_tags()
        self._apply_rarity_tags()

    def _hero_weights(self, hero_key: int) -> dict[int, float]:
        heroes = self.hero_profiles.get("heroes", {}) if isinstance(self.hero_profiles, dict) else {}
        row = heroes.get(str(hero_key), {}) if isinstance(heroes, dict) else {}
        raw_weights = row.get("weights", {}) if isinstance(row, dict) else {}
        result: dict[int, float] = {}
        for key, value in raw_weights.items():
            try:
                result[int(key)] = float(value)
            except (TypeError, ValueError):
                continue
        return result

    def auto_equip_breakdown(self, item: dict | None, hero: dict):
        return score_item(
            item,
            self.item_db(item) if item else None,
            self._hero_weights(legacy.safe_int(hero.get("heroKey"))),
            unprofiled_stat_weight=float(self.hero_profiles.get("default_unprofiled_weight", 0.85) or 0.85),
        )

    def auto_equip_score(self, item: dict | None, hero: dict) -> tuple[float, ...]:
        return self.auto_equip_breakdown(item, hero).as_tuple()

    def auto_equip_score_label(self, item: dict | None, hero: dict) -> str:
        if not item:
            return "Vazio"
        score = self.auto_equip_breakdown(item, hero)
        level_note = f" · Lv {round(score.level / 0.22)}" if score.level_known and score.level > 0 else ""
        return f"nota {score.total:.1f} · {legacy.rarity_label(self.item_rarity(item)) or 'sem DB'}{level_note} · afinidade {score.affinity:.1f} · T{score.total_tier}"

    def enchant_quality_label(self, item: dict | None, hero: dict) -> str:
        if not item:
            return "Sem item"
        enchants = item.get("EnchantData", [])
        filled = sum(isinstance(row, dict) and self.enchant_is_filled(row) for row in enchants)
        score = self.auto_equip_breakdown(item, hero)
        return f"{filled}/{len(enchants)} ativos · nota {score.total:.1f} · AF {score.affinity:.1f} · T{score.total_tier}"

    def build_auto_equip_all_plan(self) -> list[dict]:
        if not self.data:
            return []
        heroes = [hero for hero in self.data["player"].get("heroSaveDatas", []) if isinstance(hero, dict)]
        if not heroes:
            return []
        storage_items: dict[int, dict] = {}
        for row in self.storage_item_rows():
            item = row["item"]
            uid = legacy.safe_int(item.get("UniqueId"))
            if uid:
                storage_items[uid] = item

        result: list[dict] = []
        for slot_index in range(10):
            current_uids: list[int] = []
            candidate_items: dict[int, dict] = dict(storage_items)
            incompatible_current = False
            for hero in heroes:
                ids = list(hero.get("equippedItemIds", []))
                uid = legacy.safe_int(ids[slot_index]) if slot_index < len(ids) else 0
                current_uids.append(uid)
                item = self.items_by_uid.get(uid)
                if item:
                    candidate_items[uid] = item
                    if not self.item_compatible_with_slot(item, hero, slot_index):
                        incompatible_current = True
            if incompatible_current:
                continue

            candidates = [
                item for _uid, item in sorted(candidate_items.items())
                if any(self.item_compatible_with_slot(item, hero, slot_index) for hero in heroes)
            ]
            if not candidates:
                continue

            score_matrix: list[list[float | None]] = []
            minima: list[float] = []
            for hero, current_uid in zip(heroes, current_uids):
                current_item = self.items_by_uid.get(current_uid)
                minima.append(self.auto_equip_breakdown(current_item, hero).total)
                score_matrix.append([
                    self.auto_equip_breakdown(candidate, hero).total
                    if self.item_compatible_with_slot(candidate, hero, slot_index) else None
                    for candidate in candidates
                ])

            assignment = optimal_unique_assignment(score_matrix, minimum_scores=minima)
            for hero_index, candidate_index in enumerate(assignment.item_by_hero):
                if candidate_index < 0:
                    continue
                replacement = candidates[candidate_index]
                replacement_uid = legacy.safe_int(replacement.get("UniqueId"))
                current_uid = current_uids[hero_index]
                if replacement_uid == current_uid:
                    continue
                hero = heroes[hero_index]
                result.append({
                    "hero": hero,
                    "hero_key": legacy.safe_int(hero.get("heroKey")),
                    "slot_index": slot_index,
                    "current_uid": current_uid,
                    "replacement_uid": replacement_uid,
                    "current_score": self.auto_equip_score(self.items_by_uid.get(current_uid), hero),
                    "replacement_score": self.auto_equip_score(replacement, hero),
                })

        result.sort(key=lambda row: (row["slot_index"], row["hero_key"], row["replacement_uid"]))
        return result

    @staticmethod
    def _plan_signature(rows: list[dict]) -> list[tuple[int, int, int, int]]:
        return [(row["hero_key"], row["slot_index"], row["current_uid"], row["replacement_uid"]) for row in rows]

    def _storage_location_map(self) -> dict[int, dict]:
        result: dict[int, dict] = {}
        if not self.data:
            return result
        for source in ("inventorySaveDatas", "stashSaveDatas"):
            for slot in self.data["player"].get(source, []):
                uid = legacy.safe_int(slot.get("ItemUniqueId"))
                if uid:
                    result[uid] = slot
        return result

    def apply_auto_equip_all_plan(self, rows: list[dict]) -> int:
        if not self.data:
            return 0
        current_plan = self.build_auto_equip_all_plan()
        if self._plan_signature(current_plan) != self._plan_signature(rows):
            return 0
        storage_locations = self._storage_location_map()
        grouped: dict[int, list[dict]] = {}
        for row in rows:
            grouped.setdefault(row["slot_index"], []).append(row)

        for slot_index, slot_rows in grouped.items():
            current_set = {row["current_uid"] for row in slot_rows if row["current_uid"]}
            desired_set = {row["replacement_uid"] for row in slot_rows if row["replacement_uid"]}
            incoming = sorted(desired_set - current_set)
            outgoing = sorted(current_set - desired_set)
            source_slots: list[dict] = []
            for uid in incoming:
                source = storage_locations.get(uid)
                if source is None or legacy.safe_int(source.get("ItemUniqueId")) != uid:
                    return 0
                source_slots.append(source)
            if len(outgoing) > len(source_slots):
                return 0
            for row in slot_rows:
                ids = row["hero"].setdefault("equippedItemIds", [])
                while len(ids) < 10:
                    ids.append(0)
                if legacy.safe_int(ids[slot_index]) != row["current_uid"]:
                    return 0
            for row in slot_rows:
                row["hero"]["equippedItemIds"][slot_index] = row["replacement_uid"]
            for index, source_slot in enumerate(source_slots):
                source_slot["ItemUniqueId"] = outgoing[index] if index < len(outgoing) else 0
        return len(rows)

    def configured_market_slots(self) -> int:
        try:
            requested = int(os.environ.get("HOLLYEDIT_MARKET_SLOTS", BASE_LISTING_SLOTS))
        except ValueError:
            requested = BASE_LISTING_SLOTS
        return max(1, min(12, requested))

    def market_candidate_status(self, item: dict) -> tuple[bool, str]:
        uid = legacy.safe_int(item.get("UniqueId"))
        db = self.item_db(item)
        rarity = self.item_rarity(item).upper()
        if uid not in getattr(self, "original_item_uids", set()):
            return False, "criado fora do save carregado"
        if self.item_is_session_changed(item):
            return False, "criado ou alterado nesta sessão"
        if not db:
            return False, "item especial sem dados suficientes no catálogo"
        if bool(item.get("IsBlocked")):
            return False, "item bloqueado no save"
        if any(legacy.safe_int(value) == uid for hero in self.data["player"].get("heroSaveDatas", []) for value in hero.get("equippedItemIds", [])):
            return False, "item equipado"
        source_type = legacy.safe_int(item.get("ItemGetSourceType"), -1)
        if source_type in legacy.MARKET_SOURCE_TYPES_EXCLUDED:
            return False, "origem local não verificável pelo editor"
        policy = market_eligibility(str(db.get("Type") or ""), rarity, is_soulstone=self.item_is_soulstone(item))
        if not policy.allowed:
            return False, policy.reason
        reason = policy.reason
        if any(isinstance(row, dict) and self.enchant_is_filled(row) for row in item.get("EnchantData", [])):
            reason += "; encantamentos não aumentam a nota de venda e são descartados ao listar"
        return True, reason

    def market_candidates(self, stash_page: int, limit: int) -> list[dict]:
        rows: list[dict] = []
        snapshot = self.market_snapshot
        for source_row in self.storage_item_rows():
            item = source_row["item"]
            if source_row["source"] == "stashSaveDatas" and self.stash_page_for_index(legacy.safe_int(source_row["source_slot"].get("Index"))) == stash_page:
                continue
            accepted, reason = self.market_candidate_status(item)
            if not accepted:
                continue
            db = self.item_db(item)
            rarity = self.item_rarity(item).upper()
            quote = quote_for_item(snapshot, self.item_name(item), rarity)
            has_enchants = any(isinstance(enchant, dict) and self.enchant_is_filled(enchant) for enchant in item.get("EnchantData", []))
            priority = market_priority(quote, rarity_rank=legacy.RARITY_RANK.get(rarity, 0), item_type=str(db.get("Type") or ""), has_enchantments=has_enchants)
            row = dict(source_row)
            row["quality"] = priority
            row["market_quote"] = quote
            row["reason"] = (
                f"{reason}; Steam: {quote.price_text or 'preço n/d'} · {quote.sell_listings} anúncio(s)"
                if quote else f"{reason}; sem cotação inequívoca no snapshot atual"
            )
            rows.append(row)
        rows.sort(key=lambda row: (row["quality"], legacy.normalize_search_text(self.item_name(row["item"]))), reverse=True)
        self.last_market_pool = len(rows)
        return rows[: min(max(0, limit), self.market_round_capacity(stash_page))]

    def start_db_download(self) -> None:
        previous_rows = list(self.db)
        def worker() -> None:
            try:
                rows = safe_download_catalog(self.jobs, previous_rows=previous_rows, cache_file=legacy.CACHE_FILE, base_url=legacy.BASE_URL, fetch_url=legacy.fetch_url, parse_embedded_items=legacy.parse_embedded_items)
                self.jobs.put(("db", rows))
            except Exception as exc:
                self.jobs.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def _catalog_refresh_background(self) -> None:
        previous_rows = list(self.db)
        class Progress:
            def __init__(self, jobs: queue.Queue) -> None:
                self.jobs = jobs
            def put(self, payload) -> None:
                kind, value = payload
                if kind == "status":
                    self.jobs.put(("status", value))
        try:
            rows = safe_download_catalog(Progress(self.intel_jobs), previous_rows=previous_rows, cache_file=legacy.CACHE_FILE, base_url=legacy.BASE_URL, fetch_url=legacy.fetch_url, parse_embedded_items=legacy.parse_embedded_items)
            self.intel_jobs.put(("catalog", rows))
        except Exception as exc:
            self.intel_jobs.put(("status", f"Catálogo: {exc}"))

    def _market_refresh_background(self) -> None:
        try:
            self.intel_jobs.put(("market", fetch_market_snapshot(MARKET_CACHE_FILE)))
        except Exception as exc:
            self.intel_jobs.put(("status", f"Mercado Steam: {exc}"))

    def refresh_intelligence_sources(self) -> None:
        now = time.time()
        try:
            cache_age = now - legacy.CACHE_FILE.stat().st_mtime
        except OSError:
            cache_age = None
        if (cache_age is None or cache_age > 24 * 60 * 60) and now - self._last_catalog_auto_refresh > 60:
            self._last_catalog_auto_refresh = now
            threading.Thread(target=self._catalog_refresh_background, daemon=True).start()
        if (self.market_snapshot is None or not self.market_snapshot.is_fresh()) and now - self._last_market_auto_refresh > 60:
            self._last_market_auto_refresh = now
            threading.Thread(target=self._market_refresh_background, daemon=True).start()
        self.root.after(60 * 60 * 1000, self.refresh_intelligence_sources)

    def _poll_intelligence_jobs(self) -> None:
        try:
            while True:
                kind, payload = self.intel_jobs.get_nowait()
                if kind == "catalog":
                    self.set_item_db(list(payload))
                    self.status_var.set(f"Catálogo atualizado e validado: {len(self.db)} itens")
                    self.refresh_all()
                elif kind == "market":
                    self.market_snapshot = payload
                    suffix = "completo" if payload.complete else "parcial"
                    self.status_var.set(f"Steam Market atualizado: {len(payload.quotes)} cotações ({suffix})")
                elif kind == "status":
                    self.status_var.set(str(payload))
        except queue.Empty:
            pass
        self.root.after(500, self._poll_intelligence_jobs)

    def campaign_access_changes(self, apply: bool = False) -> list[str]:
        if not self.data:
            return []
        common = self.data["player"].get("commonSaveData", {})
        version = str(common.get("version", ""))
        mapping = legacy.KNOWN_CUBE_RECIPE_MAX_BY_VERSION
        if version in mapping or not mapping:
            return super().campaign_access_changes(apply=apply)
        known_versions = sorted(mapping, key=_version_tuple)
        latest = known_versions[-1]
        if _version_tuple(version) and _version_tuple(version) >= _version_tuple(latest):
            mapping[version] = copy.deepcopy(mapping[latest])
            try:
                return super().campaign_access_changes(apply=apply)
            finally:
                mapping.pop(version, None)
        return super().campaign_access_changes(apply=apply)


# Este módulo é uma camada intermediária, não uma aplicação. Até a 3.3.2 ele
# expunha um ``main()`` próprio: executá-lo diretamente entregava um editor sem
# a persistência transacional, sem a detecção fail-safe do jogo aberto e sem os
# bloqueios de criação/duplicação do Modo Protegido — todos aplicados apenas na
# camada final. A entrada suportada é hollyedittbh_final.py.
if __name__ == "__main__":
    raise SystemExit(
        "hollyedittbh_next é uma camada interna. Execute: py -3.12 hollyedittbh_final.py"
    )
