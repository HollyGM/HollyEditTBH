"""Regressões da geometria do armazém.

Duas correções sucessivas, ambas travadas aqui.

A 3.4.2 corrigiu o **tamanho** da página: o editor calculava 66 espaços, o jogo
usa 49 (7x7). O erro não aparecia em teste nenhum porque toda a suíte montava os
saves sintéticos com o mesmo 66 que o produto usava — fixture e código
concordavam no erro. Um save real desmentiu: abas com 0, 13 e 15 itens batem com
49, e os blocos contíguos começam exatamente em múltiplos de 49.

A mesma mudança, porém, inventou um teto: sete abas, nada acima do índice 342.
Treze saves reais do mesmo jogador, do dia 11 ao dia 26 de agosto, mostram
``stashSaveDatas`` sempre com 528 espaços, todos com ``IsUnLock`` verdadeiro — e
o save mais antigo, anterior a qualquer edição, já trazia itens postos pelo
próprio jogo nos índices 361-378 e 419-426. O teto era do editor, não do jogo:
fazia o validador acusar 26 itens legítimos e o Reparar arrastá-los para longe de
onde o jogo os tinha deixado. Agora o número de abas sai do save.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

import legacy_editor
from legacy_editor import STASH_PAGE_COUNT, STASH_PAGE_SIZE
from tbh_save_editor import ProEditor, safe_int


def minimal_player():
    return {
        "itemSaveDatas": [], "heroSaveDatas": [], "inventorySaveDatas": [],
        "stashSaveDatas": [], "remakeTradingStashSaveDatas": [],
    }


def stash_slot(index, uid=0, unlocked=True):
    return {"Index": index, "ItemUniqueId": uid, "IsUnLock": unlocked}


def gear(uid, key=300101):
    return {
        "ItemKey": key, "UniqueId": uid, "PrevUniqueId": 0, "IsChaotic": False,
        "IsBlocked": False, "EnchantCount": [0, 0, 0], "EnchantData": [],
        "ItemGetSourceType": 5, "DecorationAppliedTotalCount": 0,
        "EngravingAppliedTotalCount": 0, "InscriptionAppliedTotalCount": 0,
    }


def headless(player, database=None):
    database = database or [{"ItemKey": "300101", "Name": "Sword", "Rarity": "LEGENDARY", "Type": "GEAR", "StatTypes": []}]
    editor = ProEditor.__new__(ProEditor)
    editor.data = {"account": {}, "player": player}
    editor.items = list(player.get("itemSaveDatas", []))
    editor.db = list(database)
    editor.db_by_key = {str(row["ItemKey"]): row for row in database}
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


#: Todo save real deste jogo traz o armazém com este tamanho.
SLOTS_DO_JOGO = 528
PAGINAS_DO_JOGO = 11


def full_stash(total_slots=SLOTS_DO_JOGO, unlocked=True):
    return [stash_slot(index, unlocked=unlocked) for index in range(total_slots)]


class StashGeometryTests(unittest.TestCase):
    def test_a_page_is_the_seven_by_seven_grid_the_game_shows(self):
        """66 não corresponde a nenhuma aba do jogo; 49 é a grade 7x7."""
        self.assertEqual(STASH_PAGE_SIZE, 49)
        self.assertEqual(STASH_PAGE_SIZE, 7 * 7)

    def test_page_boundaries_reproduce_a_real_save(self):
        """Um save real tinha as abas 1, 2 e 3 com 0, 13 e 15 itens.

        Os índices abaixo são os do save; com página=66 dariam 13, 15 e 25, que
        é o que o editor mostrava e o jogo desmentia."""
        player = minimal_player()
        player["stashSaveDatas"] = full_stash()
        ocupados = list(range(49, 62)) + list(range(98, 113))
        for posicao, index in enumerate(ocupados):
            player["stashSaveDatas"][index]["ItemUniqueId"] = 1000 + posicao
            player["itemSaveDatas"].append(gear(1000 + posicao))
        editor = headless(player)
        contagem = {pagina: 0 for pagina in range(1, editor.stash_page_count() + 1)}
        for slot in player["stashSaveDatas"]:
            if safe_int(slot.get("ItemUniqueId")):
                contagem[editor.stash_page_for_index(safe_int(slot.get("Index")))] += 1
        self.assertEqual(contagem[1], 0)
        self.assertEqual(contagem[2], 13)
        self.assertEqual(contagem[3], 15)

    def test_each_page_offers_exactly_one_grid_of_slots(self):
        player = minimal_player()
        player["stashSaveDatas"] = full_stash(STASH_PAGE_SIZE * 7)
        editor = headless(player)
        for pagina in range(1, 8):
            self.assertEqual(editor.free_slot_count(f"Armazem {pagina}"), STASH_PAGE_SIZE)


class PageCountComesFromTheSaveTests(unittest.TestCase):
    """O editor não pode presumir quantas abas o jogador tem."""

    def test_a_real_save_has_eleven_pages_not_seven(self):
        player = minimal_player()
        player["stashSaveDatas"] = full_stash()
        editor = headless(player)
        self.assertEqual(editor.stash_page_count(), PAGINAS_DO_JOGO)
        self.assertEqual(editor.stash_display_targets()[-1], f"Armazém {PAGINAS_DO_JOGO}")
        self.assertEqual(editor.stash_targets()[-1], f"Armazem {PAGINAS_DO_JOGO}")

    def test_a_smaller_stash_yields_fewer_pages(self):
        player = minimal_player()
        player["stashSaveDatas"] = full_stash(STASH_PAGE_SIZE * 3)
        editor = headless(player)
        self.assertEqual(editor.stash_page_count(), 3)
        self.assertEqual(len(editor.stash_display_targets()), 3)

    def test_without_a_save_the_module_default_is_used(self):
        editor = headless(minimal_player())
        self.assertEqual(editor.stash_page_count(), STASH_PAGE_COUNT)
        self.assertEqual(STASH_PAGE_COUNT, PAGINAS_DO_JOGO)

    def test_every_page_of_the_real_save_can_receive_an_item(self):
        """Com o teto de 343, as abas 8 a 11 eram inalcançáveis pelo editor."""
        player = minimal_player()
        player["stashSaveDatas"] = full_stash()
        editor = headless(player)
        for pagina in range(1, PAGINAS_DO_JOGO + 1):
            item = gear(4000 + pagina)
            player["itemSaveDatas"].append(item)
            editor.items.append(item)
            editor.items_by_uid[4000 + pagina] = item
            index = editor.place_item(4000 + pagina, f"Armazem {pagina}")
            self.assertNotEqual(index, -1, f"Armazém {pagina} recusou o item")
            self.assertEqual(editor.stash_page_for_index(index), pagina)

    def test_auto_fill_uses_the_whole_stash(self):
        """``Automatico`` parava em 343 e dizia "sem espaço" com 185 vagas."""
        player = minimal_player()
        player["stashSaveDatas"] = full_stash()
        editor = headless(player)
        for numero in range(SLOTS_DO_JOGO):
            item = gear(7000 + numero)
            player["itemSaveDatas"].append(item)
            editor.items.append(item)
            editor.items_by_uid[7000 + numero] = item
            self.assertNotEqual(editor.place_item(7000 + numero, "Armazem"), -1)
        ocupados = sum(1 for slot in player["stashSaveDatas"] if safe_int(slot.get("ItemUniqueId")))
        self.assertEqual(ocupados, SLOTS_DO_JOGO)


class UnreachableSlotTests(unittest.TestCase):
    """Inalcançável é o espaço **bloqueado**, não o de índice alto.

    A aba que o jogador não comprou não é desenhada; o item posto lá continua no
    save e some da tela."""

    def build(self, presos=3, livres=None):
        player = minimal_player()
        player["stashSaveDatas"] = full_stash(STASH_PAGE_SIZE * 3)
        # Uma quarta aba, ainda bloqueada, com itens dentro.
        for posicao in range(STASH_PAGE_SIZE):
            player["stashSaveDatas"].append(stash_slot(STASH_PAGE_SIZE * 3 + posicao, unlocked=False))
        for posicao in range(presos):
            slot = player["stashSaveDatas"][STASH_PAGE_SIZE * 3 + posicao]
            slot["ItemUniqueId"] = 500 + posicao
            player["itemSaveDatas"].append(gear(500 + posicao))
        ocupar = STASH_PAGE_SIZE * 3 if livres is None else STASH_PAGE_SIZE * 3 - livres
        for index in range(ocupar):
            uid = 9000 + index
            player["stashSaveDatas"][index]["ItemUniqueId"] = uid
            player["itemSaveDatas"].append(gear(uid))
        return headless(player), player

    def test_items_in_a_locked_page_are_detected(self):
        editor, _ = self.build(presos=3, livres=STASH_PAGE_SIZE)
        presos = editor.unreachable_stash_rows()
        self.assertEqual(len(presos), 3)
        self.assertEqual(
            sorted(safe_int(row["item"].get("UniqueId")) for row in presos), [500, 501, 502]
        )

    def test_the_validator_warns_instead_of_staying_silent(self):
        editor, _ = self.build(presos=2, livres=STASH_PAGE_SIZE)
        avisos = [issue for issue in editor.validate_save() if issue["code"] == "unreachable_slot"]
        self.assertEqual(len(avisos), 2)
        self.assertEqual({issue["severity"] for issue in avisos}, {"AVISO"})
        self.assertIn("não aparece no jogo", avisos[0]["message"])

    def test_rescue_moves_them_back_without_creating_or_losing_anything(self):
        editor, player = self.build(presos=3, livres=STASH_PAGE_SIZE)
        antes = {safe_int(i.get("UniqueId")) for i in player["itemSaveDatas"]}
        resgatados, sem_espaco = editor.rescue_unreachable_stash_items()
        editor.rebuild_item_index()
        depois = {safe_int(i.get("UniqueId")) for i in player["itemSaveDatas"]}

        self.assertEqual((resgatados, sem_espaco), (3, 0))
        self.assertEqual(antes, depois, "o resgate criou ou apagou item")
        self.assertEqual(editor.unreachable_stash_rows(), [])
        alocados = [
            slot for slot in player["stashSaveDatas"]
            if safe_int(slot.get("ItemUniqueId")) in {500, 501, 502}
        ]
        self.assertEqual(len(alocados), 3)
        self.assertTrue(all(slot.get("IsUnLock") for slot in alocados))

    def test_no_unique_id_is_duplicated_by_the_rescue(self):
        editor, player = self.build(presos=3, livres=STASH_PAGE_SIZE)
        editor.rescue_unreachable_stash_items()
        ocupados = [
            safe_int(slot.get("ItemUniqueId")) for slot in player["stashSaveDatas"]
            if safe_int(slot.get("ItemUniqueId"))
        ]
        self.assertEqual(len(ocupados), len(set(ocupados)))

    def test_rescue_reports_what_did_not_fit(self):
        """Sem espaço livre desbloqueado, o item preso continua onde está."""
        editor, _ = self.build(presos=3, livres=0)
        resgatados, sem_espaco = editor.rescue_unreachable_stash_items()
        self.assertEqual((resgatados, sem_espaco), (0, 3))
        self.assertEqual(len(editor.unreachable_stash_rows()), 3)

    def test_rescue_is_idempotent(self):
        editor, _ = self.build(presos=3, livres=STASH_PAGE_SIZE)
        self.assertEqual(editor.rescue_unreachable_stash_items(), (3, 0))
        self.assertEqual(editor.rescue_unreachable_stash_items(), (0, 0))

    def test_repair_performs_the_rescue(self):
        """O usuário chega nisso pelo botão Reparar, não por uma API."""
        editor, player = self.build(presos=3, livres=STASH_PAGE_SIZE)
        with patch.object(legacy_editor.messagebox, "showinfo"):
            editor.repair_save(show_message=False)
        self.assertEqual(editor.unreachable_stash_rows(), [])
        self.assertEqual(
            len([i for i in player["itemSaveDatas"] if safe_int(i.get("UniqueId")) in {500, 501, 502}]), 3
        )

    def test_a_fully_unlocked_stash_is_left_alone(self):
        player = minimal_player()
        player["stashSaveDatas"] = full_stash()
        editor = headless(player)
        self.assertEqual(editor.unreachable_stash_rows(), [])
        self.assertEqual(editor.rescue_unreachable_stash_items(), (0, 0))


class ItemsThePlayerAlreadyHadTests(unittest.TestCase):
    """A regressão concreta: um save real do jogo, sem edição nenhuma."""

    def real_save(self):
        """Reproduz o save de 11/08: 528 espaços e cinco blocos ocupados.

        Os índices 361-378 e 419-426 vieram do jogo, não do editor — estão em
        todos os saves diários desde o dia 11."""
        player = minimal_player()
        player["stashSaveDatas"] = full_stash()
        blocos = [range(9, 28), range(49, 61), range(98, 113), range(361, 379), range(419, 427)]
        uid = 1
        for bloco in blocos:
            for index in bloco:
                player["stashSaveDatas"][index]["ItemUniqueId"] = uid
                player["itemSaveDatas"].append(gear(uid))
                uid += 1
        return headless(player), player

    def test_the_game_own_high_index_items_are_not_flagged(self):
        editor, _ = self.real_save()
        self.assertEqual(editor.unreachable_stash_rows(), [])
        avisos = [i for i in editor.validate_save() if i["code"] == "unreachable_slot"]
        self.assertEqual(avisos, [], "o validador acusou item que o jogo pôs ali")

    def test_repair_does_not_move_them(self):
        editor, player = self.real_save()
        antes = {
            safe_int(slot.get("Index")): safe_int(slot.get("ItemUniqueId"))
            for slot in player["stashSaveDatas"]
        }
        with patch.object(legacy_editor.messagebox, "showinfo"):
            editor.repair_save(show_message=False)
        depois = {
            safe_int(slot.get("Index")): safe_int(slot.get("ItemUniqueId"))
            for slot in player["stashSaveDatas"]
        }
        self.assertEqual(antes, depois, "o Reparar mexeu em item que estava no lugar")

    def test_they_show_up_in_the_editor_pages(self):
        editor, _ = self.real_save()
        paginas = {editor.stash_page_for_index(i) for i in list(range(361, 379)) + list(range(419, 427))}
        self.assertEqual(paginas, {8, 9})
        self.assertLessEqual(max(paginas), editor.stash_page_count())


if __name__ == "__main__":
    unittest.main()
