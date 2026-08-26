"""Regressões da geometria do armazém.

O editor calculava a página do armazém com 66 espaços. O jogo usa 49 (7x7), e a
diferença não era visível em teste nenhum porque toda a suíte montava os saves
sintéticos com o mesmo 66 que o produto usava — fixture e código concordavam no
erro. Só um save real expôs o problema: as abas com 0, 13 e 15 itens batem com 49
e não com 66.

Duas consequências, ambas cobertas aqui: os rótulos de página ficavam deslocados
(a "Armazém 3" do editor caía no meio da aba 4 do jogo) e o editor gravava itens
em índices além da última aba exibida, onde o item continua no save e some da
tela do jogo.
"""
from __future__ import annotations

import unittest
from unittest.mock import patch

import legacy_editor
from legacy_editor import STASH_PAGE_COUNT, STASH_PAGE_SIZE, STASH_REACHABLE_SLOTS
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


def full_stash(total_slots=None, unlocked=True):
    return [stash_slot(index, unlocked=unlocked) for index in range(total_slots or STASH_REACHABLE_SLOTS)]


class StashGeometryTests(unittest.TestCase):
    def test_a_page_is_the_seven_by_seven_grid_the_game_shows(self):
        """66 não corresponde a nenhuma aba do jogo; 49 é a grade 7x7."""
        self.assertEqual(STASH_PAGE_SIZE, 49)
        self.assertEqual(STASH_PAGE_SIZE, 7 * 7)
        self.assertEqual(STASH_REACHABLE_SLOTS, STASH_PAGE_SIZE * STASH_PAGE_COUNT)
        self.assertEqual(STASH_REACHABLE_SLOTS, 343)

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
        contagem = {pagina: 0 for pagina in range(1, STASH_PAGE_COUNT + 1)}
        for slot in player["stashSaveDatas"]:
            if safe_int(slot.get("ItemUniqueId")):
                contagem[editor.stash_page_for_index(safe_int(slot.get("Index")))] += 1
        self.assertEqual(contagem[1], 0)
        self.assertEqual(contagem[2], 13)
        self.assertEqual(contagem[3], 15)

    def test_each_page_offers_exactly_one_grid_of_slots(self):
        player = minimal_player()
        player["stashSaveDatas"] = full_stash()
        editor = headless(player)
        for pagina in range(1, STASH_PAGE_COUNT + 1):
            self.assertEqual(editor.free_slot_count(f"Armazem {pagina}"), STASH_PAGE_SIZE)


class UnreachableSlotTests(unittest.TestCase):
    """``stashSaveDatas`` vem maior que as abas exibidas; escrever além delas
    grava o item no save e o esconde do jogo, sem qualquer aviso."""

    def build(self, presos=3, livres_por_pagina=STASH_PAGE_SIZE):
        player = minimal_player()
        # Espaços além do alcance existem no save real; aqui uma página extra.
        player["stashSaveDatas"] = full_stash(STASH_REACHABLE_SLOTS + STASH_PAGE_SIZE)
        for posicao in range(presos):
            index = STASH_REACHABLE_SLOTS + posicao
            player["stashSaveDatas"][index]["ItemUniqueId"] = 500 + posicao
            player["itemSaveDatas"].append(gear(500 + posicao))
        ocupar = STASH_PAGE_SIZE - livres_por_pagina
        for pagina in range(STASH_PAGE_COUNT):
            for posicao in range(ocupar):
                index = pagina * STASH_PAGE_SIZE + posicao
                uid = 9000 + index
                player["stashSaveDatas"][index]["ItemUniqueId"] = uid
                player["itemSaveDatas"].append(gear(uid))
        return headless(player), player

    def test_no_destination_ever_writes_past_the_last_visible_page(self):
        """A causa raiz: o editor achava que a faixa ia até 461 e escrevia lá."""
        player = minimal_player()
        player["stashSaveDatas"] = full_stash(STASH_REACHABLE_SLOTS + STASH_PAGE_SIZE)
        editor = headless(player)
        for numero in range(STASH_REACHABLE_SLOTS + 10):
            item = gear(7000 + numero)
            player["itemSaveDatas"].append(item)
            editor.items.append(item)
            editor.items_by_uid[7000 + numero] = item
            editor.place_item(7000 + numero, "Automatico")
        usados = [
            safe_int(slot.get("Index")) for slot in player["stashSaveDatas"]
            if safe_int(slot.get("ItemUniqueId"))
        ]
        self.assertTrue(usados, "nada foi colocado no armazém")
        self.assertLess(max(usados), STASH_REACHABLE_SLOTS, "o editor escreveu onde o jogo não mostra")

    def test_items_past_the_last_page_are_detected(self):
        editor, _ = self.build(presos=3)
        presos = editor.unreachable_stash_rows()
        self.assertEqual(len(presos), 3)
        self.assertEqual(
            sorted(safe_int(row["item"].get("UniqueId")) for row in presos), [500, 501, 502]
        )

    def test_the_validator_warns_instead_of_staying_silent(self):
        editor, _ = self.build(presos=2)
        avisos = [issue for issue in editor.validate_save() if issue["code"] == "unreachable_slot"]
        self.assertEqual(len(avisos), 2)
        self.assertEqual({issue["severity"] for issue in avisos}, {"AVISO"})
        self.assertIn("não aparece no jogo", avisos[0]["message"])

    def test_rescue_moves_them_back_without_creating_or_losing_anything(self):
        editor, player = self.build(presos=3)
        antes = {safe_int(i.get("UniqueId")) for i in player["itemSaveDatas"]}
        resgatados, sem_espaco = editor.rescue_unreachable_stash_items()
        editor.rebuild_item_index()
        depois = {safe_int(i.get("UniqueId")) for i in player["itemSaveDatas"]}

        self.assertEqual((resgatados, sem_espaco), (3, 0))
        self.assertEqual(antes, depois, "o resgate criou ou apagou item")
        self.assertEqual(editor.unreachable_stash_rows(), [])
        alocados = [
            safe_int(slot.get("Index")) for slot in player["stashSaveDatas"]
            if safe_int(slot.get("ItemUniqueId")) in {500, 501, 502}
        ]
        self.assertEqual(len(alocados), 3)
        self.assertTrue(all(index < STASH_REACHABLE_SLOTS for index in alocados))

    def test_no_unique_id_is_duplicated_by_the_rescue(self):
        editor, player = self.build(presos=3)
        editor.rescue_unreachable_stash_items()
        ocupados = [
            safe_int(slot.get("ItemUniqueId")) for slot in player["stashSaveDatas"]
            if safe_int(slot.get("ItemUniqueId"))
        ]
        self.assertEqual(len(ocupados), len(set(ocupados)))

    def test_rescue_reports_what_did_not_fit(self):
        """Sem espaço livre, o item preso continua onde está e é contado."""
        editor, _ = self.build(presos=3, livres_por_pagina=0)
        resgatados, sem_espaco = editor.rescue_unreachable_stash_items()
        self.assertEqual((resgatados, sem_espaco), (0, 3))
        self.assertEqual(len(editor.unreachable_stash_rows()), 3)

    def test_rescue_is_idempotent(self):
        editor, _ = self.build(presos=3)
        self.assertEqual(editor.rescue_unreachable_stash_items(), (3, 0))
        self.assertEqual(editor.rescue_unreachable_stash_items(), (0, 0))

    def test_repair_performs_the_rescue(self):
        """O usuário chega nisso pelo botão Reparar, não por uma API."""
        editor, player = self.build(presos=3)
        with patch.object(legacy_editor.messagebox, "showinfo"):
            editor.repair_save(show_message=False)
        self.assertEqual(editor.unreachable_stash_rows(), [])
        self.assertEqual(
            len([i for i in player["itemSaveDatas"] if safe_int(i.get("UniqueId")) in {500, 501, 502}]), 3
        )

    def test_a_save_without_extra_slots_is_left_alone(self):
        player = minimal_player()
        player["stashSaveDatas"] = full_stash()
        editor = headless(player)
        self.assertEqual(editor.unreachable_stash_rows(), [])
        self.assertEqual(editor.rescue_unreachable_stash_items(), (0, 0))


if __name__ == "__main__":
    unittest.main()
