import itertools
import json
import random
import unittest
from unittest.mock import patch

from legacy_editor import STASH_PAGE_SIZE as PAGE
from catalog_update import validate_catalog_candidate
from intelligence_engine import greedy_assignment, optimal_unique_assignment, score_item, slot_prefixes
from market_intelligence import MarketQuote, market_eligibility, market_priority, parse_market_search_html

from hollyedittbh_next import EnhancedProEditor, _load_profiles


def minimal_player():
    return {
        "itemSaveDatas": [],
        "heroSaveDatas": [],
        "inventorySaveDatas": [],
        "stashSaveDatas": [],
        "remakeTradingStashSaveDatas": [],
    }


def storage_slot(index, uid=0, stash=False, unlocked=True):
    return {
        "Index": index,
        "ItemUniqueId": uid,
        "IsUnLock" if stash else "IsUnlock": unlocked,
        "IsUnlockedByRune": False,
    }


def enhanced_headless(data, database):
    editor = EnhancedProEditor.__new__(EnhancedProEditor)
    editor.data = data
    editor.items = list(data["player"].get("itemSaveDatas", []))
    editor.db = database
    editor.db_by_key = {str(item["ItemKey"]): item for item in database}
    editor.loaded_kind = "json"
    editor.save_file = None
    editor.selected_item = None
    editor.original_item_uids = set()
    editor.session_created_uids = set()
    editor.session_modified_uids = set()
    editor.protected_mode = True
    editor.hero_profiles = _load_profiles()
    editor.market_snapshot = None
    editor.mark_dirty = lambda *_args, **_kwargs: None
    editor.refresh_all = lambda: None
    editor.rebuild_item_index()
    editor.original_item_uids = set(editor.items_by_uid)
    return editor


class IntelligenceEngineTests(unittest.TestCase):
    def test_accessory_slot_mapping_restores_amulet(self):
        self.assertEqual(slot_prefixes(101, 6), {"60"})
        self.assertEqual(slot_prefixes(101, 7), {"61"})
        self.assertEqual(slot_prefixes(101, 8), {"62"})
        self.assertEqual(slot_prefixes(101, 9), {"63"})

    def test_strong_legendary_can_beat_blank_immortal(self):
        weights = {1: 1.5}
        legendary = {
            "IsChaotic": False,
            "EnchantData": [
                {"Tier": 30, "StatType": 1, "StatModKey": 100101, "Value": 100},
                {"Tier": 30, "StatType": 1, "StatModKey": 100101, "Value": 100},
            ],
        }
        blank = {"IsChaotic": False, "EnchantData": []}
        legendary_score = score_item(legendary, {"Rarity": "LEGENDARY", "Name": "Lv. 80 Test"}, weights)
        immortal_score = score_item(blank, {"Rarity": "IMMORTAL", "Name": "Lv. 80 Test"}, weights)
        self.assertGreater(legendary_score.total, immortal_score.total)
        self.assertGreater(legendary_score.affinity, 0)

    def test_exact_assignment_beats_sequential_counterexample(self):
        matrix = [[0.8, 0.7], [0.8, 0.0]]
        self.assertEqual(greedy_assignment(matrix).total_score, 0.8)
        exact = optimal_unique_assignment(matrix)
        self.assertEqual(exact.total_score, 1.5)
        self.assertEqual(exact.item_by_hero, (1, 0))

    def test_exact_assignment_matches_bruteforce_random_matrices(self):
        random.seed(7331)
        for _ in range(60):
            hero_count = random.randint(1, 5)
            item_count = random.randint(1, 6)
            matrix = [
                [None if random.random() < 0.2 else round(random.random() * 3, 3) for _ in range(item_count)]
                for _ in range(hero_count)
            ]
            expected = -1.0
            for assignment in itertools.product(range(-1, item_count), repeat=hero_count):
                real = [index for index in assignment if index >= 0]
                if len(real) != len(set(real)):
                    continue
                score = 0.0
                valid = True
                for hero_index, item_index in enumerate(assignment):
                    if item_index < 0:
                        continue
                    value = matrix[hero_index][item_index]
                    if value is None:
                        valid = False
                        break
                    score += value
                if valid:
                    expected = max(expected, score)
            actual = optimal_unique_assignment(matrix)
            self.assertAlmostEqual(actual.total_score, expected, places=6)

    def test_minimum_score_prevents_hero_downgrade(self):
        matrix = [[1.0, 1.2], [2.0, 0.1]]
        result = optimal_unique_assignment(matrix, minimum_scores=[1.0, 2.0])
        self.assertEqual(result.item_by_hero, (1, 0))
        self.assertEqual(result.total_score, 3.2)


class EnhancedAutoEquipTests(unittest.TestCase):
    def test_global_plan_is_not_save_order_greedy_and_fills_empty_slots(self):
        database = [
            {"ItemKey": "500101", "Name": "Helmet A", "Rarity": "LEGENDARY", "Type": "GEAR", "StatTypes": []},
            {"ItemKey": "500102", "Name": "Helmet B", "Rarity": "LEGENDARY", "Type": "GEAR", "StatTypes": []},
        ]
        item_a = {
            "ItemKey": 500101, "UniqueId": 101, "ItemGetSourceType": 5, "IsBlocked": False, "IsChaotic": False,
            "EnchantData": [{"Tier": 30, "StatType": 1, "StatModKey": 100101, "Value": 100}],
        }
        item_b = {
            "ItemKey": 500102, "UniqueId": 102, "ItemGetSourceType": 5, "IsBlocked": False, "IsChaotic": False,
            "EnchantData": [{"Tier": 30, "StatType": 4, "StatModKey": 100401, "Value": 100}],
        }
        player = minimal_player()
        player["itemSaveDatas"] = [item_a, item_b]
        player["heroSaveDatas"] = [
            {"heroKey": 101, "equippedItemIds": [0] * 10},
            {"heroKey": 201, "equippedItemIds": [0] * 10},
        ]
        player["inventorySaveDatas"] = [storage_slot(0, 101), storage_slot(1, 102)]
        editor = enhanced_headless({"account": {}, "player": player}, database)

        plan = editor.build_auto_equip_all_plan()
        helmet_rows = [row for row in plan if row["slot_index"] == 2]
        by_hero = {row["hero_key"]: row["replacement_uid"] for row in helmet_rows}
        self.assertEqual(by_hero, {101: 102, 201: 101})
        self.assertEqual(editor.apply_auto_equip_all_plan(plan), 2)
        self.assertEqual(player["heroSaveDatas"][0]["equippedItemIds"][2], 102)
        self.assertEqual(player["heroSaveDatas"][1]["equippedItemIds"][2], 101)
        self.assertEqual([slot["ItemUniqueId"] for slot in player["inventorySaveDatas"]], [0, 0])


class MarketIntelligenceTests(unittest.TestCase):
    def test_market_policy_blocks_low_grade_gear_but_not_material(self):
        self.assertFalse(market_eligibility("GEAR", "RARE").allowed)
        self.assertTrue(market_eligibility("MATERIAL", "RARE").allowed)
        self.assertFalse(market_eligibility("GEAR", "CELESTIAL").allowed)

    def test_enchantments_never_improve_sale_priority(self):
        quote = MarketQuote("Sword", 12, "$1.00", 1.0, "https://example.invalid")
        clean = market_priority(quote, rarity_rank=6, item_type="GEAR", has_enchantments=False)
        enchanted = market_priority(quote, rarity_rank=6, item_type="GEAR", has_enchantments=True)
        self.assertGreater(clean, enchanted)

    def test_market_html_parser_extracts_quote_without_login(self):
        page = """Found 913 results
        <a class="market_listing_row_link" href="https://steamcommunity.com/market/listings/3678970/Dimensional%20Gloves%20%28Divine%29%20A">
        <span class="market_listing_item_name">Dimensional Gloves (Divine) A</span>
        <span class="market_listing_num_listings_qty">12</span>
        <span class="normal_price"><span class="market_listing_price_with_fee">$1.19 USD</span></span>
        </a>"""
        quotes, total = parse_market_search_html(page)
        self.assertEqual(total, 913)
        self.assertEqual(len(quotes), 1)
        self.assertEqual(quotes[0].hash_name, "Dimensional Gloves (Divine) A")
        self.assertEqual(quotes[0].sell_listings, 12)
        self.assertAlmostEqual(quotes[0].price_value, 1.19)

    def test_enhanced_market_queue_is_limited_to_listing_slots(self):
        database = [
            {"ItemKey": str(300100 + index), "Name": f"Tradable {index}", "Rarity": "LEGENDARY", "Type": "GEAR", "StatTypes": []}
            for index in range(8)
        ]
        items = [
            {"ItemKey": 300100 + index, "UniqueId": index + 1, "ItemGetSourceType": 5, "IsBlocked": False, "IsChaotic": False, "EnchantData": []}
            for index in range(8)
        ]
        player = minimal_player()
        player["itemSaveDatas"] = items
        player["inventorySaveDatas"] = [storage_slot(index, index + 1) for index in range(8)]
        player["stashSaveDatas"] = [storage_slot(PAGE * 6 + index, 0, stash=True) for index in range(PAGE)]
        editor = enhanced_headless({"account": {}, "player": player}, database)
        with patch.dict("os.environ", {"HOLLYEDIT_MARKET_SLOTS": "4"}):
            candidates = editor.market_candidates(7, PAGE)
        self.assertEqual(len(candidates), 4)


class CatalogSafetyTests(unittest.TestCase):
    @staticmethod
    def rows(count):
        rarities = ["COMMON", "UNCOMMON", "RARE", "LEGENDARY", "IMMORTAL", "ARCANA"]
        return [
            {
                "ItemKey": str(index + 1),
                "Name": f"Item {index + 1}",
                "Rarity": rarities[index % len(rarities)],
                "Type": "GEAR" if index % 2 else "MATERIAL",
                "StatTypes": [],
            }
            for index in range(count)
        ]

    def test_partial_catalog_is_rejected(self):
        previous = self.rows(5875)
        result = validate_catalog_candidate(self.rows(700), previous)
        self.assertFalse(result.ok)
        self.assertIn("parcial", result.reason)

    def test_large_regression_is_rejected_even_above_absolute_minimum(self):
        previous = self.rows(5875)
        result = validate_catalog_candidate(self.rows(4000), previous)
        self.assertFalse(result.ok)
        self.assertIn("regressão", result.reason)

    def test_normal_growth_is_accepted(self):
        previous = self.rows(5875)
        result = validate_catalog_candidate(self.rows(5900), previous)
        self.assertTrue(result.ok)


if __name__ == "__main__":
    unittest.main()
