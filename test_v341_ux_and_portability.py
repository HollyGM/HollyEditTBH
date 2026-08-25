"""Regressões da revisão de usabilidade, português e portabilidade.

Cobre defeitos que a suíte anterior não pegava porque nenhum deles quebra o
formato do save: um comando inteligente sem chamador, mensagens visíveis sem
acento, tabelas sem barra de rolagem, caminhos e chamadas exclusivos do Windows
e resumos de operação em massa que contavam registros não alterados.
"""
from __future__ import annotations

import ast
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import app_meta
import legacy_editor
import market_policy
import platform_support
from tbh_save_editor import ProEditor

BASE = Path(__file__).resolve().parent
EDITOR_SOURCE = (BASE / "legacy_editor.py").read_text(encoding="utf-8")

#: Palavras que só aparecem em texto de interface quando falta acento. "nao"
#: fica de fora: ``parse_edited_value`` aceita a forma sem acento de propósito.
UNACCENTED = {
    "voce", "sao", "estao", "acao", "opcao", "opcoes", "informacao", "informacoes",
    "configuracao", "selecao", "criacao", "duplicacao", "alocacao", "validacao",
    "codigo", "unico", "numero", "nivel", "maximo", "minimo", "automatico",
    "automatica", "invalido", "invalida", "permissao", "versao", "localizacao",
    "posicao", "pagina", "paginas", "ultimo", "ultima", "proximo", "obrigatorio",
    "necessario", "possivel", "disponivel", "responsavel", "referencia",
    "experiencia", "inteligencia", "copia", "copias", "memoria", "heroi", "herois",
    "previa", "excluido", "concluido", "concluida", "colecao", "espaco", "espacos",
    "reparacao", "icones", "armazem", "inventario",
}
#: Literais que são valores internos ou entrada tolerada, não texto de tela.
#: "Armazem " é o prefixo do destino interno (``ITEM_DESTINATIONS``); a interface
#: só o mostra passando por ``destination_label``, que devolve "Armazém".
ALLOWED_LITERALS = {"nao", "sim", "Inventario", "Automatico", "Armazem "}


def _ui_string_literals(source: str) -> list[str]:
    """Literais que se parecem com frase de interface: têm espaço e letra minúscula."""
    found: list[str] = []
    for node in ast.walk(ast.parse(source)):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            text = node.value
            if text in ALLOWED_LITERALS:
                continue
            if " " in text and any(character.islower() for character in text):
                found.append(text)
    return found


def _words(text: str) -> set[str]:
    cleaned = "".join(character if character.isalnum() else " " for character in text)
    return {word.casefold() for word in cleaned.split()}


def minimal_player():
    return {
        "itemSaveDatas": [], "heroSaveDatas": [], "inventorySaveDatas": [],
        "stashSaveDatas": [], "remakeTradingStashSaveDatas": [],
    }


def headless(player):
    editor = ProEditor.__new__(ProEditor)
    editor.data = {"account": {}, "player": player}
    editor.items = list(player.get("itemSaveDatas", []))
    editor.db = []
    editor.db_by_key = {}
    editor.protected_mode = True
    editor.session_created_uids = set()
    editor.session_modified_uids = set()
    editor.mark_dirty = lambda *_a, **_k: None
    editor.refresh_all = lambda: None
    editor.refresh_collections = lambda: None
    editor.rebuild_item_index()
    editor.original_item_uids = set(editor.items_by_uid)
    return editor


class PortugueseInterfaceTests(unittest.TestCase):
    def test_no_visible_message_lost_its_accents(self):
        """Dezenas de mensagens diziam "copia", "sao", "automatico" e "excluido"."""
        offenders: list[tuple[str, str]] = []
        for text in _ui_string_literals(EDITOR_SOURCE):
            for word in sorted(_words(text) & UNACCENTED):
                offenders.append((word, text[:80]))
        self.assertEqual(offenders, [], f"texto de interface sem acento: {offenders[:5]}")

    def test_heroes_without_a_registered_name_are_still_labelled_in_portuguese(self):
        """As duas listas de locais rotulavam um herói desconhecido como "Hero N"."""
        for source_name in ("uid_location_labels", "item_locations"):
            body = EDITOR_SOURCE.split(f"def {source_name}(", 1)[1].split("\n    def ", 1)[0]
            self.assertNotIn('f"Hero {', body, f"{source_name} ainda usa rótulo em inglês")
            self.assertIn("Herói", body)

    def test_move_reports_the_accented_destination_instead_of_the_internal_value(self):
        """A barra de status mostrava o valor cru "Armazem 3" ao usuário."""
        player = minimal_player()
        player["inventorySaveDatas"] = [{"Index": 0, "ItemUniqueId": 7, "IsUnLock": True}]
        player["itemSaveDatas"] = [{"ItemKey": 1, "UniqueId": 7, "EnchantData": []}]
        editor = headless(player)
        messages: list[str] = []
        editor.status_var = type("Var", (), {"set": lambda _s, value: messages.append(value)})()
        self.assertTrue(editor.move_item(player["itemSaveDatas"][0], "Inventario"))
        self.assertEqual(messages, ["Item 1 já está em Inventário."])


class ReachableIntelligenceTests(unittest.TestCase):
    def test_global_optimisation_has_a_command_in_the_interface(self):
        """open_auto_equip_all_preview existia, era testado e não tinha chamador.

        A alocação exata de intelligence_engine só roda por esse caminho, então
        sem um ``command=`` o recurso inteiro ficava inacessível ao usuário."""
        self.assertIn("command=self.open_auto_equip_all_preview", EDITOR_SOURCE)
        self.assertIn("self.open_auto_equip_all_preview()", EDITOR_SOURCE)

    def test_every_public_dialog_opener_is_reachable(self):
        """Guarda genérica contra um novo comando nascer órfão como aquele."""
        tree = ast.parse(EDITOR_SOURCE)
        openers = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name.startswith("open_")
        }
        orphans = sorted(
            name for name in openers
            if f"self.{name}(" not in EDITOR_SOURCE.replace(f"def {name}(", "")
            and f"command=self.{name}" not in EDITOR_SOURCE
        )
        self.assertEqual(orphans, [], f"comandos sem nenhum chamador: {orphans}")

    def test_each_layer_describes_the_algorithm_it_actually_runs(self):
        """A prévia dizia "não é um ótimo global" mesmo no produto, que é exato.

        O núcleo legado resolve guloso e a camada intermediária substitui o
        planejamento por uma alocação exata; uma frase fixa descreveria errado
        uma das duas."""
        import hollyedittbh_next

        legacy_note = ProEditor.auto_equip_all_strategy_note(object())
        enhanced_note = hollyedittbh_next.EnhancedProEditor.auto_equip_all_strategy_note(object())
        self.assertNotEqual(legacy_note, enhanced_note)
        self.assertIn("não é um ótimo global", legacy_note)
        self.assertIn("ótimo global", enhanced_note)
        self.assertNotIn("não é um ótimo global", enhanced_note)
        self.assertIn("self.auto_equip_all_strategy_note()", EDITOR_SOURCE)


class SingleEntryPointTests(unittest.TestCase):
    def test_the_core_layer_is_not_an_application(self):
        """O README afirmava que legacy_editor recusava execução direta.

        Ele continuava expondo ``main()``: executá-lo entregava um editor sem
        persistência transacional, sem detecção fail-safe do jogo aberto e sem
        os bloqueios de criação/duplicação do Modo Protegido."""
        self.assertFalse(hasattr(legacy_editor, "main"))
        self.assertIn("legacy_editor é uma camada interna", EDITOR_SOURCE)


class BulkCommandTests(unittest.TestCase):
    def _collection_editor(self, records, collection="Moedas"):
        player = minimal_player()
        player["currenySaveDatas"] = records
        editor = headless(player)
        editor.collection_var = type("Var", (), {"get": lambda _s: collection, "set": lambda _s, _v: None})()
        return editor

    def test_bulk_edit_counts_only_the_records_it_can_reach(self):
        """O resumo dizia "atualizado em N registros" contando os sem o campo."""
        records = [{"Key": 1, "Quantity": 5}, {"Key": 2}, {"Key": 3, "Quantity": 7}]
        editor = self._collection_editor(records)
        seen: list[str] = []
        editor.mark_dirty = lambda message="": seen.append(message)
        with patch.object(legacy_editor.messagebox, "askyesno", return_value=True), \
             patch.object(legacy_editor.messagebox, "showinfo") as info, \
             patch.object(ProEditor, "ask_quantity", return_value=99):
            editor.bulk_edit_collection()
        self.assertEqual(records[0]["Quantity"], 99)
        self.assertEqual(records[2]["Quantity"], 99)
        self.assertNotIn("Quantity", records[1])
        self.assertIn("2 registro(s)", seen[0])
        self.assertIn("2 registro(s)", info.call_args.args[1])

    def test_bulk_edit_asks_before_rewriting_every_record(self):
        """Era a única operação em massa que aplicava sem nenhuma confirmação."""
        records = [{"Key": 1, "Quantity": 5}]
        editor = self._collection_editor(records)
        with patch.object(legacy_editor.messagebox, "askyesno", return_value=False) as ask, \
             patch.object(legacy_editor.messagebox, "showinfo"), \
             patch.object(ProEditor, "ask_quantity", return_value=99):
            editor.bulk_edit_collection()
        self.assertTrue(ask.called)
        self.assertEqual(records[0]["Quantity"], 5)

    def test_bulk_edit_says_so_when_no_record_carries_the_field(self):
        editor = self._collection_editor([{"Key": 1}, {"Key": 2}])
        with patch.object(legacy_editor.messagebox, "showinfo") as info, \
             patch.object(ProEditor, "ask_quantity") as quantity:
            editor.bulk_edit_collection()
        self.assertFalse(quantity.called)
        self.assertIn("Nenhum registro", info.call_args.args[1])

    def test_unlocking_pets_only_touches_the_locked_ones_and_confirms_first(self):
        player = minimal_player()
        player["PetSaveData"] = [
            {"PetKey": 1, "IsUnlock": True, "IsViewed": True},
            {"PetKey": 2, "IsUnlock": False, "IsViewed": False},
        ]
        editor = headless(player)
        editor.collection_var = type("Var", (), {"get": lambda _s: "Pets", "set": lambda _s, _v: None})()
        seen: list[str] = []
        editor.mark_dirty = lambda message="": seen.append(message)
        with patch.object(legacy_editor.messagebox, "askyesno", return_value=True) as ask, \
             patch.object(legacy_editor.messagebox, "showinfo") as info:
            editor.unlock_all_pets()
        self.assertTrue(ask.called)
        self.assertIn("1 pet(s)", ask.call_args.args[1])
        self.assertIn("1 pet(s)", info.call_args.args[1])
        self.assertEqual(seen, ["1 pet(s) desbloqueado(s)."])
        self.assertTrue(all(pet["IsUnlock"] for pet in player["PetSaveData"]))

    def test_unlocking_pets_reports_an_already_complete_save_instead_of_dirtying_it(self):
        player = minimal_player()
        player["PetSaveData"] = [{"PetKey": 1, "IsUnlock": True, "IsViewed": True}]
        editor = headless(player)
        editor.collection_var = type("Var", (), {"get": lambda _s: "Pets", "set": lambda _s, _v: None})()
        editor.mark_dirty = lambda *_a, **_k: self.fail("save marcado como alterado sem alteração")
        with patch.object(legacy_editor.messagebox, "askyesno") as ask, \
             patch.object(legacy_editor.messagebox, "showinfo") as info:
            editor.unlock_all_pets()
        self.assertFalse(ask.called)
        self.assertIn("já estão desbloqueados", info.call_args.args[1])


class PlatformSupportTests(unittest.TestCase):
    def test_windows_keeps_the_historical_localLow_path(self):
        home = Path("/home/tester")
        candidates = platform_support.game_save_dir_candidates(home, "win32")
        self.assertEqual(candidates[0], home / "AppData" / "LocalLow" / "TesseractStudio" / "TaskbarHero")

    def test_linux_looks_inside_the_proton_prefix_first(self):
        """No Linux o jogo roda sob Proton: o save fica dentro do prefixo, não em ~/AppData."""
        home = Path("/home/tester")
        candidates = platform_support.game_save_dir_candidates(home, "linux")
        rendered = [str(path) for path in candidates]
        self.assertTrue(any("compatdata" in path and "TaskbarHero" in path for path in rendered))
        self.assertFalse(any(path.startswith(str(home / "AppData")) for path in rendered))

    def test_macos_looks_in_application_support_and_in_the_wine_bottle(self):
        home = Path("/Users/tester")
        rendered = [str(path) for path in platform_support.game_save_dir_candidates(home, "darwin")]
        self.assertIn(str(home / "Library" / "Application Support" / "TesseractStudio" / "TaskbarHero"), rendered)
        self.assertTrue(any("drive_c" in path for path in rendered))

    def test_every_platform_offers_at_least_one_candidate(self):
        for system in ("win32", "darwin", "linux"):
            self.assertTrue(platform_support.game_save_dir_candidates(Path("/home/tester"), system))

    def test_default_dir_prefers_a_folder_that_exists(self):
        with patch.object(Path, "is_dir", lambda self: "compatdata" in str(self)):
            chosen = platform_support.default_game_save_dir(Path("/home/tester"), "linux")
        self.assertIn("compatdata", str(chosen))

    def test_default_dir_falls_back_to_the_canonical_path_when_nothing_exists(self):
        with patch.object(Path, "is_dir", lambda self: False):
            chosen = platform_support.default_game_save_dir(Path("/home/tester"), "win32")
        self.assertEqual(chosen, Path("/home/tester/AppData/LocalLow/TesseractStudio/TaskbarHero"))

    def test_user_data_dir_uses_the_native_location_of_each_system(self):
        fallback = Path("/opt/app")
        self.assertEqual(platform_support.user_data_dir("App", fallback, frozen=False, platform="linux"), fallback)
        with patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\t\AppData\Local"}, clear=False):
            self.assertEqual(
                platform_support.user_data_dir("App", fallback, frozen=True, platform="win32"),
                Path(r"C:\Users\t\AppData\Local") / "App",
            )
        with patch.dict(os.environ, {"XDG_DATA_HOME": "/home/t/.local/share"}, clear=False):
            self.assertEqual(
                platform_support.user_data_dir("App", fallback, frozen=True, platform="linux"),
                Path("/home/t/.local/share/App"),
            )

    def test_opening_a_folder_never_reaches_for_a_missing_os_startfile(self):
        """``os.startfile`` não existe fora do Windows: a chamada crua levantava
        AttributeError em vez de abrir a pasta."""
        with patch.object(platform_support.shutil, "which", return_value="/usr/bin/xdg-open"), \
             patch.object(platform_support.subprocess, "Popen") as popen:
            self.assertTrue(platform_support.open_in_file_manager("/tmp/x", platform="linux"))
        self.assertEqual(popen.call_args.args[0], ["xdg-open", "/tmp/x"])
        with patch.object(platform_support.shutil, "which", return_value="/usr/bin/open"), \
             patch.object(platform_support.subprocess, "Popen") as popen:
            self.assertTrue(platform_support.open_in_file_manager("/tmp/x", platform="darwin"))
        self.assertEqual(popen.call_args.args[0], ["open", "/tmp/x"])

    def test_opening_a_folder_reports_failure_instead_of_raising(self):
        with patch.object(platform_support.shutil, "which", return_value=None):
            self.assertFalse(platform_support.open_in_file_manager("/tmp/x", platform="linux"))

    def test_font_preference_falls_back_to_an_installed_family(self):
        self.assertEqual(platform_support.preferred_font_family(["DejaVu Sans", "Fixed"], "linux"), "DejaVu Sans")
        self.assertEqual(platform_support.preferred_font_family(["Segoe UI", "Arial"], "win32"), "Segoe UI")
        self.assertIsNone(platform_support.preferred_font_family([], "linux"))
        self.assertIsNone(platform_support.preferred_font_family(["Comic Sans MS"], "linux"))


class SteamLibraryDiscoveryTests(unittest.TestCase):
    """O editor não achava o save no Linux por dois defeitos independentes.

    O AppID em ``platform_support`` era o do playtest (2957000) enquanto o valor
    correto (3678970) já existia em ``market_policy``, e a busca só olhava
    bibliotecas Steam dentro do ``$HOME`` — uma biblioteca em disco externo,
    declarada em ``libraryfolders.vdf``, ficava invisível.
    """

    SAVE_SUFFIX = Path("pfx/drive_c/users/steamuser/AppData/LocalLow/TesseractStudio/TaskbarHero")

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.home = self.tmp / "home" / "thiago"
        self.home.mkdir(parents=True)

    def write_vdf(self, steam_root: Path, body: bytes) -> Path:
        target = steam_root / "steamapps" / "libraryfolders.vdf"
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(body)
        return target

    @staticmethod
    def vdf_for(paths) -> bytes:
        rows = "\n".join(f'\t\t\t"path"\t\t"{path}"' for path in paths)
        return f'"libraryfolders"\n{{\n\t"0"\n\t{{\n{rows}\n\t}}\n}}\n'.encode("utf-8")

    def candidates(self):
        return [str(path) for path in platform_support.game_save_dir_candidates(self.home, "linux")]

    def test_a_library_on_an_external_disk_is_found(self):
        """Cenário relatado: SSD de sistema pequeno e jogo em disco externo."""
        external = self.tmp / "run" / "media" / "thiago" / "Thiago" / "SteamLibrary"
        self.write_vdf(
            self.home / ".steam" / "steam",
            self.vdf_for([self.home / ".local" / "share" / "Steam", external]),
        )
        expected = external / "steamapps" / "compatdata" / "3678970" / self.SAVE_SUFFIX
        self.assertIn(str(expected), self.candidates())

    def test_the_external_library_is_what_default_dir_returns(self):
        """Ponta a ponta: com o save no disco externo, é ele que o editor abre."""
        external = self.tmp / "run" / "media" / "thiago" / "Thiago" / "SteamLibrary"
        save_dir = external / "steamapps" / "compatdata" / "3678970" / self.SAVE_SUFFIX
        save_dir.mkdir(parents=True)
        (save_dir / platform_support.SAVE_FILE_NAME).write_bytes(b"save")
        self.write_vdf(self.home / ".steam" / "steam", self.vdf_for([external]))
        self.assertEqual(platform_support.default_game_save_dir(self.home, "linux"), save_dir)

    def test_the_published_app_id_wins_over_the_playtest(self):
        """Os dois prefixos podem coexistir; o jogo publicado tem de vir antes."""
        external = self.tmp / "biblioteca"
        self.write_vdf(self.home / ".steam" / "steam", self.vdf_for([external]))
        rendered = self.candidates()
        published = [index for index, path in enumerate(rendered) if "/3678970/" in path]
        playtest = [index for index, path in enumerate(rendered) if "/2957000/" in path]
        self.assertTrue(published, "nenhum candidato usa o AppID do jogo publicado")
        self.assertTrue(playtest, "o AppID do playtest deixou de ser procurado")
        self.assertLess(
            max(published), min(playtest),
            "um prefixo do playtest seria aberto antes do prefixo do jogo publicado",
        )

    def test_a_playtest_only_install_is_still_found(self):
        external = self.tmp / "biblioteca"
        save_dir = external / "steamapps" / "compatdata" / "2957000" / self.SAVE_SUFFIX
        save_dir.mkdir(parents=True)
        self.write_vdf(self.home / ".steam" / "steam", self.vdf_for([external]))
        self.assertEqual(platform_support.default_game_save_dir(self.home, "linux"), save_dir)

    def test_a_missing_vdf_keeps_the_previous_behaviour(self):
        """Sem Steam instalada, nada muda e nada explode."""
        rendered = self.candidates()
        self.assertTrue(rendered)
        outside_home = [path for path in rendered if not path.startswith(str(self.home))]
        self.assertEqual(outside_home, [], f"caminho fora do home sem VDF: {outside_home[:3]}")

    def test_an_unreadable_or_corrupt_vdf_never_raises(self):
        """``legacy_editor`` resolve GAME_SAVE_DIR em tempo de import: uma exceção
        aqui derruba a aplicação na inicialização em vez de só não achar o save."""
        steam_root = self.home / ".steam" / "steam"
        for body in (b"", b"\x00\x01\x02 lixo binario \xff\xfe", b'"libraryfolders" { "0" {', b'"path" ""'):
            with self.subTest(body=body[:16]):
                self.write_vdf(steam_root, body)
                self.assertTrue(self.candidates())

        # Um diretório no lugar do arquivo cobre o caso de leitura impossível.
        vdf = steam_root / "steamapps" / "libraryfolders.vdf"
        vdf.unlink()
        vdf.mkdir()
        self.assertTrue(self.candidates())

    def test_the_same_library_declared_twice_appears_once(self):
        """``~/.steam/steam`` costuma ser symlink para ``~/.local/share/Steam``."""
        external = self.tmp / "biblioteca"
        body = self.vdf_for([external])
        self.write_vdf(self.home / ".steam" / "steam", body)
        self.write_vdf(self.home / ".local" / "share" / "Steam", body)
        roots = [str(path) for path in platform_support.steam_library_roots(self.home)]
        self.assertEqual(roots.count(str(external)), 1, roots)
        rendered = self.candidates()
        self.assertEqual(len(rendered), len(set(rendered)), "há candidatos repetidos")

    def test_a_windows_style_escaped_path_is_normalised(self):
        self.write_vdf(self.home / ".steam" / "steam", b'"path"\t\t"D:\\\\SteamLibrary"')
        roots = [str(path) for path in platform_support.steam_library_roots(self.home)]
        self.assertIn("D:\\SteamLibrary", roots)
        self.assertNotIn("D:\\\\SteamLibrary", roots)

    def test_a_huge_file_in_place_of_the_vdf_is_not_read_whole(self):
        steam_root = self.home / ".steam" / "steam"
        filler = b'"ignorado" "x"\n' * 200_000
        self.write_vdf(steam_root, filler + self.vdf_for([self.tmp / "tarde-demais"]))
        self.assertGreater(len(filler), platform_support.VDF_READ_LIMIT)
        roots = [str(path) for path in platform_support.steam_library_roots(self.home)]
        self.assertNotIn(str(self.tmp / "tarde-demais"), roots)
        self.assertTrue(self.candidates())


class StartupAutoLoadTests(unittest.TestCase):
    """Achar o caminho do save não bastava para o editor abri-lo sozinho.

    ``DEFAULT_SAVE_FILE`` só escolhia a pasta inicial do seletor: ``main`` carregava
    apenas um argumento de linha de comando ou ``player_dump.json``, então o
    usuário confirmava o mesmo arquivo no diálogo a cada abertura.
    """

    def setUp(self):
        import hollyedittbh_final

        self.module = hollyedittbh_final
        self.tmp = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: __import__("shutil").rmtree(self.tmp, ignore_errors=True))
        self.loaded: list[Path] = []

    def run_main(self, argv, *, save_file: Path, app_dir: Path):
        editor = type("FakeEditor", (), {"load_dump": lambda _self, path: self.loaded.append(Path(path))})
        with patch.object(self.module, "Tk", lambda: type("FakeRoot", (), {"mainloop": lambda _s: None})()), \
             patch.object(self.module, "FinalProEditor", lambda _root: editor()), \
             patch.object(self.module.legacy, "DEFAULT_SAVE_FILE", save_file), \
             patch.object(self.module.legacy, "APP_DIR", app_dir), \
             patch.object(self.module.sys, "argv", argv):
            self.module.main()

    def test_the_game_save_is_loaded_on_startup_when_it_exists(self):
        save_file = self.tmp / "SaveFile_Live.es3"
        save_file.write_bytes(b"save")
        self.run_main(["hollyedittbh_final.py"], save_file=save_file, app_dir=self.tmp / "app")
        self.assertEqual(self.loaded, [save_file])

    def test_an_explicit_argument_still_wins_over_the_game_save(self):
        save_file = self.tmp / "SaveFile_Live.es3"
        save_file.write_bytes(b"save")
        requested = self.tmp / "outro.json"
        requested.write_text("{}", encoding="utf-8")
        self.run_main(["hollyedittbh_final.py", str(requested)], save_file=save_file, app_dir=self.tmp / "app")
        self.assertEqual(self.loaded, [requested])

    def test_a_local_dump_still_wins_over_the_game_save(self):
        save_file = self.tmp / "SaveFile_Live.es3"
        save_file.write_bytes(b"save")
        app_dir = self.tmp / "app"
        app_dir.mkdir()
        dump = app_dir / "player_dump.json"
        dump.write_text("{}", encoding="utf-8")
        self.run_main(["hollyedittbh_final.py"], save_file=save_file, app_dir=app_dir)
        self.assertEqual(self.loaded, [dump])

    def test_nothing_is_loaded_when_no_save_was_found(self):
        self.run_main(
            ["hollyedittbh_final.py"],
            save_file=self.tmp / "ausente" / "SaveFile_Live.es3",
            app_dir=self.tmp / "app",
        )
        self.assertEqual(self.loaded, [])


class SteamAppIdTests(unittest.TestCase):
    def test_the_app_id_has_a_single_definition(self):
        """Eram duas constantes homônimas com valores diferentes: ``market_policy``
        trazia 3678970 e ``platform_support`` trazia o AppID do playtest, então a
        procura do save no Linux apontava para uma pasta que não existe."""
        self.assertEqual(app_meta.STEAM_APP_ID, 3678970)
        self.assertIs(market_policy.STEAM_APP_ID, app_meta.STEAM_APP_ID)
        self.assertEqual(platform_support.STEAM_APP_IDS[0], app_meta.STEAM_APP_ID)
        for module in ("market_policy.py", "platform_support.py"):
            source = (BASE / module).read_text(encoding="utf-8")
            self.assertNotIn("STEAM_APP_ID = 3678970", source, f"{module} redefine o AppID")
            self.assertNotIn("2957000", source, f"{module} embute o AppID do playtest")

    def test_the_market_url_still_receives_the_app_id(self):
        """``market_intelligence`` interpola o AppID numa URL e o reexporta."""
        import market_intelligence

        self.assertIs(market_intelligence.STEAM_APP_ID, app_meta.STEAM_APP_ID)
        self.assertIn("STEAM_APP_ID", market_intelligence.__all__)
        self.assertEqual(
            f"{market_intelligence.STEAM_MARKET_SEARCH}?appid={market_intelligence.STEAM_APP_ID}",
            "https://steamcommunity.com/market/search/?appid=3678970",
        )

    def test_the_playtest_id_is_only_a_fallback_for_path_discovery(self):
        self.assertEqual(platform_support.STEAM_APP_IDS, (3678970, 2957000))


class EditorPortabilityTests(unittest.TestCase):
    def test_the_editor_no_longer_hardcodes_a_windows_save_path(self):
        self.assertIn("platform_support.default_game_save_dir()", EDITOR_SOURCE)
        self.assertNotIn('Path.home() / "AppData"', EDITOR_SOURCE)

    def test_the_editor_never_calls_os_startfile_directly(self):
        self.assertNotIn("os.startfile(", EDITOR_SOURCE)
        self.assertIn("platform_support.open_in_file_manager", EDITOR_SOURCE)

    def test_the_font_family_is_resolved_at_runtime(self):
        """Pedir "Segoe UI" no Linux/macOS derruba o Tk numa fonte bitmap antiga."""
        self.assertNotIn('font=("Segoe UI"', EDITOR_SOURCE)
        self.assertIn("platform_support.preferred_font_family", EDITOR_SOURCE)

    def test_the_spec_only_asks_for_windows_resources_on_windows(self):
        spec = (BASE / "HollyEditTBH.spec").read_text(encoding="utf-8")
        self.assertIn("version='version_info.txt' if IS_WINDOWS else None", spec)
        self.assertIn("BUNDLE(", spec)

    def test_windows_only_build_dependencies_carry_a_platform_marker(self):
        requirements = (BASE / "requirements-build.txt").read_text(encoding="utf-8")
        for package in ("pefile==2024.8.26", "pywin32-ctypes==0.2.3"):
            line = next(row for row in requirements.splitlines() if row.startswith(package))
            self.assertIn('sys_platform == "win32"', line)

    def test_ci_builds_and_smoke_tests_all_three_platforms(self):
        workflow = (BASE / ".github" / "workflows" / "tests.yml").read_text(encoding="utf-8")
        for runner in ("windows-latest", "ubuntu-latest", "macos-latest"):
            self.assertIn(runner, workflow)
        for artifact in ("-windows", "-linux", "-macos"):
            self.assertIn(f"HollyEditTBH-v3.4.0{artifact}", workflow)


class ScrollableTableTests(unittest.TestCase):
    """As tabelas não tinham barra de rolagem; a correção introduziu um empilhamento errado."""

    def setUp(self):
        import tkinter as tk

        try:
            self.root = tk.Tk()
        except tk.TclError as exc:  # pragma: no cover - runner sem display
            raise unittest.SkipTest(f"sem display para exercitar o Tk: {exc}")
        self.addCleanup(self.root.destroy)

    def test_every_item_table_gets_a_scrollbar(self):
        from tkinter import ttk

        editor = ProEditor.__new__(ProEditor)
        editor.root = self.root
        parent = ttk.Frame(self.root)
        tree = ttk.Treeview(parent)
        holder = editor.attach_scrollbars(parent, tree)
        bars = [child for child in holder.winfo_children() if child.winfo_class() == "TScrollbar"]
        self.assertEqual(len(bars), 1)
        self.assertTrue(tree.cget("yscrollcommand"))

    def test_the_table_stays_above_its_scroll_container(self):
        """A tabela é irmã do container e foi criada antes dele: sem lift, o
        fundo do container cobre a tabela inteira e ela some da tela mesmo
        continuando populada."""
        from tkinter import ttk

        editor = ProEditor.__new__(ProEditor)
        editor.root = self.root
        parent = ttk.Frame(self.root)
        tree = ttk.Treeview(parent)
        holder = editor.attach_scrollbars(parent, tree)
        stacking = [str(child) for child in parent.winfo_children()]
        self.assertGreater(
            stacking.index(str(tree)),
            stacking.index(str(holder)),
            "a tabela ficou abaixo do container e seria invisível",
        )

    def test_no_table_in_the_editor_is_packed_without_a_scrollbar(self):
        self.assertNotIn("tree.pack(fill=BOTH", EDITOR_SOURCE)
        self.assertGreaterEqual(EDITOR_SOURCE.count("attach_scrollbars"), 10)

    def test_a_tab_taller_than_the_window_can_be_scrolled_to_its_last_button(self):
        """A aba Moedas empilha duas seções: num monitor de 1366x768 o botão
        "Adicionar ao armazém" caía fora da janela e ficava inalcançável."""
        from tkinter import ttk

        editor = ProEditor.__new__(ProEditor)
        editor.root = self.root
        page = ttk.Frame(self.root, height=200, width=400)
        page.pack(fill="both", expand=True)
        page.pack_propagate(False)
        body = editor.scrollable_area(page)
        for index in range(30):
            ttk.Label(body, text=f"linha {index}").pack(fill="x")
        last = ttk.Button(body, text="Adicionar ao armazém")
        last.pack(fill="x")
        self.root.update_idletasks()

        canvas = body.master
        region = [float(value) for value in canvas.cget("scrollregion").split()]
        self.assertGreater(region[3], canvas.winfo_height(), "a área não ficou rolável")
        canvas.yview_moveto(1.0)
        self.root.update_idletasks()
        bottom_of_last = last.winfo_y() + last.winfo_height()
        self.assertLessEqual(
            bottom_of_last - canvas.canvasy(0),
            canvas.winfo_height() + 1,
            "o último botão continua fora da área visível mesmo rolando até o fim",
        )

    def test_action_bars_are_reserved_before_the_expanding_area(self):
        """O pack aloca por ordem: uma tabela com expand=True empacotada antes
        consome toda a cavidade e o botão principal some em telas baixas."""
        self.assertNotIn("buttons.pack(fill=X)\n", EDITOR_SOURCE)
        self.assertIn('buttons.pack(side="bottom", fill=X, before=tabs)', EDITOR_SOURCE)
        self.assertIn('buttons.pack(side="bottom", fill=X, before=table)', EDITOR_SOURCE)


if __name__ == "__main__":
    unittest.main()
