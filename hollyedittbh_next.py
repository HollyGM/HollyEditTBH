#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import os
from pathlib import Path
import queue
import sys
import threading
import time
import tkinter as tk
from tkinter import Tk

import tbh_save_editor as legacy
from catalog_update import safe_download_catalog
from intelligence_engine import (
    SLOT_NAMES as INTELLIGENCE_SLOT_NAMES,
    optimal_unique_assignment,
    score_item,
    slot_prefixes as intelligence_slot_prefixes,
)
from market_intelligence import (
    BASE_LISTING_SLOTS,
    fetch_market_snapshot,
    load_market_snapshot,
    market_eligibility,
    market_priority,
    quote_for_item,
)

legacy.SLOT_NAMES.update(INTELLIGENCE_SLOT_NAMES)

PROFILE_FILE = legacy.RESOURCE_DIR / "hero_profiles.json"
MARKET_CACHE_FILE = legacy.USER_DATA_DIR / "steam_market_snapshot.json"

THEME = {
    "base": "#08111F",
    "top": "#0F1B2D",
    "panel": "#111F33",
    "card": "#172A43",
    "selected": "#1D3C5F",
    "input": "#0B1728",
    "border": "#2B4566",
    "text": "#F4F7FB",
    "muted": "#A9B8CC",
    "muted2": "#7F93AD",
    "accent": "#53D6C5",
    "accent_text": "#061712",
    "selection": "#2F6FED",
    "danger": "#FF8C82",
    "success": "#77D6AE",
}

LEGACY_COLOR_MAP = {
    "#0e1420": THEME["base"],
    "#0e1624": THEME["input"],
    "#111a29": THEME["panel"],
    "#141722": THEME["input"],
    "#151e2c": THEME["input"],
    "#172033": THEME["top"],
    "#172438": THEME["card"],
    "#17243a": THEME["card"],
    "#181c29": THEME["base"],
    "#1a2638": THEME["card"],
    "#1c2940": THEME["card"],
    "#1d2231": THEME["card"],
    "#202638": THEME["card"],
    "#20314a": THEME["selected"],
    "#203a59": THEME["selected"],
    "#222838": THEME["card"],
    "#263a58": THEME["selected"],
    "#293b58": THEME["selected"],
    "#2a3144": THEME["selected"],
    "#2c3a51": THEME["border"],
    "#2c3d57": THEME["border"],
    "#33445f": THEME["border"],
    "#34405a": THEME["border"],
    "#f5b84b": THEME["accent"],
    "#ffb84d": THEME["accent"],
    "#ffffff": THEME["text"],
    "#e6edf7": THEME["text"],
    "#dbe7f7": THEME["text"],
    "#d7e5f7": THEME["text"],
    "#cbd7e6": THEME["muted"],
    "#c5d1e1": THEME["muted"],
    "#b5c4d8": THEME["muted"],
    "#9fb0c8": THEME["muted"],
    "#7f91aa": THEME["muted2"],
    "#6f7d95": THEME["muted2"],
    "#64748b": THEME["muted2"],
    "#83d5b5": THEME["success"],
    "#ffb4a9": THEME["danger"],
}

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

TEXT_REPLACEMENTS = {
    "Assistente guiado": "Inteligência",
    "ASSISTENTE GUIADO": "CENTRAL DE INTELIGÊNCIA",
    "A raridade tem prioridade; em empate entram caos, afinidade dos atributos e tiers dos encantamentos.":
        "A nota combina raridade, nível conhecido, afinidade e tiers dos encantamentos; a prévia mostra a decisão antes de aplicar.",
    "Cada item é usado uma única vez. A raridade tem prioridade e os encantamentos entram no desempate.":
        "Alocação global exata: cada item é usado uma única vez e nenhum herói é rebaixado para beneficiar outro.",
    "Compare o item equipado com a melhor opção disponível. A raridade vem primeiro; em empate, afinidade, tiers e quantidade de encantamentos decidem.":
        "Compare o item equipado com a melhor opção disponível. A nota combina raridade, nível conhecido, afinidade, tiers e ocupação dos encantamentos.",
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
        self.theme = dict(THEME)
        self.hero_profiles = _load_profiles()
        self.market_snapshot = load_market_snapshot(MARKET_CACHE_FILE)
        self.intel_jobs: queue.Queue = queue.Queue()
        self._last_catalog_auto_refresh = 0.0
        self._last_market_auto_refresh = 0.0
        super().__init__(root)
        self._install_runtime_theme()
        self._configure_rarity_tags()
        self.root.after(350, self._poll_intelligence_jobs)
        self.root.after(1200, self.refresh_intelligence_sources)

    def setup_style(self) -> None:
        self.root.configure(bg=self.theme["base"])
        style = legacy.ttk.Style()
        style.theme_use("clam")
        style.configure(".", background=self.theme["base"], foreground=self.theme["text"], fieldbackground=self.theme["top"], bordercolor=self.theme["border"])
        style.configure("Top.TFrame", background=self.theme["top"])
        style.configure("Panel.TFrame", background=self.theme["panel"], relief="solid", borderwidth=1)
        style.configure("Card.TFrame", background=self.theme["card"], relief="solid", borderwidth=1)
        style.configure("Selected.TFrame", background=self.theme["selected"], relief="solid", borderwidth=1)
        style.configure("TButton", background=self.theme["card"], foreground=self.theme["text"], borderwidth=0, padding=(10, 7))
        style.map("TButton", background=[("active", self.theme["selected"]), ("disabled", self.theme["input"])], foreground=[("disabled", self.theme["muted2"])])
        style.configure("Accent.TButton", background=self.theme["accent"], foreground=self.theme["accent_text"], borderwidth=0, padding=(12, 8), font=("Segoe UI", 9, "bold"))
        style.configure("Compact.TButton", background=self.theme["card"], foreground=self.theme["text"], borderwidth=0, padding=(6, 2))
        style.configure("TEntry", fieldbackground=self.theme["input"], foreground=self.theme["text"], bordercolor=self.theme["border"], padding=5)
        style.configure("TCombobox", fieldbackground=self.theme["input"], foreground=self.theme["text"], arrowcolor=self.theme["text"], padding=4)
        style.configure("TNotebook", background=self.theme["base"], borderwidth=0)
        style.configure("TNotebook.Tab", background=self.theme["top"], foreground=self.theme["muted"], padding=(14, 9))
        style.map("TNotebook.Tab", background=[("selected", self.theme["selected"])], foreground=[("selected", self.theme["text"])])
        style.configure("Treeview", background=self.theme["panel"], foreground=self.theme["text"], fieldbackground=self.theme["panel"], bordercolor=self.theme["border"], lightcolor=self.theme["border"], darkcolor=self.theme["border"], rowheight=36)
        style.map("Treeview", background=[("selected", self.theme["selection"])], foreground=[("selected", self.theme["text"])])
        style.configure("Treeview.Heading", background=self.theme["card"], foreground=self.theme["text"], bordercolor=self.theme["border"], relief="solid", font=("Segoe UI", 9, "bold"))
        style.map("Treeview.Heading", background=[("active", self.theme["selected"])])

    def _install_runtime_theme(self) -> None:
        self._retint_widget(self.root, recursive=True)
        self.root.bind_all("<Map>", lambda event: self._retint_widget(event.widget, recursive=True), add="+")

    def _retint_widget(self, widget: tk.Misc, recursive: bool = False) -> None:
        if not isinstance(widget, tk.Misc):
            return
        options = {
            "background": "background",
            "foreground": "foreground",
            "activebackground": "activebackground",
            "activeforeground": "activeforeground",
            "highlightbackground": "highlightbackground",
            "highlightcolor": "highlightcolor",
            "insertbackground": "insertbackground",
            "selectbackground": "selectbackground",
            "selectforeground": "selectforeground",
        }
        changes = {}
        for option in options:
            try:
                current = str(widget.cget(option)).lower()
            except (tk.TclError, AttributeError):
                continue
            replacement = LEGACY_COLOR_MAP.get(current)
            if replacement and replacement.lower() != current:
                changes[option] = replacement
        try:
            current_text = str(widget.cget("text"))
            replacement_text = TEXT_REPLACEMENTS.get(current_text)
            if replacement_text:
                changes["text"] = replacement_text
        except (tk.TclError, AttributeError):
            pass
        if changes:
            try:
                widget.configure(**changes)
            except tk.TclError:
                pass
        if recursive:
            try:
                children = widget.winfo_children()
            except tk.TclError:
                children = []
            for child in children:
                self._retint_widget(child, recursive=True)

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
        self._retint_widget(self.root, recursive=True)

    def open_smart_center(self) -> None:
        before = set(self.root.winfo_children())
        super().open_smart_center()
        self.root.update_idletasks()
        for child in self.root.winfo_children():
            if child in before or not isinstance(child, tk.Toplevel):
                continue
            try:
                if child.title() == "Assistente guiado":
                    child.title("Inteligência — equipamentos, desbloqueios e Mercado")
            except tk.TclError:
                pass
            self._retint_widget(child, recursive=True)

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

    def slot_prefixes(self, hero_key: int, slot_index: int) -> set[str]:
        return intelligence_slot_prefixes(hero_key, slot_index)

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
        target = f"Armazem {stash_page}"
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
        capacity = self.free_slot_count(target)
        batch_limit = min(max(0, limit), capacity, self.configured_market_slots())
        return rows[:batch_limit]

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


def main() -> None:
    root = Tk()
    app = EnhancedProEditor(root)
    requested = Path(sys.argv[1]) if len(sys.argv) > 1 and not str(sys.argv[1]).startswith("-") else None
    default_dump = legacy.APP_DIR / "player_dump.json"
    if requested and requested.is_file():
        app.load_dump(requested)
    elif default_dump.exists():
        app.load_dump(default_dump)
    root.mainloop()


if __name__ == "__main__":
    main()
