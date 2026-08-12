import os
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from hollyedittbh_final import FinalProEditor
from market_intelligence import MarketQuote, MarketSnapshot
from market_snapshot_guard import prefer_snapshot


def minimal_player():
    return {
        "itemSaveDatas": [],
        "heroSaveDatas": [],
        "inventorySaveDatas": [],
        "stashSaveDatas": [],
        "remakeTradingStashSaveDatas": [],
    }


def storage_slot(index, uid=0, stash=False):
    return {
        "Index": index,
        "ItemUniqueId": uid,
        "IsUnLock" if stash else "IsUnlock": True,
        "IsUnlockedByRune": False,
    }


def final_headless(data=None, database=None):
    data = data or {"account": {}, "player": minimal_player()}
    database = database or []
    editor = FinalProEditor.__new__(FinalProEditor)
    editor.data = data
    editor.items = list(data["player"].get("itemSaveDatas", []))
    editor.db = database
    editor.db_by_key = {str(item["ItemKey"]): item for item in database}
    editor.items_by_uid = {
        int(item["UniqueId"]): item
        for item in editor.items
        if isinstance(item, dict) and int(item.get("UniqueId") or 0) > 0
    }
    editor.original_item_uids = set(editor.items_by_uid)
    editor.session_created_uids = set()
    editor.session_modified_uids = set()
    editor.protected_mode = True
    editor.selected_item = None
    editor.mark_dirty = lambda *_args, **_kwargs: None
    editor.refresh_all = lambda: None
    return editor


class ProtectedModeFinalTests(unittest.TestCase):
    def test_protected_mode_blocks_item_creation_even_for_one_item(self):
        database = [{"ItemKey": "300101", "Name": "Sword", "Rarity": "LEGENDARY", "Type": "GEAR", "StatTypes": []}]
        player = minimal_player()
        player["inventorySaveDatas"] = [storage_slot(0)]
        editor = final_headless({"account": {}, "player": player}, database)
        with patch("hollyedittbh_final.messagebox.showwarning") as warning:
            self.assertEqual(editor.create_item(300101, 1), [])
        warning.assert_called_once()
        self.assertEqual(player["itemSaveDatas"], [])

    def test_protected_mode_blocks_duplication(self):
        item = {"ItemKey": 300101, "UniqueId": 7, "EnchantData": []}
        player = minimal_player()
        player["itemSaveDatas"] = [item]
        player["inventorySaveDatas"] = [storage_slot(0, 7), storage_slot(1)]
        editor = final_headless({"account": {}, "player": player}, [])
        with patch("hollyedittbh_final.messagebox.showwarning") as warning:
            self.assertEqual(editor.duplicate_item(item, 1), [])
        warning.assert_called_once()
        self.assertEqual(len(player["itemSaveDatas"]), 1)

    def test_protected_mode_refuses_session_created_item_on_equip(self):
        item = {"ItemKey": 300101, "UniqueId": 9, "EnchantData": []}
        editor = final_headless()
        editor.session_created_uids.add(9)
        with patch("hollyedittbh_final.messagebox.showwarning") as warning:
            self.assertFalse(editor.equip_item({"heroKey": 101, "equippedItemIds": [0] * 10}, 0, item))
        warning.assert_called_once()

    def test_market_round_capacity_uses_configured_slot_limit(self):
        player = minimal_player()
        player["stashSaveDatas"] = [storage_slot(396 + index, 0, stash=True) for index in range(66)]
        editor = final_headless({"account": {}, "player": player}, [])
        with patch.dict("os.environ", {"HOLLYEDIT_MARKET_SLOTS": "4"}):
            self.assertEqual(editor.market_round_capacity(7), 4)

    def test_market_fill_context_caps_inherited_free_slot_count(self):
        player = minimal_player()
        player["stashSaveDatas"] = [storage_slot(396 + index, 0, stash=True) for index in range(66)]
        editor = final_headless({"account": {}, "player": player}, [])

        def fill_market_page():
            return editor.free_slot_count("Armazem 7")

        with patch.dict("os.environ", {"HOLLYEDIT_MARKET_SLOTS": "4"}):
            self.assertEqual(fill_market_page(), 4)

    def test_market_summary_capacity_is_consumed_once(self):
        player = minimal_player()
        player["stashSaveDatas"] = [storage_slot(396 + index, 0, stash=True) for index in range(66)]
        editor = final_headless({"account": {}, "player": player}, [])
        editor._market_summary_capacity = ("Armazem 7", 4)
        self.assertEqual(editor.free_slot_count("Armazem 7"), 4)
        self.assertIsNone(editor._market_summary_capacity)
        self.assertEqual(editor.free_slot_count("Armazem 7"), 66)

    def test_file_signature_detects_same_size_same_timestamp_content_change(self):
        editor = final_headless()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "SaveFile_Live.es3"
            path.write_bytes(b"AAAA")
            stat = path.stat()
            before = editor.file_signature(path)
            path.write_bytes(b"BBBB")
            os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns))
            after = editor.file_signature(path)
        self.assertIsNotNone(before)
        self.assertIsNotNone(after)
        self.assertEqual(before[:2], after[:2])
        self.assertNotEqual(before, after)


class MarketSnapshotGuardTests(unittest.TestCase):
    @staticmethod
    def snapshot(count, *, complete):
        return MarketSnapshot(
            captured_at=time.time(),
            quotes=[MarketQuote(f"Item {index}", index + 1, "$1.00", 1.0, "https://example.invalid") for index in range(count)],
            complete=complete,
            total_reported=count if complete else count + 100,
        )

    def test_partial_regression_does_not_replace_better_cache(self):
        cached = self.snapshot(100, complete=True)
        partial = self.snapshot(20, complete=False)
        self.assertIs(prefer_snapshot(cached, partial), cached)

    def test_complete_cache_beats_larger_partial_candidate(self):
        cached = self.snapshot(100, complete=True)
        partial = self.snapshot(150, complete=False)
        self.assertIs(prefer_snapshot(cached, partial), cached)

    def test_complete_snapshot_replaces_cache(self):
        cached = self.snapshot(100, complete=True)
        complete = self.snapshot(120, complete=True)
        self.assertIs(prefer_snapshot(cached, complete), complete)

    def test_partial_snapshot_can_be_used_when_no_cache_exists(self):
        partial = self.snapshot(20, complete=False)
        self.assertIs(prefer_snapshot(None, partial), partial)


class DistributionFinalTests(unittest.TestCase):
    def test_pyinstaller_uses_final_entrypoint(self):
        spec = (Path(__file__).resolve().parent / "HollyEditTBH.spec").read_text(encoding="utf-8")
        self.assertIn("['hollyedittbh_final.py']", spec)

    def test_tbh_save_editor_import_resolves_legacy_core(self):
        import tbh_save_editor

        self.assertEqual(Path(tbh_save_editor.__file__).name, "legacy_editor.py")


if __name__ == "__main__":
    unittest.main()
