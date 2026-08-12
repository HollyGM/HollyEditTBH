import json
import os
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import safe_persistence
import save_layer
from app_meta import APP_VERSION
from hollyedittbh_final import (
    EnhancedProEditor,
    FinalProEditor,
    VerifiedSaveFile,
    taskbar_hero_is_running_fail_safe,
)
from safe_persistence import SaveConflictError
from save_layer import SaveFile as BaseSaveFile


def minimal_player():
    return {
        "itemSaveDatas": [],
        "heroSaveDatas": [],
        "inventorySaveDatas": [],
        "stashSaveDatas": [],
        "remakeTradingStashSaveDatas": [],
    }


def es3_root(*, marker="original"):
    account = {"ownerSteamId": "123456"}
    player = minimal_player()
    player["marker"] = marker
    account_json = json.dumps(account, ensure_ascii=False, separators=(",", ":"))
    player_json = json.dumps(player, ensure_ascii=False, separators=(",", ":"))
    return {
        "AccountSaveData": {"__type": "System.String", "value": account_json},
        "PlayerSaveData": {"__type": "System.String", "value": player_json},
        "SystemInfo": {
            "__type": "System.String",
            "value": save_layer._system_info_value(account_json, player_json, account["ownerSteamId"]),
        },
    }


def save_bytes(marker="original"):
    return BaseSaveFile(es3_root(marker=marker)).to_es3_bytes()


class TransactionalSaveTests(unittest.TestCase):
    def test_loaded_save_rejects_external_change_without_overwrite(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "SaveFile_Live.es3"
            path.write_bytes(save_bytes("loaded"))
            save = VerifiedSaveFile.load(path)
            save.player["marker"] = "editor"

            external = save_bytes("external")
            path.write_bytes(external)

            with self.assertRaises(SaveConflictError):
                save.save(path, backup=True)

            self.assertEqual(path.read_bytes(), external)
            self.assertEqual(BaseSaveFile.load(path).player["marker"], "external")
            self.assertFalse(any(path.parent.glob(".tbh-save-*.tmp")))

    def test_race_at_commit_is_detected_and_external_source_is_restored(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "SaveFile_Live.es3"
            path.write_bytes(save_bytes("loaded"))
            save = VerifiedSaveFile.load(path)
            save.player["marker"] = "editor"
            external = save_bytes("race-winner")
            real_replace = safe_persistence._replace_existing_with_backup
            raced = False

            def replace_with_race(target, replacement, backup_path):
                nonlocal raced
                if not raced and Path(target) == path:
                    raced = True
                    path.write_bytes(external)
                return real_replace(target, replacement, backup_path)

            with patch("safe_persistence._replace_existing_with_backup", side_effect=replace_with_race):
                with self.assertRaises(SaveConflictError):
                    save.save(path, backup=True)

            self.assertTrue(raced)
            self.assertEqual(path.read_bytes(), external)
            self.assertEqual(BaseSaveFile.load(path).player["marker"], "race-winner")
            self.assertFalse(any(path.parent.glob(".tbh-save-*.tmp")))

    def test_replace_failure_keeps_original_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "SaveFile_Live.es3"
            original = save_bytes("original")
            path.write_bytes(original)
            save = VerifiedSaveFile.load(path)
            save.player["marker"] = "editor"

            with patch("safe_persistence._replace_existing_with_backup", side_effect=OSError("replace failure")):
                with self.assertRaises(OSError):
                    save.save(path, backup=True)

            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(BaseSaveFile.load(path).player["marker"], "original")
            self.assertFalse(any(path.parent.glob(".tbh-save-*.tmp")))

    def test_failed_replace_partial_state_restores_missing_target_from_backup(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "SaveFile_Live.es3"
            backup = Path(temp_dir) / "SaveFile_Live_backup.es3"
            original = save_bytes("original")
            backup.write_bytes(original)

            self.assertFalse(path.exists())
            self.assertTrue(safe_persistence._recover_failed_windows_replace(path, backup))
            self.assertEqual(path.read_bytes(), original)
            self.assertFalse(backup.exists())

    def test_successful_saves_refresh_origin_fingerprint_and_backup_exact_source(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "SaveFile_Live.es3"
            path.write_bytes(save_bytes("v1"))
            save = VerifiedSaveFile.load(path)
            first_source = save._source_sha256

            save.player["marker"] = "v2"
            save.save(path, backup=True)
            second_source = save._source_sha256
            self.assertNotEqual(first_source, second_source)
            self.assertIsNotNone(save.last_backup_path)
            self.assertEqual(BaseSaveFile.load(save.last_backup_path).player["marker"], "v1")

            save.player["marker"] = "v3"
            save.save(path, backup=True)
            self.assertEqual(BaseSaveFile.load(path).player["marker"], "v3")
            self.assertNotEqual(second_source, save._source_sha256)
            self.assertEqual(BaseSaveFile.load(save.last_backup_path).player["marker"], "v2")

    def test_unicode_path_round_trip(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            folder = Path(temp_dir) / "Usuário José 漢字"
            folder.mkdir()
            path = folder / "SaveFile_Live.es3"
            path.write_bytes(save_bytes("unicode"))
            save = VerifiedSaveFile.load(path)
            save.player["marker"] = "gravado"
            save.save(path, backup=True)
            self.assertEqual(VerifiedSaveFile.load(path).player["marker"], "gravado")


class ProtectedModeFailSafeTests(unittest.TestCase):
    def test_protected_save_blocks_when_loaded_signature_is_unavailable(self):
        editor = FinalProEditor.__new__(FinalProEditor)
        editor.path = Path("SaveFile_Live.es3")
        editor.data = {"account": {}, "player": minimal_player()}
        editor.protected_mode = True
        editor.loaded_file_signature = None

        with patch("hollyedittbh_final.messagebox.showerror") as error, patch.object(
            EnhancedProEditor, "save_dump"
        ) as inherited_save:
            editor.save_dump()

        error.assert_called_once()
        inherited_save.assert_not_called()

    def test_process_probe_fails_closed_on_tasklist_error(self):
        with patch("hollyedittbh_final.os.name", "nt"), patch(
            "hollyedittbh_final.subprocess.run", side_effect=OSError("tasklist unavailable")
        ):
            self.assertTrue(taskbar_hero_is_running_fail_safe())

    def test_process_probe_fails_closed_on_nonzero_tasklist_status(self):
        completed = SimpleNamespace(returncode=1, stdout="")
        with patch("hollyedittbh_final.os.name", "nt"), patch(
            "hollyedittbh_final.subprocess.run", return_value=completed
        ):
            self.assertTrue(taskbar_hero_is_running_fail_safe())

    def test_process_probe_distinguishes_absent_and_running_game(self):
        absent = SimpleNamespace(returncode=0, stdout='INFO: No tasks are running which match the specified criteria.\n')
        running = SimpleNamespace(returncode=0, stdout='"TaskBarHero.exe","1234","Console","1","100 K"\n')
        with patch("hollyedittbh_final.os.name", "nt"):
            with patch("hollyedittbh_final.subprocess.run", return_value=absent):
                self.assertFalse(taskbar_hero_is_running_fail_safe())
            with patch("hollyedittbh_final.subprocess.run", return_value=running):
                self.assertTrue(taskbar_hero_is_running_fail_safe())


class BuildReproducibilityTests(unittest.TestCase):
    def test_toolchain_and_actions_remain_pinned(self):
        base = Path(__file__).resolve().parent
        workflow = (base / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
        requirements = (base / "requirements-build.txt").read_text(encoding="utf-8").casefold()

        self.assertIn("python-version: '3.12.10'", workflow)
        for requirement in (
            "pyinstaller==6.22.0",
            "pyinstaller-hooks-contrib==2026.6",
            "altgraph==0.17.5",
            "pefile==2024.8.26",
            "pywin32-ctypes==0.2.3",
            "packaging==26.2",
            "setuptools==84.0.0",
        ):
            self.assertIn(requirement, requirements)
        self.assertIn("actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", workflow)
        self.assertIn("actions/setup-python@5fda3b95a4ea91299a34e894583c3862153e4b97", workflow)
        self.assertIn("actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a", workflow)
        self.assertIn("permissions:\n  contents: read", workflow)

    def test_version_is_consistent_for_332(self):
        base = Path(__file__).resolve().parent
        version_info = (base / "version_info.txt").read_text(encoding="utf-8")
        workflow = (base / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")

        self.assertEqual(APP_VERSION, "3.3.2")
        self.assertIn("FileVersion', '3.3.2'", version_info)
        self.assertIn("filevers=(3, 3, 2, 0)", version_info)
        self.assertIn("HollyEditTBH-v3.3.2-windows", workflow)


if __name__ == "__main__":
    unittest.main()
