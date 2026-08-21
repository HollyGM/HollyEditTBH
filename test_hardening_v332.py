import hashlib
import json
import re
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

    def test_rollback_preserves_second_concurrent_save_instead_of_deleting_it(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "SaveFile_Live.es3"
            captured = Path(temp_dir) / "captured.es3"
            editor_blob = save_bytes("editor")
            first_external = save_bytes("external-1")
            second_external = save_bytes("external-2")
            path.write_bytes(editor_blob)
            captured.write_bytes(first_external)

            real_replace = safe_persistence._replace_existing_with_backup
            injected = False

            def replace_with_second_external(target, replacement, backup_path):
                nonlocal injected
                if not injected and Path(target) == path:
                    injected = True
                    path.write_bytes(second_external)
                return real_replace(target, replacement, backup_path)

            with patch("safe_persistence._replace_existing_with_backup", side_effect=replace_with_second_external):
                restored, recovery = safe_persistence._restore_captured_source(
                    path,
                    captured,
                    hashlib.sha256(editor_blob).hexdigest(),
                )

            self.assertFalse(restored)
            self.assertIsNotNone(recovery)
            self.assertEqual(BaseSaveFile.load(path).player["marker"], "external-1")
            self.assertEqual(BaseSaveFile.load(recovery).player["marker"], "external-2")

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
        with patch("hollyedittbh_final.os.name", "nt"), patch.dict(
            "hollyedittbh_final.os.environ", {"SystemRoot": r"C:\Windows"}, clear=False
        ), patch("hollyedittbh_final.subprocess.run", side_effect=OSError("tasklist unavailable")):
            self.assertTrue(taskbar_hero_is_running_fail_safe())

    def test_process_probe_fails_closed_on_nonzero_tasklist_status(self):
        completed = SimpleNamespace(returncode=1, stdout="")
        with patch("hollyedittbh_final.os.name", "nt"), patch.dict(
            "hollyedittbh_final.os.environ", {"SystemRoot": r"C:\Windows"}, clear=False
        ), patch("hollyedittbh_final.subprocess.run", return_value=completed):
            self.assertTrue(taskbar_hero_is_running_fail_safe())

    def test_process_probe_distinguishes_absent_and_running_game(self):
        absent = SimpleNamespace(returncode=0, stdout='INFO: No tasks are running which match the specified criteria.\n')
        running = SimpleNamespace(returncode=0, stdout='"TaskBarHero.exe","1234","Console","1","100 K"\n')
        with patch("hollyedittbh_final.os.name", "nt"), patch.dict(
            "hollyedittbh_final.os.environ", {"SystemRoot": r"C:\Windows"}, clear=False
        ):
            with patch("hollyedittbh_final.subprocess.run", return_value=absent):
                self.assertFalse(taskbar_hero_is_running_fail_safe())
            with patch("hollyedittbh_final.subprocess.run", return_value=running):
                self.assertTrue(taskbar_hero_is_running_fail_safe())

    def test_process_probe_uses_system32_tasklist_and_tolerant_decode(self):
        completed = SimpleNamespace(returncode=0, stdout="")
        with patch("hollyedittbh_final.os.name", "nt"), patch.dict(
            "hollyedittbh_final.os.environ", {"SystemRoot": r"D:\WinRoot"}, clear=False
        ), patch("hollyedittbh_final.subprocess.run", return_value=completed) as run:
            self.assertFalse(taskbar_hero_is_running_fail_safe())

        command = run.call_args.args[0]
        self.assertEqual(command[0], r"D:\WinRoot\System32\tasklist.exe")
        self.assertEqual(run.call_args.kwargs["errors"], "replace")
        self.assertEqual(run.call_args.kwargs["timeout"], 3)


class BuildReproducibilityTests(unittest.TestCase):
    def test_toolchain_and_actions_remain_pinned(self):
        base = Path(__file__).resolve().parent
        workflow = (base / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
        requirements = (base / "requirements-build.txt").read_text(encoding="utf-8").casefold()

        self.assertRegex(workflow, r"python-version\s*:\s*['\"]?3\.12\.10['\"]?")
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
        self.assertRegex(workflow, r"permissions\s*:\s*\r?\n\s*contents\s*:\s*read\b")

    def test_version_is_consistent_across_every_artifact(self):
        """Um bump de versão passou a ser uma linha em app_meta.py.

        As asserções derivam de APP_VERSION em vez de repetirem o número: antes
        subir a versão exigia editar seis literais neste teste, e esquecer um
        deles quebrava o gate de distribuição só no runner Windows."""
        base = Path(__file__).resolve().parent
        version_info = (base / "version_info.txt").read_text(encoding="utf-8")
        workflow = (base / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
        parts = APP_VERSION.split(".")

        self.assertRegex(APP_VERSION, r"^\d+\.\d+\.\d+$")
        self.assertIn(f"FileVersion', '{APP_VERSION}'", version_info)
        self.assertIn(f"ProductVersion', '{APP_VERSION}'", version_info)
        self.assertIn(f"filevers=({', '.join(parts)}, 0)", version_info)
        self.assertIn(f"prodvers=({', '.join(parts)}, 0)", version_info)
        self.assertIn(f"HollyEditTBH-v{APP_VERSION}-windows", workflow)
        self.assertIn(f"@('{APP_VERSION}', '{APP_VERSION}.0')", workflow)
        self.assertIn("$allowedVersions -notcontains $fileVersion", workflow)
        self.assertIn("$allowedVersions -notcontains $productVersion", workflow)
        self.assertNotIn("-notlike", workflow)

    def test_ci_runs_every_test_module_in_the_repository(self):
        """Uma suíte nova só protege o produto se o CI de fato a executar."""
        base = Path(__file__).resolve().parent
        workflow = (base / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
        for module in sorted(path.name for path in base.glob("test_*.py")):
            self.assertIn(module, workflow, f"{module} não é executado pelo CI")


if __name__ == "__main__":
    unittest.main()
