import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import save_layer
from save_layer import SaveFile
from tbh_save_editor import (
    GAME_SAVE_DIR,
    HERO_NAMES,
    ITEM_TYPE_LABELS,
    RARITY_FILTER_ALL,
    RARITY_LABELS,
    ProEditor,
    MARKET_RESTRICTED_RARITIES,
    hero_portrait_candidates,
    item_matches_filters,
    normalize_search_text,
    validate_dump_structure,
)


def minimal_player():
    return {
        "itemSaveDatas": [],
        "heroSaveDatas": [],
        "inventorySaveDatas": [],
        "stashSaveDatas": [],
        "remakeTradingStashSaveDatas": [],
    }


def es3_root(account=None, player=None, valid_integrity=True):
    account = account or {"ownerSteamId": "123456"}
    player = player or minimal_player()
    account_json = json.dumps(account, ensure_ascii=False, separators=(",", ":"))
    player_json = json.dumps(player, ensure_ascii=False, separators=(",", ":"))
    system_info = save_layer._system_info_value(account_json, player_json, account["ownerSteamId"])
    if not valid_integrity:
        system_info = "invalid"
    return {
        "AccountSaveData": {"__type": "System.String", "value": account_json},
        "PlayerSaveData": {"__type": "System.String", "value": player_json},
        "SystemInfo": {"__type": "System.String", "value": system_info},
    }


def headless_editor(data, database):
    editor = ProEditor.__new__(ProEditor)
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
    editor.mark_dirty = lambda *_args, **_kwargs: None
    editor.refresh_all = lambda: None
    editor.rebuild_item_index()
    editor.original_item_uids = set(editor.items_by_uid)
    return editor


def storage_slot(index, uid=0, stash=False):
    return {
        "Index": index,
        "ItemUniqueId": uid,
        "IsUnLock" if stash else "IsUnlock": True,
        "IsUnlockedByRune": False,
    }


class CryptoTests(unittest.TestCase):
    def test_pure_python_aes_matches_fips_197_vector(self):
        key = bytes.fromhex("000102030405060708090a0b0c0d0e0f")
        plaintext = bytes.fromhex("00112233445566778899aabbccddeeff")
        ciphertext = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")
        round_keys = save_layer._key_expansion(key)
        self.assertEqual(save_layer._aes_encrypt_block(plaintext, round_keys), ciphertext)
        self.assertEqual(save_layer._aes_decrypt_block(ciphertext, round_keys), plaintext)

    def test_es3_round_trip_integrity_and_timestamped_backup(self):
        source = SaveFile(es3_root())
        self.assertTrue(source.integrity_valid)
        with tempfile.TemporaryDirectory() as temp_dir:
            save_path = Path(temp_dir) / "SaveFile_Live.es3"
            save_path.write_bytes(source.to_es3_bytes())
            loaded = SaveFile.load(save_path)
            loaded.player["level"] = 42
            loaded.save(save_path, backup=True)

            self.assertIsNotNone(loaded.last_backup_path)
            self.assertTrue(Path(loaded.last_backup_path).is_file())
            self.assertEqual(SaveFile.load(save_path).player["level"], 42)
            self.assertNotIn("level", SaveFile.load(loaded.last_backup_path).player)
            self.assertTrue(SaveFile.load(save_path).integrity_valid)

    def test_invalid_source_integrity_is_detected_and_repaired_on_save(self):
        save = SaveFile(es3_root(valid_integrity=False))
        self.assertFalse(save.integrity_valid)
        repaired = SaveFile(json.loads(save_layer.es3_decrypt(save.to_es3_bytes()).decode("utf-8")))
        self.assertTrue(repaired.integrity_valid)


class DataValidationTests(unittest.TestCase):
    def test_portuguese_search_is_accent_and_case_insensitive(self):
        self.assertEqual(normalize_search_text("  CÓSMICO  "), "cosmico")
        row = {
            "ItemKey": "300001",
            "Name": "Arcane Sword",
            "Rarity": "COSMIC",
            "Type": "GEAR",
            "StatTypes": ["CriticalDamage"],
        }
        self.assertTrue(item_matches_filters(row, "espada cosmico", RARITY_FILTER_ALL, ITEM_TYPE_LABELS["GEAR"]))
        self.assertTrue(item_matches_filters(row, "300001 dano critico", RARITY_LABELS["COSMIC"], ITEM_TYPE_LABELS["GEAR"]))
        self.assertFalse(item_matches_filters(row, "arco", RARITY_FILTER_ALL, ITEM_TYPE_LABELS["GEAR"]))

    def test_all_heroes_have_portuguese_names_and_portraits(self):
        self.assertEqual(set(HERO_NAMES), {101, 201, 301, 401, 501, 601})
        self.assertTrue(all("Hero" not in name for name in HERO_NAMES.values()))
        for hero_key in HERO_NAMES:
            self.assertTrue(any(path.is_file() for path in hero_portrait_candidates(hero_key)))

    def test_materials_never_receive_enchantments(self):
        base = Path(__file__).resolve().parent
        cache = json.loads((base / "tbh_items_cache.json").read_text(encoding="utf-8"))["items"]
        editor = headless_editor({"account": {}, "player": minimal_player()}, cache)
        material_key = int(next(row["ItemKey"] for row in cache if row.get("Type") == "MATERIAL"))
        item = editor.new_item(material_key, enchanted=True)
        self.assertEqual(item["EnchantData"], [])
        self.assertEqual(editor.expected_enchant_slot_count(item), 0)

    def test_open_dialog_starts_in_the_standard_game_save_folder(self):
        editor = ProEditor.__new__(ProEditor)
        editor.path = None
        editor.confirm_discard_or_save = lambda: True
        editor.load_dump = lambda _path: None
        # A pasta do jogo só existe no Windows com o TBH instalado; sem simular
        # a presença dela, este teste passava por acidente em qualquer host.
        with patch("tbh_save_editor.GAME_SAVE_DIR") as game_dir, patch(
            "tbh_save_editor.DEFAULT_SAVE_FILE"
        ) as save_file, patch(
            "tbh_save_editor.filedialog.askopenfilename", return_value=""
        ) as dialog:
            game_dir.is_dir.return_value = True
            game_dir.__str__ = lambda _self: str(GAME_SAVE_DIR)
            save_file.is_file.return_value = True
            save_file.name = "SaveFile_Live.es3"
            editor.open_dump()
        self.assertEqual(Path(dialog.call_args.kwargs["initialdir"]), GAME_SAVE_DIR)
        self.assertEqual(dialog.call_args.kwargs.get("initialfile"), "SaveFile_Live.es3")

    def test_dump_structure_requires_account_player_and_object_records(self):
        valid = {"account": {}, "player": minimal_player()}
        self.assertIs(validate_dump_structure(valid), valid)
        with self.assertRaisesRegex(ValueError, "account"):
            validate_dump_structure({"player": minimal_player()})
        invalid = copy.deepcopy(valid)
        invalid["player"]["itemSaveDatas"] = ["not-an-object"]
        with self.assertRaisesRegex(ValueError, r"itemSaveDatas\[0\]"):
            validate_dump_structure(invalid)

    def test_rarity_specific_enchant_layouts(self):
        base = Path(__file__).resolve().parent
        cache = json.loads((base / "tbh_items_cache.json").read_text(encoding="utf-8"))["items"]
        editor = headless_editor({"account": {}, "player": minimal_player()}, cache)

        keys_by_rarity = {}
        for row in cache:
            if row.get("Type") == "GEAR" and row.get("Rarity") in {"RARE", "IMMORTAL", "COSMIC"}:
                keys_by_rarity.setdefault(row["Rarity"], int(row["ItemKey"]))
        expected = {
            "RARE": (2, [2, 0, 0], [3, 3]),
            "IMMORTAL": (4, [2, 2, 0], [3, 3, 4, 4]),
            "COSMIC": (6, [2, 2, 2], [1, 1, 2, 2, 3, 3]),
        }
        for rarity, (slot_count, counts, recipes) in expected.items():
            item = editor.new_item(keys_by_rarity[rarity], enchanted=True)
            self.assertEqual(len(item["EnchantData"]), slot_count)
            self.assertEqual(item["EnchantCount"], counts)
            self.assertEqual([enchant["RecipeType"] for enchant in item["EnchantData"]], recipes)

    def test_invalid_enchant_is_repaired_without_remaining_errors(self):
        base = Path(__file__).resolve().parent
        cache = json.loads((base / "tbh_items_cache.json").read_text(encoding="utf-8"))["items"]
        rare_gear = next(row for row in cache if row.get("Type") == "GEAR" and row.get("Rarity") == "RARE")
        player = minimal_player()
        editor = headless_editor({"account": {}, "player": player}, cache)
        item = editor.new_item(int(rare_gear["ItemKey"]), enchanted=True)
        item["EnchantData"][0]["RecipeType"] = 999
        player["itemSaveDatas"] = [item]
        player["inventorySaveDatas"] = [storage_slot(0, item["UniqueId"])]
        editor.items = player["itemSaveDatas"]
        editor.rebuild_item_index()

        before = editor.validate_save()
        self.assertTrue(any(issue["code"] == "recipe_type" for issue in before))
        editor.repair_save(show_message=False)
        remaining_errors = [issue for issue in editor.validate_save() if issue["severity"] == "ERRO"]
        self.assertEqual(remaining_errors, [])

    def test_market_queue_excludes_restricted_local_and_session_items(self):
        database = [
            {"ItemKey": "300101", "Name": "Beyond Sword", "Rarity": "BEYOND", "Type": "GEAR", "StatTypes": []},
            {"ItemKey": "300102", "Name": "Celestial Sword", "Rarity": "CELESTIAL", "Type": "GEAR", "StatTypes": []},
            {"ItemKey": "190003", "Name": "Soulstone - Hell", "Rarity": "BEYOND", "Type": "MATERIAL", "StatTypes": []},
            {"ItemKey": "300103", "Name": "Local Sword", "Rarity": "LEGENDARY", "Type": "GEAR", "StatTypes": []},
        ]
        items = [
            {"ItemKey": 300101, "UniqueId": 1, "ItemGetSourceType": 5, "IsBlocked": False, "IsChaotic": False, "EnchantData": []},
            {"ItemKey": 300102, "UniqueId": 2, "ItemGetSourceType": 5, "IsBlocked": False, "IsChaotic": False, "EnchantData": []},
            {"ItemKey": 190003, "UniqueId": 3, "ItemGetSourceType": 5, "IsBlocked": False, "IsChaotic": False, "EnchantData": []},
            {"ItemKey": 300103, "UniqueId": 4, "ItemGetSourceType": 0, "IsBlocked": False, "IsChaotic": False, "EnchantData": []},
        ]
        player = minimal_player()
        player["itemSaveDatas"] = items
        player["inventorySaveDatas"] = [storage_slot(i, i + 1) for i in range(4)]
        player["stashSaveDatas"] = [storage_slot(396 + i, 0, stash=True) for i in range(10)]
        editor = headless_editor({"account": {}, "player": player}, database)

        candidates = editor.market_candidates(7, 10)
        self.assertEqual({row["item"]["UniqueId"] for row in candidates}, {1, 3})
        self.assertEqual(MARKET_RESTRICTED_RARITIES, {"COSMIC", "DIVINE", "CELESTIAL"})

        editor.session_modified_uids.add(1)
        self.assertEqual([row["item"]["UniqueId"] for row in editor.market_candidates(7, 10)], [3])

    def test_recycle_queue_keeps_best_duplicate_and_never_deletes(self):
        database = [
            {"ItemKey": "500101", "Name": "Rare Helmet", "Rarity": "RARE", "Type": "GEAR", "StatTypes": ["Armor"]},
            {"ItemKey": "500102", "Name": "Other Helmet", "Rarity": "RARE", "Type": "GEAR", "StatTypes": ["Armor"]},
        ]
        best_enchant = [{"StatModKey": 100501, "Tier": 30, "Value": 100, "RecipeType": 3, "ModType": 0, "MaterialKey": 112001, "StatType": 5, "EnchantVersion": None}]
        items = [
            {"ItemKey": 500101, "UniqueId": 11, "ItemGetSourceType": 5, "IsBlocked": False, "IsChaotic": False, "EnchantData": best_enchant},
            {"ItemKey": 500101, "UniqueId": 12, "ItemGetSourceType": 5, "IsBlocked": False, "IsChaotic": False, "EnchantData": []},
            {"ItemKey": 500101, "UniqueId": 13, "ItemGetSourceType": 5, "IsBlocked": False, "IsChaotic": False, "EnchantData": []},
            {"ItemKey": 500102, "UniqueId": 14, "ItemGetSourceType": 5, "IsBlocked": False, "IsChaotic": False, "EnchantData": []},
        ]
        player = minimal_player()
        player["itemSaveDatas"] = items
        player["inventorySaveDatas"] = [storage_slot(i, 11 + i) for i in range(4)]
        player["stashSaveDatas"] = [storage_slot(330 + i, 0, stash=True) for i in range(10)]
        editor = headless_editor({"account": {}, "player": player}, database)

        rows = editor.recycle_candidates(6, 10, "LEGENDARY")
        self.assertEqual({row["item"]["UniqueId"] for row in rows}, {12, 13})
        self.assertEqual(len(player["itemSaveDatas"]), 4)
        self.assertEqual(editor.apply_storage_queue(rows, 6), 2)
        self.assertEqual(len(player["itemSaveDatas"]), 4)

    def test_campaign_unlocks_only_known_local_access(self):
        player = minimal_player()
        player["commonSaveData"] = {
            "version": "1.01.05",
            "TutorialCleared": [True, False],
            "isFirstPlay": True,
            "isOpeningDirectionPlayed": False,
            "maxCompletedStage": 4310,
            "currentStageKey": 4309,
        }
        player["heroSaveDatas"] = [{"heroKey": 101, "IsUnLock": False, "unlockedAttributeGroupKeys": [], "equippedItemIds": [0] * 10}]
        player["PetSaveData"] = [{"PetKey": 1, "IsUnlock": False, "IsViewed": False}]
        player["cubeRecipeSaveDatas"] = [{"CubeKey": 100001, "MaxUnlockRecipeKey": 100001}]
        editor = headless_editor({"account": {}, "player": player}, [])

        before_stage = player["commonSaveData"]["maxCompletedStage"]
        changes = editor.campaign_access_changes(apply=False)
        self.assertGreaterEqual(len(changes), 5)
        editor.campaign_access_changes(apply=True)
        self.assertEqual(player["commonSaveData"]["maxCompletedStage"], before_stage)
        self.assertEqual(player["commonSaveData"]["TutorialCleared"], [True, True])
        self.assertTrue(player["heroSaveDatas"][0]["IsUnLock"])
        self.assertEqual(player["cubeRecipeSaveDatas"][0]["MaxUnlockRecipeKey"], 100081)

    def test_auto_equip_all_uses_each_replacement_once(self):
        database = [
            {"ItemKey": "300101", "Name": "Common Sword", "Rarity": "COMMON", "Type": "GEAR", "StatTypes": []},
            {"ItemKey": "300102", "Name": "Cosmic Sword", "Rarity": "COSMIC", "Type": "GEAR", "StatTypes": []},
        ]
        items = [
            {"ItemKey": 300101, "UniqueId": 21, "ItemGetSourceType": 5, "IsBlocked": False, "IsChaotic": False, "EnchantData": []},
            {"ItemKey": 300102, "UniqueId": 22, "ItemGetSourceType": 5, "IsBlocked": False, "IsChaotic": False, "EnchantData": []},
        ]
        player = minimal_player()
        player["itemSaveDatas"] = items
        player["heroSaveDatas"] = [{"heroKey": 101, "equippedItemIds": [21] + [0] * 9}]
        player["inventorySaveDatas"] = [storage_slot(0, 22)]
        editor = headless_editor({"account": {}, "player": player}, database)

        plan = editor.build_auto_equip_all_plan()
        self.assertEqual([(row["slot_index"], row["replacement_uid"]) for row in plan], [(0, 22)])
        self.assertEqual(editor.apply_auto_equip_all_plan(plan), 1)
        self.assertEqual(player["heroSaveDatas"][0]["equippedItemIds"][0], 22)
        self.assertEqual(player["inventorySaveDatas"][0]["ItemUniqueId"], 21)

    def test_single_equipment_recommendation_can_be_applied(self):
        database = [
            {"ItemKey": "300101", "Name": "Espada comum", "Rarity": "COMMON", "Type": "GEAR", "StatTypes": []},
            {"ItemKey": "300102", "Name": "Espada cósmica", "Rarity": "COSMIC", "Type": "GEAR", "StatTypes": []},
        ]
        items = [
            {"ItemKey": 300101, "UniqueId": 31, "ItemGetSourceType": 5, "IsBlocked": False, "IsChaotic": False, "EnchantData": []},
            {"ItemKey": 300102, "UniqueId": 32, "ItemGetSourceType": 5, "IsBlocked": False, "IsChaotic": False, "EnchantData": []},
        ]
        player = minimal_player()
        hero = {"heroKey": 101, "equippedItemIds": [31] + [0] * 9}
        player["itemSaveDatas"] = items
        player["heroSaveDatas"] = [hero]
        player["inventorySaveDatas"] = [storage_slot(0, 32)]
        editor = headless_editor({"account": {}, "player": player}, database)

        recommendations = editor.build_auto_equip_plan(hero)
        self.assertEqual(len(recommendations), 1)
        self.assertEqual(editor.apply_auto_equip_plan(hero, [recommendations[0]]), 1)
        self.assertEqual(hero["equippedItemIds"][0], 32)
        self.assertEqual(player["inventorySaveDatas"][0]["ItemUniqueId"], 31)

    def test_market_page_can_be_filled_with_safe_existing_candidates(self):
        database = [
            {"ItemKey": "300101", "Name": "Espada Beyond", "Rarity": "BEYOND", "Type": "GEAR", "StatTypes": []},
            {"ItemKey": "300102", "Name": "Espada Imortal", "Rarity": "IMMORTAL", "Type": "GEAR", "StatTypes": []},
        ]
        items = [
            {"ItemKey": 300101, "UniqueId": 41, "ItemGetSourceType": 5, "IsBlocked": False, "IsChaotic": False, "EnchantData": []},
            {"ItemKey": 300102, "UniqueId": 42, "ItemGetSourceType": 5, "IsBlocked": False, "IsChaotic": False, "EnchantData": []},
        ]
        player = minimal_player()
        player["itemSaveDatas"] = items
        player["inventorySaveDatas"] = [storage_slot(0, 41), storage_slot(1, 42)]
        player["stashSaveDatas"] = [storage_slot(396 + index, 0, stash=True) for index in range(66)]
        editor = headless_editor({"account": {}, "player": player}, database)

        candidates = editor.market_candidates(7, 66)
        self.assertEqual({row["item"]["UniqueId"] for row in candidates}, {41, 42})
        self.assertEqual(editor.apply_storage_queue(candidates, 7), 2)
        filled = {slot["ItemUniqueId"] for slot in player["stashSaveDatas"] if slot["ItemUniqueId"]}
        self.assertEqual(filled, {41, 42})

    def test_created_desired_item_stays_out_of_market_candidates(self):
        database = [{"ItemKey": "300101", "Name": "Espada local", "Rarity": "BEYOND", "Type": "GEAR", "StatTypes": []}]
        player = minimal_player()
        player["inventorySaveDatas"] = [storage_slot(0)]
        player["stashSaveDatas"] = [storage_slot(396 + index, 0, stash=True) for index in range(66)]
        editor = headless_editor({"account": {}, "player": player}, database)
        item = editor.new_item(300101, enchanted=False)
        player["itemSaveDatas"].append(item)
        editor.items.append(item)
        editor.items_by_uid[item["UniqueId"]] = item
        editor.session_created_uids.add(item["UniqueId"])
        player["inventorySaveDatas"][0]["ItemUniqueId"] = item["UniqueId"]

        self.assertEqual(editor.market_candidates(7, 66), [])

    def test_protected_mode_limits_bulk_item_creation(self):
        database = [{"ItemKey": "300101", "Name": "Sword", "Rarity": "COMMON", "Type": "GEAR", "StatTypes": []}]
        player = minimal_player()
        player["inventorySaveDatas"] = [storage_slot(i) for i in range(20)]
        editor = headless_editor({"account": {}, "player": player}, database)
        with patch("tbh_save_editor.messagebox.showerror") as error:
            self.assertEqual(editor.create_item(300101, 11), [])
        error.assert_called_once()

    def test_protected_save_refuses_when_game_is_open(self):
        editor = ProEditor.__new__(ProEditor)
        editor.path = Path("SaveFile_Live.es3")
        editor.data = {"account": {}, "player": minimal_player()}
        editor.protected_mode = True
        editor.loaded_file_signature = None
        with patch("tbh_save_editor.taskbar_hero_is_running", return_value=True), patch(
            "tbh_save_editor.messagebox.showerror"
        ) as error:
            editor.save_dump()
        error.assert_called_once()


if __name__ == "__main__":
    unittest.main()
