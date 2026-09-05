"""Regressões de gravação e recarga. Fixtures sintéticas, sem executar o jogo."""
import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import hollyedittbh_final as final
import legacy_editor as legacy
import persistence_audit as audit
import platform_support
from save_layer import SaveFile
from test_final_audit_v331 import final_headless
from test_hollyedittbh import es3_root, minimal_player, storage_slot


DATABASE = [
    {"ItemKey": "160001", "Name": "Coin", "Type": "MATERIAL", "Rarity": "COMMON"},
    {"ItemKey": "300101", "Name": "Sword", "Type": "GEAR", "Rarity": "RARE"},
]


def player_fixture():
    player = minimal_player()
    player["inventorySaveDatas"] = [storage_slot(i) for i in range(8)]
    player["stashSaveDatas"] = [storage_slot(i, stash=True) for i in range(legacy.STASH_PAGE_SIZE)]
    player["heroSaveDatas"] = [{"heroKey": 101, "equippedItemIds": [0] * 10}]
    player["unknownFutureField"] = {"revision": "1.02", "dados": ["ação", 7]}
    return player


class PersistenceFixture(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.folder = Path(directory.name)
        self.path = self.folder / "SaveFile_Live.es3"
        root = es3_root(player=player_fixture())
        root["FutureEnvelope"] = {"__type": "System.String", "value": "preservar"}
        self.path.write_bytes(SaveFile(root).to_es3_bytes())
        self.original = self.path.read_bytes()
        self.save = final.VerifiedSaveFile.load(self.path)
        self.editor = final_headless({"account": self.save.account, "player": self.save.player}, DATABASE)
        self.editor.path = self.path
        self.editor.save_file = self.save
        self.editor.loaded_kind = "es3"
        self.editor.loaded_file_signature = self.editor.file_signature(self.path)
        self.editor.protected_mode = False
        self.editor.dirty = True
        self.editor.mark_clean = lambda: setattr(self.editor, "dirty", False)
        self.editor.status_var = Mock()
        self.editor._receipt_directory = lambda: self.folder / "receipts"
        self.info = self.enterContext(patch.object(legacy.messagebox, "showinfo"))
        self.warning = self.enterContext(patch.object(legacy.messagebox, "showwarning"))
        self.error = self.enterContext(patch.object(legacy.messagebox, "showerror"))
        self.enterContext(patch.object(legacy.messagebox, "askyesno", return_value=True))
        self.running = self.enterContext(patch.object(legacy, "taskbar_hero_is_running", return_value=False))

    def coin(self):
        return self.editor.create_item(160001)[0]

    def receipt(self):
        return audit.read_receipt(self.editor._receipt_directory(), self.path)


class SaveLifecycleTests(PersistenceFixture):
    def test_create_duplicate_move_equip_save_and_reopen_preserves_every_record(self):
        coin = self.coin()
        self.editor.duplicate_item(coin, 2)
        gear = self.editor.create_item(300101)[0]
        self.assertFalse(any(self.editor.enchant_is_filled(e) for e in gear["EnchantData"]))
        self.assertTrue(self.editor.move_item(coin, "Armazem 1"))
        hero = self.editor.data["player"]["heroSaveDatas"][0]
        self.assertTrue(self.editor.equip_item(hero, 0, gear))
        expected = copy.deepcopy(self.editor.data)
        self.editor.save_dump()
        self.error.assert_not_called()
        loaded = final.VerifiedSaveFile.load(self.path)
        self.assertTrue(loaded.integrity_valid)
        self.assertEqual(loaded.account, expected["account"])
        self.assertEqual(loaded.player, expected["player"])
        self.assertEqual(loaded._es3["FutureEnvelope"]["value"], "preservar")
        self.assertEqual(Path(self.save.last_backup_path).read_bytes(), self.original)
        self.assertEqual(len(self.receipt()["items"]), 4)
        self.assertFalse(self.editor.dirty)

    def test_game_running_blocks_save_with_protected_mode_disabled(self):
        self.coin()
        self.running.return_value = True
        self.editor.save_dump()
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertTrue(self.editor.dirty)
        self.assertIsNone(self.receipt())
        self.error.assert_called_once()

    def test_game_opened_during_validation_also_blocks(self):
        self.coin()
        self.running.side_effect = [False, True]
        self.editor.save_dump()
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertTrue(self.editor.dirty)
        self.error.assert_called_once()

    def test_unknown_source_signature_blocks_with_protected_mode_disabled(self):
        self.editor.loaded_file_signature = None
        self.editor.save_dump()
        self.assertEqual(self.path.read_bytes(), self.original)
        self.error.assert_called_once()

    def test_external_save_change_blocks_with_protected_mode_disabled(self):
        external = final.VerifiedSaveFile.load(self.path)
        external.player["other_progress"] = 99
        external.save(self.path)
        external_bytes = self.path.read_bytes()
        self.editor.save_dump()
        self.assertEqual(self.path.read_bytes(), external_bytes)
        self.assertTrue(self.editor.dirty)
        self.error.assert_called_once()

    def test_auxiliary_receipt_failure_does_not_report_save_failure(self):
        self.coin()
        with patch.object(audit, "write_receipt", side_effect=OSError("sem espaço")):
            self.editor.save_dump()
        self.assertEqual(len(final.VerifiedSaveFile.load(self.path).player["itemSaveDatas"]), 1)
        self.assertFalse(self.editor.dirty)
        self.error.assert_not_called()
        self.assertIn("registro de conferência não pôde", self.info.call_args.args[1])

    def test_failed_reread_keeps_dirty_and_creates_no_receipt(self):
        self.coin()
        with patch.object(final.VerifiedSaveFile, "load", side_effect=OSError("releitura falhou")):
            self.editor.save_dump()
        self.assertTrue(self.editor.dirty)
        self.assertIsNone(self.receipt())
        self.error.assert_called_once()
        self.assertEqual(Path(self.save.last_backup_path).read_bytes(), self.original)

    def test_nan_is_rejected_before_the_original_file_is_touched(self):
        self.save.player["unknownFutureField"]["invalid"] = float("nan")
        with self.assertRaises(ValueError):
            self.save.save(self.path)
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertIsNone(self.save.last_backup_path)

    def test_json_export_cannot_overwrite_the_game_save(self):
        with patch.object(legacy.filedialog, "asksaveasfilename", return_value=str(self.path)):
            self.editor.export_json()
        self.assertEqual(self.path.read_bytes(), self.original)
        self.error.assert_called_once()


class StorageConsistencyTests(PersistenceFixture):
    def test_partial_batch_placement_failure_rolls_back_data_and_session_flags(self):
        self.coin()
        before = copy.deepcopy(self.editor.data)
        previous_flags = set(self.editor.session_created_uids)
        place = self.editor.place_item_grouped
        calls = 0

        def fail_second(*args):
            nonlocal calls
            calls += 1
            return place(*args) if calls == 1 else -1

        with patch.object(self.editor, "place_item_grouped", side_effect=fail_second):
            self.assertEqual(self.editor.create_item(160001, 2), [])
        self.assertEqual(self.editor.data, before)
        self.assertEqual(self.editor.items, before["player"]["itemSaveDatas"])
        self.assertEqual(self.editor.session_created_uids, previous_flags)

    def test_duplication_failure_also_rolls_back_the_whole_batch(self):
        coin = self.coin()
        before = copy.deepcopy(self.editor.data)
        with patch.object(self.editor, "place_item_grouped", return_value=-1):
            self.assertEqual(self.editor.duplicate_item(coin, 2), [])
        self.assertEqual(self.editor.data, before)

    def test_aliasing_the_model_and_view_does_not_duplicate_records(self):
        self.editor.items = self.editor.data["player"]["itemSaveDatas"]
        self.editor.create_item(160001, 2)
        self.assertEqual(len(self.editor.items), 2)
        self.assertEqual(len(self.editor.items_by_uid), 2)
        self.assertEqual([i for i in self.editor.validate_save() if i["severity"] == "ERRO"], [])

    def test_invalid_and_duplicate_indices_never_count_as_free_slots(self):
        player = self.editor.data["player"]
        player["inventorySaveDatas"] = [storage_slot(-1), storage_slot(0), storage_slot(0), storage_slot("1")]
        self.assertEqual(self.editor.free_slot_count("Inventario"), 0)
        self.assertEqual(self.editor.create_item(160001), [])
        self.assertEqual(player["itemSaveDatas"], [])

    def test_repair_does_not_invent_storage_indices(self):
        player = self.editor.data["player"]
        player["inventorySaveDatas"] = [storage_slot(-1), storage_slot(0), storage_slot(0)]
        self.editor.repair_save(show_message=False)
        self.assertEqual([s["Index"] for s in player["inventorySaveDatas"]], [-1, 0, 0])
        self.assertFalse(self.editor.validate_before_save())

    def test_orphan_item_is_relocated_before_saving(self):
        coin = self.coin()
        self.editor.remove_uid_from_locations(coin["UniqueId"])
        self.assertIn("orphan_item", [i["code"] for i in self.editor.validate_save() if i["severity"] == "ERRO"])
        self.editor.save_dump()
        self.error.assert_not_called()
        loaded = final.VerifiedSaveFile.load(self.path)
        self.assertIn(coin["UniqueId"], [s["ItemUniqueId"] for s in loaded.player["inventorySaveDatas"]])

    def test_orphan_without_room_blocks_save_and_keeps_the_item(self):
        coin = self.coin()
        self.editor.data["player"]["inventorySaveDatas"] = []
        self.editor.data["player"]["stashSaveDatas"] = []
        self.editor.save_dump()
        self.assertEqual(self.path.read_bytes(), self.original)
        self.assertIn(coin, self.editor.items)
        self.assertTrue(self.editor.dirty)

    def test_item_beyond_the_last_page_is_rescued_before_save(self):
        coin = self.coin()
        self.editor.remove_uid_from_locations(coin["UniqueId"])
        self.editor.data["player"]["stashSaveDatas"].append(storage_slot(400, coin["UniqueId"], stash=True))
        self.editor.save_dump()
        self.error.assert_not_called()
        slots = final.VerifiedSaveFile.load(self.path).player["stashSaveDatas"]
        self.assertEqual(next(s for s in slots if s["Index"] == 400)["ItemUniqueId"], 0)
        self.assertIn(coin["UniqueId"], [s["ItemUniqueId"] for s in slots if s["Index"] < 343])

    def test_locked_slot_is_evacuated_without_unlocking_it(self):
        coin = self.coin()
        self.editor.data["player"]["inventorySaveDatas"][0]["IsUnlock"] = False
        self.editor.save_dump()
        self.error.assert_not_called()
        slots = final.VerifiedSaveFile.load(self.path).player["inventorySaveDatas"]
        self.assertFalse(slots[0]["IsUnlock"])
        self.assertEqual(slots[0]["ItemUniqueId"], 0)
        self.assertIn(coin["UniqueId"], [s["ItemUniqueId"] for s in slots[1:]])

    def test_unlock_flags_are_preserved_and_ambiguous_values_are_not_accepted(self):
        for flags in ({"IsUnlock": "false"}, {"IsUnLock": "true"}, {"IsUnLock": True, "IsUnlock": False}):
            with self.subTest(flags=flags):
                self.assertFalse(self.editor.slot_is_unlocked("stashSaveDatas", flags))
        slot = {"Index": 0, "ItemUniqueId": 0, "IsUnlock": True, "future": 8}
        self.editor.data["player"]["stashSaveDatas"] = [slot]
        self.assertEqual(self.editor.place_item(77, "Armazem 1"), 0)
        self.assertEqual(slot, {"Index": 0, "ItemUniqueId": 77, "IsUnlock": True, "future": 8})

    def test_automatic_destination_keeps_inventory_priority(self):
        player = self.editor.data["player"]
        player["inventorySaveDatas"] = [storage_slot(20)]
        self.editor.create_item(160001, target="Automatico")
        self.assertNotEqual(player["inventorySaveDatas"][0]["ItemUniqueId"], 0)
        self.assertTrue(all(s["ItemUniqueId"] == 0 for s in player["stashSaveDatas"]))

    def test_repair_preserves_server_pending_and_unknown_metadata(self):
        coin = self.coin()
        coin["IsServerPendingItem"] = True
        coin["FutureItem"] = {"token": "keep"}
        self.editor.repair_save(show_message=False)
        self.assertIs(coin["IsServerPendingItem"], True)
        self.assertEqual(coin["FutureItem"], {"token": "keep"})
        self.assertEqual(self.editor.duplicate_item(coin), [])

    def test_ids_do_not_reuse_previous_item_identity(self):
        coin = self.coin()
        coin["PrevUniqueId"] = 900
        self.assertGreater(self.editor.next_unique_id(), 900)


class ReloadComparisonTests(PersistenceFixture):
    def test_same_file_does_not_claim_that_the_game_accepted_it(self):
        self.coin()
        self.editor.save_dump()
        before = self.path.read_bytes()
        self.editor.check_saved_persistence()
        self.assertIn("Ainda não há evidência", self.info.call_args.args[1])
        self.assertEqual(self.path.read_bytes(), before)

    def test_reordering_item_records_is_not_reported_as_item_loss(self):
        self.editor.create_item(160001, 3)
        self.editor.save_dump()
        previous = self.receipt()
        external = final.VerifiedSaveFile.load(self.path)
        external.player["itemSaveDatas"].reverse()
        external.save(self.path)
        loaded = final.VerifiedSaveFile.load(self.path)
        current = audit.make_receipt(self.path, loaded, loaded._source_sha256)
        report = audit.compare_receipts(previous, current)
        self.assertTrue(report["file_changed"])
        self.assertEqual(report["missing"], [])
        self.assertEqual(report["changed"], [])
        self.assertEqual(report["moved"], [])

    def test_moved_changed_and_missing_items_are_distinguished(self):
        items = self.editor.create_item(160001, 3)
        self.editor.save_dump()
        previous = self.receipt()
        external = final.VerifiedSaveFile.load(self.path)
        player = external.player
        player["inventorySaveDatas"][0]["ItemUniqueId"] = 0
        player["stashSaveDatas"][0]["ItemUniqueId"] = items[0]["UniqueId"]
        player["itemSaveDatas"][1]["IsBlocked"] = True
        player["itemSaveDatas"].pop()
        player["inventorySaveDatas"][2]["ItemUniqueId"] = 0
        external.save(self.path)
        loaded = final.VerifiedSaveFile.load(self.path)
        report = audit.compare_receipts(previous, audit.make_receipt(self.path, loaded, loaded._source_sha256))
        self.assertEqual(report["moved"], [str(items[0]["UniqueId"])])
        self.assertEqual(report["changed"], [str(items[1]["UniqueId"])])
        self.assertEqual(report["missing"], [str(items[2]["UniqueId"])])
        self.assertEqual(self.receipt(), previous)

    def test_comparison_preserves_unsaved_edits_and_survives_a_new_editor(self):
        self.coin()
        self.editor.save_dump()
        other = final.FinalProEditor.__new__(final.FinalProEditor)
        other.path = self.path
        other._receipt_directory = self.editor._receipt_directory
        other.data = {"unsaved": "keep"}
        other.dirty = True
        other.check_saved_persistence()
        self.assertEqual(other.data, {"unsaved": "keep"})
        self.assertTrue(other.dirty)
        self.assertIn("preservou", self.info.call_args.args[1])

    def test_receipt_for_a_different_account_is_rejected(self):
        self.coin()
        self.editor.save_dump()
        self.save.account["ownerSteamId"] = "987654"
        current = audit.make_receipt(self.path, self.save, self.save._source_sha256)
        with self.assertRaisesRegex(ValueError, "outra conta"):
            audit.compare_receipts(self.receipt(), current)

    def test_receipt_for_a_different_path_is_rejected(self):
        self.coin()
        self.editor.save_dump()
        current = audit.make_receipt(self.folder / "copy.es3", self.save, self.save._source_sha256)
        with self.assertRaisesRegex(ValueError, "outro arquivo"):
            audit.compare_receipts(self.receipt(), current)

    def test_corrupt_receipt_reports_error_without_touching_save(self):
        self.coin()
        self.editor.save_dump()
        target = audit.receipt_path(self.editor._receipt_directory(), self.path)
        target.write_text("{broken", encoding="utf-8")
        before = self.path.read_bytes()
        self.editor.check_saved_persistence()
        self.error.assert_called_once()
        self.assertEqual(self.path.read_bytes(), before)


class PlatformPersistenceTests(unittest.TestCase):
    def test_directory_with_a_live_save_wins_over_an_empty_prefix(self):
        with tempfile.TemporaryDirectory() as raw:
            empty, live = Path(raw) / "empty", Path(raw) / "live"
            empty.mkdir()
            live.mkdir()
            (live / platform_support.SAVE_FILE_NAME).write_bytes(b"fixture")
            with patch.object(platform_support, "game_save_dir_candidates", return_value=[empty, live]):
                self.assertEqual(platform_support.default_game_save_dir(), live)

    def test_posix_probe_detects_wine_and_native_and_ignores_mentions_in_scripts(self):
        samples = [
            ("TaskBarHero.exe Z:\\Games\\TaskBarHero.exe\n", True),
            ('wine64-preloader wine64 "C:\\Games\\Task Bar Hero\\TaskBarHero.exe"\n', True),
            ("TaskbarHero.x86_64 /games/TaskbarHero.x86_64\n", True),
            ("python python test_item_persistence.py\nbash bash -c 'TaskBarHero.exe is a game'\n", False),
        ]
        for output, expected in samples:
            with self.subTest(output=output), patch.object(platform_support.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=output)):
                self.assertEqual(platform_support.posix_game_is_running_fail_safe(), expected)

    def test_posix_probe_fails_closed_on_missing_ps_timeout_and_empty_output(self):
        for error in (OSError("ps missing"), subprocess.TimeoutExpired("ps", 3)):
            with self.subTest(error=error), patch.object(platform_support.subprocess, "run", side_effect=error):
                self.assertTrue(platform_support.posix_game_is_running_fail_safe())
        for result in (SimpleNamespace(returncode=1, stdout="denied"), SimpleNamespace(returncode=0, stdout="")):
            with self.subTest(result=result), patch.object(platform_support.subprocess, "run", return_value=result):
                self.assertTrue(platform_support.posix_game_is_running_fail_safe())


if __name__ == "__main__":
    unittest.main()
