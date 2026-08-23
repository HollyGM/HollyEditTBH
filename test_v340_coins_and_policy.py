"""Regressões da 3.4.0: moedas comemorativas, política única e fim dos hacks."""
import json
import unittest
from pathlib import Path
from unittest.mock import patch

import commemorative_coins as coins
import intelligence_engine as intelligence
import legacy_editor
import market_intelligence
import market_policy
import market_snapshot_guard
from app_meta import APP_VERSION
from tbh_save_editor import ProEditor, safe_int

BASE = Path(__file__).resolve().parent
CATALOG = json.loads((BASE / "tbh_items_cache.json").read_text(encoding="utf-8"))["items"]


def minimal_player():
    return {
        "itemSaveDatas": [],
        "heroSaveDatas": [],
        "inventorySaveDatas": [],
        "stashSaveDatas": [],
        "remakeTradingStashSaveDatas": [],
    }


def stash_slot(index, uid=0, unlocked=True):
    return {"Index": index, "ItemUniqueId": uid, "IsUnLock": unlocked, "IsUnlockedByRune": False}


def inventory_slot(index, uid=0):
    return {"Index": index, "ItemUniqueId": uid, "IsUnlock": True, "IsUnlockedByRune": False}


def headless(player, database=None):
    editor = ProEditor.__new__(ProEditor)
    editor.data = {"account": {}, "player": player}
    editor.items = list(player.get("itemSaveDatas", []))
    editor.db = list(database if database is not None else CATALOG)
    editor.db_by_key = {str(row["ItemKey"]): row for row in editor.db}
    editor.loaded_kind = "json"
    editor.save_file = None
    editor.selected_item = None
    editor.protected_mode = True
    editor.session_created_uids = set()
    editor.session_modified_uids = set()
    editor.last_market_pool = 0
    editor.last_recycle_pool = 0
    editor.mark_dirty = lambda *_a, **_k: None
    editor.refresh_all = lambda: None
    editor.rebuild_item_index()
    editor.original_item_uids = set(editor.items_by_uid)
    return editor


def coin_item(item_key, uid):
    return {
        "ItemKey": item_key, "UniqueId": uid, "PrevUniqueId": 0, "IsChaotic": False,
        "IsBlocked": False, "EnchantCount": [0, 0, 0], "EnchantData": [],
        "ItemGetSourceType": 1, "DecorationAppliedTotalCount": 0,
        "EngravingAppliedTotalCount": 0, "InscriptionAppliedTotalCount": 0,
    }


class CommemorativeCoinRegistryTests(unittest.TestCase):
    def test_registry_matches_the_published_catalog(self):
        """Nome e raridade das dez moedas conferem com tbh_items_cache.json."""
        by_key = {int(row["ItemKey"]): row for row in CATALOG}
        self.assertEqual(len(coins.COIN_DEFINITIONS), 10)
        for definition in coins.COIN_DEFINITIONS:
            row = by_key.get(definition.item_key)
            self.assertIsNotNone(row, f"moeda {definition.item_key} ausente do catálogo")
            self.assertEqual(row["Name"], definition.name)
            self.assertEqual(row["Rarity"], definition.rarity)
            self.assertEqual(row["Type"], "MATERIAL")

    def test_registry_covers_every_rarity_exactly_once(self):
        rarities = [definition.rarity for definition in coins.COIN_DEFINITIONS]
        self.assertEqual(sorted(rarities), sorted(legacy_editor.RARITY_RANK))

    def test_catalog_has_no_coin_outside_the_declared_range(self):
        found = {
            int(row["ItemKey"]) for row in CATALOG
            if "anniversary coin" in str(row.get("Name", "")).casefold()
        }
        self.assertEqual(found, set(coins.COIN_KEYS))

    def test_is_coin_key_tolerates_strings_and_junk(self):
        self.assertTrue(coins.is_coin_key("160001"))
        self.assertTrue(coins.is_coin_key(160010))
        self.assertFalse(coins.is_coin_key(160011))
        self.assertFalse(coins.is_coin_key(None))
        self.assertFalse(coins.is_coin_key("abacaxi"))


class CommemorativeCoinPlanTests(unittest.TestCase):
    def build(self, *, page_unlocked=True, free_slots=10):
        player = minimal_player()
        player["inventorySaveDatas"] = [inventory_slot(index) for index in range(6)]
        # páginas 1 e 2 existem; a 2 recebe a fila
        player["stashSaveDatas"] = [stash_slot(index) for index in range(66)]
        player["stashSaveDatas"] += [
            stash_slot(66 + index, unlocked=page_unlocked) for index in range(66)
        ]
        items = []
        uid = 500
        # três moedas no inventário, duas já na página 2
        for offset, key in enumerate((160010, 160001, 160005)):
            uid += 1
            items.append(coin_item(key, uid))
            player["inventorySaveDatas"][offset]["ItemUniqueId"] = uid
        for offset, key in enumerate((160009, 160003)):
            uid += 1
            items.append(coin_item(key, uid))
            player["stashSaveDatas"][66 + offset]["ItemUniqueId"] = uid
        # ruído: um item que não é moeda
        uid += 1
        items.append({"ItemKey": 110001, "UniqueId": uid, "EnchantData": [], "EnchantCount": [0, 0, 0]})
        player["inventorySaveDatas"][5]["ItemUniqueId"] = uid
        player["itemSaveDatas"] = items
        # ocupa o excedente da página para simular espaço restrito
        for index in range(66 + 2 + free_slots, 132):
            player["stashSaveDatas"][index]["ItemUniqueId"] = 90000 + index
        return headless(player)

    def test_finds_every_coin_and_ignores_other_items(self):
        editor = self.build()
        rows = editor.commemorative_coin_rows()
        self.assertEqual(len(rows), 5)
        self.assertTrue(all(coins.coin_for_item(row["item"]) for row in rows))

    def test_groups_are_ordered_by_registry_and_carry_locations(self):
        editor = self.build()
        groups = editor.commemorative_coin_groups()
        self.assertEqual([g.definition.item_key for g in groups], [160001, 160003, 160005, 160009, 160010])
        by_key = {g.definition.item_key: g for g in groups}
        self.assertEqual(by_key[160001].locations, ("Inventário",))
        self.assertEqual(by_key[160003].locations, ("Armazém 2",))

    def test_plan_skips_coins_already_on_the_target_page(self):
        editor = self.build()
        plan = editor.build_commemorative_coin_plan(2)
        self.assertEqual(plan.total_found, 5)
        self.assertEqual(len(plan.already_there), 2)
        self.assertEqual(plan.moving, 3)
        self.assertEqual(plan.left_out, 0)

    def test_plan_orders_by_rarity_so_the_top_grade_moves_first(self):
        editor = self.build()
        plan = editor.build_commemorative_coin_plan(2)
        keys = [safe_int(row["item"]["ItemKey"]) for row in plan.rows_to_apply]
        self.assertEqual(keys, [160010, 160005, 160001])

    def test_plan_respects_the_remaining_space_on_the_page(self):
        editor = self.build(free_slots=2)
        plan = editor.build_commemorative_coin_plan(2)
        self.assertEqual(plan.moving, 2)
        self.assertEqual(plan.left_out, 1)
        self.assertIn("sem espaço nesta página", plan.summary())

    def test_locked_page_is_reported_instead_of_silently_returning_zero(self):
        editor = self.build(page_unlocked=False)
        plan = editor.build_commemorative_coin_plan(2)
        self.assertFalse(plan.page_unlocked)
        self.assertEqual(plan.moving, 0)
        self.assertIn("bloqueado", plan.summary())

    def test_applying_the_plan_really_moves_the_coins(self):
        editor = self.build()
        plan = editor.build_commemorative_coin_plan(2)
        moved_uids = [safe_int(row["item"]["UniqueId"]) for row in plan.rows_to_apply]
        applied = editor.apply_storage_queue(list(plan.rows_to_apply), 2)
        self.assertEqual(applied, 3)

        page_two = {
            safe_int(slot["ItemUniqueId"])
            for slot in editor.data["player"]["stashSaveDatas"]
            if 66 <= safe_int(slot["Index"]) < 132
        }
        self.assertTrue(set(moved_uids).issubset(page_two))
        inventory = {safe_int(slot["ItemUniqueId"]) for slot in editor.data["player"]["inventorySaveDatas"]}
        self.assertFalse(set(moved_uids) & inventory)
        # nenhuma moeda criada, consumida ou duplicada
        self.assertEqual(len(editor.data["player"]["itemSaveDatas"]), 6)
        self.assertEqual(len(editor.commemorative_coin_rows()), 5)

    def test_second_run_has_nothing_left_to_move(self):
        editor = self.build()
        editor.apply_storage_queue(list(editor.build_commemorative_coin_plan(2).rows_to_apply), 2)
        editor.rebuild_item_index()
        again = editor.build_commemorative_coin_plan(2)
        self.assertEqual(again.moving, 0)
        self.assertEqual(len(again.already_there), 5)


class CommemorativeCoinCreationTests(unittest.TestCase):
    """A aba Moedas passou a criar moedas novas, pelo mesmo caminho de ProEditor.create_item.

    Antes só era possível reunir moedas já existentes no save (classe acima);
    estes testes cobrem a criação, que reaproveita o motor de criação de itens
    já usado pelo restante do editor em vez de duplicar validação de catálogo,
    limite de lote e capacidade de página."""

    def build(self, *, free_slots=10, page_unlocked=True):
        player = minimal_player()
        player["inventorySaveDatas"] = [inventory_slot(index) for index in range(4)]
        player["stashSaveDatas"] = [stash_slot(index) for index in range(66)]
        player["stashSaveDatas"] += [
            stash_slot(66 + index, unlocked=page_unlocked) for index in range(66)
        ]
        for index in range(66 + free_slots, 132):
            player["stashSaveDatas"][index]["ItemUniqueId"] = 90000 + index
        return headless(player)

    def test_create_item_really_adds_a_coin_to_the_chosen_stash_page(self):
        editor = self.build()
        with patch("legacy_editor.messagebox.showinfo"):
            created = editor.create_item(160006, 1, "Armazem 2", enchanted=False)
        self.assertEqual(len(created), 1)
        coin = created[0]
        self.assertEqual(safe_int(coin["ItemKey"]), 160006)

        page_two = {
            safe_int(slot["ItemUniqueId"])
            for slot in editor.data["player"]["stashSaveDatas"]
            if 66 <= safe_int(slot["Index"]) < 132
        }
        self.assertIn(safe_int(coin["UniqueId"]), page_two)
        found_uids = [safe_int(row["item"]["UniqueId"]) for row in editor.commemorative_coin_rows()]
        self.assertIn(safe_int(coin["UniqueId"]), found_uids)

    def test_a_created_coin_keeps_the_material_shape_at_any_rarity(self):
        """Moedas são MATERIAL: mesmo em raridade alta não ganham espaços de encantamento."""
        editor = self.build()
        with patch("legacy_editor.messagebox.showinfo"):
            created = editor.create_item(160009, 1, "Armazem 2", enchanted=False)  # DIVINE
        coin = created[0]
        self.assertEqual(coin["EnchantData"], [])
        self.assertEqual(coin["EnchantCount"], [0, 0, 0])

    def test_created_coin_is_flagged_and_stays_out_of_market_candidates(self):
        editor = self.build()
        with patch("legacy_editor.messagebox.showinfo"):
            created = editor.create_item(160010, 1, "Armazem 2", enchanted=False)
        coin = created[0]
        self.assertTrue(editor.item_is_session_changed(coin))
        accepted, _reason = editor.market_candidate_status(coin)
        self.assertFalse(accepted)

    def test_created_coin_can_then_be_gathered_like_any_found_coin(self):
        """Fluxo completo: adicionar uma moeda e, na sequência, juntá-la no armazém."""
        editor = self.build()
        with patch("legacy_editor.messagebox.showinfo"):
            created = editor.create_item(160001, 1, "Inventario", enchanted=False)
        coin_uid = safe_int(created[0]["UniqueId"])

        plan = editor.build_commemorative_coin_plan(2)
        self.assertIn(coin_uid, [safe_int(row["item"]["UniqueId"]) for row in plan.rows_to_apply])

        applied = editor.apply_storage_queue(list(plan.rows_to_apply), 2)
        self.assertEqual(applied, plan.moving)
        page_two = {
            safe_int(slot["ItemUniqueId"])
            for slot in editor.data["player"]["stashSaveDatas"]
            if 66 <= safe_int(slot["Index"]) < 132
        }
        self.assertIn(coin_uid, page_two)

    def test_batch_limit_still_applies_when_creating_coins(self):
        editor = self.build()
        with patch("legacy_editor.messagebox.showerror") as error:
            created = editor.create_item(160001, legacy_editor.PROTECTED_BATCH_LIMIT + 1, "Armazem 2", enchanted=False)
        self.assertEqual(created, [])
        error.assert_called_once()

    def test_create_item_refuses_a_locked_stash_page(self):
        editor = self.build(page_unlocked=False)
        with patch("legacy_editor.messagebox.showerror") as error:
            created = editor.create_item(160001, 1, "Armazem 2", enchanted=False)
        self.assertEqual(created, [])
        error.assert_called_once()


class StashPageStateTests(unittest.TestCase):
    def test_locked_page_is_detected_even_when_it_has_no_items(self):
        player = minimal_player()
        player["stashSaveDatas"] = [stash_slot(index, unlocked=index < 66) for index in range(132)]
        editor = headless(player)
        self.assertTrue(editor.stash_page_is_unlocked(1))
        self.assertFalse(editor.stash_page_is_unlocked(2))
        self.assertEqual(editor.stash_page_capacity(2), (False, 0))
        self.assertEqual(editor.market_round_capacity(2), 0)

    def test_missing_unlock_key_fails_closed_on_the_stash(self):
        """Sem a chave de desbloqueio, o editor não deve ocupar a página.

        Antes da 3.4.0 a ausência de IsUnLock era lida como liberada, e a
        gravação seguinte marcava o espaço como desbloqueado no save."""
        slot = {"Index": 70, "ItemUniqueId": 0}
        self.assertFalse(ProEditor.slot_is_unlocked("stashSaveDatas", slot))
        self.assertTrue(ProEditor.slot_is_unlocked("inventorySaveDatas", slot))

    def test_both_spellings_of_the_unlock_key_are_accepted(self):
        self.assertTrue(ProEditor.slot_is_unlocked("stashSaveDatas", {"IsUnLock": True}))
        self.assertTrue(ProEditor.slot_is_unlocked("stashSaveDatas", {"IsUnlock": True}))
        self.assertFalse(ProEditor.slot_is_unlocked("stashSaveDatas", {"IsUnLock": False}))

    def test_summary_separates_blocked_page_from_empty_result(self):
        player = minimal_player()
        player["stashSaveDatas"] = [stash_slot(index, unlocked=index < 66) for index in range(132)]
        editor = headless(player)
        self.assertIn("bloqueado", editor.queue_summary_text(2, 0, 7, "pré-candidato"))
        self.assertIn("Nenhum pré-candidato", editor.queue_summary_text(1, 0, 0, "pré-candidato"))
        text = editor.queue_summary_text(1, 4, 30, "pré-candidato")
        self.assertIn("4 pré-candidato(s) nesta rodada", text)
        self.assertIn("26 fora do limite desta rodada", text)

    def test_full_page_is_not_reported_as_lacking_candidates(self):
        player = minimal_player()
        player["stashSaveDatas"] = [stash_slot(index, uid=1000 + index) for index in range(66)]
        editor = headless(player)
        self.assertIn("está cheio", editor.queue_summary_text(1, 0, 12, "duplicado"))


class SlotCompatibilityTests(unittest.TestCase):
    def test_amulet_slot_no_longer_shares_the_ring_prefix(self):
        """O espaço 6 é o amuleto (prefixo 60); o anel é o espaço 8 (62).

        A tabela do núcleo trazia 62 nos dois, de modo que nenhum amuleto era
        aceito no próprio espaço."""
        editor = ProEditor.__new__(ProEditor)
        self.assertEqual(editor.slot_prefixes(101, 6), {"60"})
        self.assertEqual(editor.slot_prefixes(101, 8), {"62"})
        self.assertEqual(legacy_editor.SLOT_NAMES[6], "AMULETO")
        self.assertEqual(legacy_editor.SLOT_NAMES[8], "ANEL")

    def test_core_and_intelligence_agree_on_every_slot(self):
        editor = ProEditor.__new__(ProEditor)
        for hero_key in legacy_editor.HERO_NAMES:
            for slot_index in range(10):
                self.assertEqual(
                    editor.slot_prefixes(hero_key, slot_index),
                    intelligence.slot_prefixes(hero_key, slot_index),
                    f"herói {hero_key} espaço {slot_index}",
                )
        self.assertEqual(legacy_editor.SLOT_NAMES, intelligence.SLOT_NAMES)

    def test_a_real_amulet_is_accepted_in_the_amulet_slot(self):
        amulet = next(row for row in CATALOG if str(row["ItemKey"]).startswith("60") and row["Type"] == "GEAR")
        editor = headless(minimal_player())
        item = {"ItemKey": int(amulet["ItemKey"]), "UniqueId": 1, "EnchantData": []}
        hero = {"heroKey": 101, "equippedItemIds": [0] * 10}
        self.assertTrue(editor.item_compatible_with_slot(item, hero, 6))
        self.assertFalse(editor.item_compatible_with_slot(item, hero, 8))


class RarityRankSingleSourceTests(unittest.TestCase):
    def test_rarity_rank_has_a_single_definition(self):
        """RARITY_RANK vivia como três literais independentes (legacy_editor,
        intelligence_engine, commemorative_coins._RARITY_ORDER) com os mesmos
        valores, mas sem fonte única — o mesmo padrão que já causou o bug real
        de SLOT_NAMES ter duas tabelas divergentes. As três referências agora
        devem apontar para o mesmo dict de intelligence_engine."""
        self.assertEqual(legacy_editor.RARITY_RANK, intelligence.RARITY_RANK)
        self.assertEqual(coins._RARITY_ORDER, intelligence.RARITY_RANK)


class MarketPolicySingleSourceTests(unittest.TestCase):
    def test_the_editor_shows_one_policy_date(self):
        self.assertEqual(legacy_editor.MARKET_POLICY_CHECKED_AT, market_policy.POLICY_CHECKED_AT)
        self.assertEqual(market_intelligence.POLICY_CHECKED_AT, market_policy.POLICY_CHECKED_AT)

    def test_restricted_rarities_have_a_single_definition(self):
        self.assertEqual(legacy_editor.MARKET_RESTRICTED_RARITIES, set(market_policy.HIGH_GRADE_GEAR_BLOCKED))
        self.assertEqual(legacy_editor.MARKET_SOURCE_TYPES_EXCLUDED, set(market_policy.SOURCE_TYPES_EXCLUDED))
        self.assertEqual(legacy_editor.MARKET_OFFICIAL_NEWS_URL, market_policy.OFFICIAL_NEWS_URL)

    def test_low_grade_gear_is_blocked_and_material_is_not(self):
        for grade in ("COMMON", "UNCOMMON", "RARE"):
            self.assertFalse(market_policy.market_eligibility("GEAR", grade).allowed)
            self.assertTrue(market_policy.market_eligibility("MATERIAL", grade).allowed)
        for grade in ("LEGENDARY", "IMMORTAL", "ARCANA", "BEYOND"):
            self.assertTrue(market_policy.market_eligibility("GEAR", grade).allowed)

    def test_top_grade_gear_stays_blocked_except_soulstones(self):
        for grade in ("CELESTIAL", "DIVINE", "COSMIC"):
            self.assertFalse(market_policy.market_eligibility("GEAR", grade).allowed)
            self.assertTrue(market_policy.market_eligibility("GEAR", grade, is_soulstone=True).allowed)
            self.assertTrue(market_policy.market_eligibility("MATERIAL", grade).allowed)

    def test_commemorative_coins_qualify_at_every_rarity(self):
        for definition in coins.COIN_DEFINITIONS:
            self.assertTrue(
                market_policy.market_eligibility("MATERIAL", definition.rarity).allowed,
                f"{definition.name} deveria ser elegível",
            )

    def test_user_agent_follows_the_application_version(self):
        self.assertIn(APP_VERSION, market_intelligence.MARKET_USER_AGENT)
        self.assertNotIn("3.x", market_intelligence.MARKET_USER_AGENT)

    def test_the_guarded_collector_is_the_only_implementation(self):
        self.assertIs(
            market_snapshot_guard.fetch_market_snapshot_guarded,
            market_intelligence.fetch_market_snapshot,
        )


class TradeShipGateTests(unittest.TestCase):
    def test_cube_level_is_read_from_the_known_shapes(self):
        self.assertEqual(market_policy.cube_level({"cubeSaveLevelData": {"Level": 12}}), 12)
        self.assertEqual(market_policy.cube_level({"cubeSaveLevelData": {"CubeLevel": 3}}), 3)
        self.assertEqual(market_policy.cube_level({"cubeSaveLevelData": [{"Level": 4}, {"Level": 9}]}), 9)

    def test_unknown_shapes_do_not_invent_a_level(self):
        self.assertIsNone(market_policy.cube_level({}))
        self.assertIsNone(market_policy.cube_level({"cubeSaveLevelData": {"Exp": 10}}))
        self.assertIsNone(market_policy.cube_level({"cubeSaveLevelData": {"Level": "muitos"}}))
        self.assertIsNone(market_policy.cube_level(None))

    def test_the_gate_opens_only_at_the_required_level(self):
        self.assertFalse(market_policy.trade_ship_status({"cubeSaveLevelData": {"Level": 9}}).unlocked)
        self.assertTrue(market_policy.trade_ship_status({"cubeSaveLevelData": {"Level": 10}}).unlocked)
        self.assertTrue(market_policy.trade_ship_status({"cubeSaveLevelData": {"Level": 40}}).unlocked)

    def test_a_blocked_ship_explains_itself(self):
        status = market_policy.trade_ship_status({"cubeSaveLevelData": {"Level": 7}})
        self.assertIn("nível 10", status.reason)
        self.assertTrue(status.known)

    def test_unknown_level_does_not_block_but_says_so(self):
        status = market_policy.trade_ship_status({})
        self.assertTrue(status.unlocked)
        self.assertFalse(status.known)
        self.assertIn("não reconhecido", status.reason)

    def test_editor_exposes_the_status_of_the_loaded_save(self):
        player = minimal_player()
        player["cubeSaveLevelData"] = {"Level": 7}
        self.assertFalse(headless(player).trade_ship_status().unlocked)
        player["cubeSaveLevelData"] = {"Level": 10}
        self.assertTrue(headless(player).trade_ship_status().unlocked)


class SingleEntryPointTests(unittest.TestCase):
    def test_the_intermediate_layer_is_not_an_application(self):
        """Executar a camada intermediária dava um editor sem os reforços finais."""
        import hollyedittbh_next

        self.assertFalse(hasattr(hollyedittbh_next, "main"))

    def test_the_final_layer_wires_in_the_hardened_save_file(self):
        """legacy_editor.SaveFile precisa virar VerifiedSaveFile ao importar a camada final.

        save_layer.SaveFile.save() não usa ReplaceFileW nem reverifica hash
        pós-escrita; só VerifiedSaveFile.save() (via write_save_transactionally)
        tem essas proteções. legacy_editor.py resolve o nome global SaveFile em
        tempo de chamada (import direto, sem alias), então a aplicação real só
        fica protegida se essa substituição realmente acontecer ao importar
        hollyedittbh_final — duas implementações divergentes de gravação já
        causaram o mesmo tipo de regressão silenciosa neste projeto antes."""
        import hollyedittbh_final
        import save_layer

        self.assertIs(legacy_editor.SaveFile, hollyedittbh_final.VerifiedSaveFile)
        self.assertTrue(issubclass(hollyedittbh_final.VerifiedSaveFile, save_layer.SaveFile))
        self.assertIsNot(hollyedittbh_final.VerifiedSaveFile.save, save_layer.SaveFile.save)

    def test_the_final_layer_no_longer_inspects_its_caller(self):
        source = (BASE / "hollyedittbh_final.py").read_text(encoding="utf-8")
        self.assertNotIn("_getframe", source)
        self.assertNotIn("_market_summary_capacity", source)

    def test_the_theme_is_not_reapplied_by_walking_widgets(self):
        source = (BASE / "hollyedittbh_next.py").read_text(encoding="utf-8")
        self.assertNotIn("LEGACY_COLOR_MAP", source)
        self.assertNotIn("_retint_widget", source)
        self.assertNotIn("TEXT_REPLACEMENTS", source)

    def test_every_core_colour_comes_from_the_theme(self):
        import re

        source = (BASE / "legacy_editor.py").read_text(encoding="utf-8")
        _head, _sep, body = source.partition("HERO_NAMES = {")
        self.assertEqual(re.findall(r'"(#[0-9a-fA-F]{6})"', body), [])


class MarketCandidateTests(unittest.TestCase):
    def build_editor(self, item_key, *, source_type=1):
        player = minimal_player()
        player["inventorySaveDatas"] = [inventory_slot(0, 700)]
        player["stashSaveDatas"] = [stash_slot(index) for index in range(66)]
        item = coin_item(item_key, 700)
        item["ItemGetSourceType"] = source_type
        player["itemSaveDatas"] = [item]
        return headless(player)

    def test_a_cosmic_coin_is_accepted_while_cosmic_gear_is_not(self):
        editor = self.build_editor(160010)
        accepted, reason = editor.market_candidate_status(editor.items[0])
        self.assertTrue(accepted, reason)

        gear = next(row for row in CATALOG if row["Type"] == "GEAR" and row["Rarity"] == "COSMIC")
        editor = self.build_editor(int(gear["ItemKey"]))
        accepted, reason = editor.market_candidate_status(editor.items[0])
        self.assertFalse(accepted)
        self.assertIn("COSMIC", reason)

    def test_unverifiable_origin_is_still_rejected(self):
        editor = self.build_editor(160010, source_type=0)
        accepted, reason = editor.market_candidate_status(editor.items[0])
        self.assertFalse(accepted)
        self.assertIn("origem local", reason)

    def test_the_round_limit_does_not_hide_the_size_of_the_pool(self):
        player = minimal_player()
        player["inventorySaveDatas"] = [inventory_slot(index, 800 + index) for index in range(12)]
        player["stashSaveDatas"] = [stash_slot(index) for index in range(66)]
        player["itemSaveDatas"] = [coin_item(160010, 800 + index) for index in range(12)]
        editor = headless(player)
        rows = editor.market_candidates(1, 20)
        self.assertEqual(len(rows), editor.configured_market_slots())
        self.assertEqual(editor.last_market_pool, 12)
        self.assertIn("fora do limite desta rodada", editor.queue_summary_text(1, len(rows), 12, "pré-candidato"))


if __name__ == "__main__":
    unittest.main()
