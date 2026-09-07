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

A 3.4.2 tentou substituir o número de abas por uma medida tirada de
``len(stashSaveDatas)`` e chegou a 11, oferecendo destinos que a tela do jogo não
tem. ``GameScreenGeometryTests``, abaixo, fecha essa porta: os números vêm da
captura da tela do jogo, não da aritmética do vetor de espaços.
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
    # `total_slots or STASH_REACHABLE_SLOTS` devolveria o armazém cheio para
    # total_slots=0, escondendo um caso de teste em vez de montá-lo.
    if total_slots is None:
        total_slots = STASH_REACHABLE_SLOTS
    return [stash_slot(index, unlocked=unlocked) for index in range(total_slots)]


class StashGeometryTests(unittest.TestCase):
    def test_a_page_is_the_seven_by_seven_grid_the_game_shows(self):
        """66 não corresponde a nenhuma aba do jogo; 49 é a grade 7x7."""
        self.assertEqual(STASH_PAGE_SIZE, 49)
        self.assertEqual(STASH_PAGE_SIZE, 7 * 7)
        self.assertEqual(STASH_REACHABLE_SLOTS, STASH_PAGE_SIZE * STASH_PAGE_COUNT)
        self.assertEqual(STASH_REACHABLE_SLOTS, 343)

    def test_the_limit_is_a_count_and_the_last_visible_index_is_one_below(self):
        """``STASH_REACHABLE_SLOTS`` é contagem, não índice.

        Trocar ``<`` por ``<=`` em qualquer um dos dois usos, ou ler o 343 como
        último índice, faz o editor gravar no primeiro espaço que o jogo não
        desenha — que é o defeito inteiro."""
        player = minimal_player()
        player["stashSaveDatas"] = full_stash(STASH_REACHABLE_SLOTS + 1)
        ultimo, primeiro_invisivel = STASH_REACHABLE_SLOTS - 1, STASH_REACHABLE_SLOTS
        self.assertEqual(ultimo, 342)
        editor = headless(player)

        for index, uid in ((ultimo, 601), (primeiro_invisivel, 602)):
            item = gear(uid)
            player["itemSaveDatas"].append(item)
            editor.items.append(item)
            editor.items_by_uid[uid] = item
            player["stashSaveDatas"][index]["ItemUniqueId"] = uid

        presos = [safe_int(row["slot"].get("Index")) for row in editor.unreachable_stash_rows()]
        self.assertEqual(presos, [primeiro_invisivel], "o 342 é visível; o 343 não é")
        self.assertEqual(editor.stash_page_for_index(ultimo), STASH_PAGE_COUNT)
        self.assertEqual(editor.stash_page_for_index(primeiro_invisivel), STASH_PAGE_COUNT + 1)

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


#: O armazém de um save real: 528 espaços gravados, índices 0 a 527, todos com
#: ``IsUnLock`` verdadeiro. O jogo mostra 343 deles.
SLOTS_NO_SAVE = 528

#: Ocupação por aba na tela do jogo, do mesmo save. Conferido por captura: aba 1
#: vazia, aba 2 com 13, e as abas 5, 6 e 7 cheias. Só existem estas sete.
ABAS_NA_TELA = {1: 0, 2: 13, 3: 15, 4: 23, 5: 49, 6: 49, 7: 49}

#: Índices ocupados no mesmo save, incluindo os dois blocos acima de 342 que o
#: editor antigo gravou e o jogo não desenha.
BLOCOS_DO_SAVE = [
    range(49, 62), range(98, 113), range(147, 170), range(196, 343),
    range(361, 379), range(419, 427),
]


class GameScreenGeometryTests(unittest.TestCase):
    """Os números vêm da tela do jogo, não da aritmética do vetor de espaços.

    A 3.4.2 derivou o número de abas de ``len(stashSaveDatas)`` — 528 espaços,
    todos destravados, dão 11 páginas de 49 — e o editor passou a oferecer
    "Armazém 8" a "Armazém 11", que não existem. A captura da tela mostra sete
    abas numeradas de 1 a 7 e uma grade 7x7."""

    def real_save(self):
        player = minimal_player()
        player["stashSaveDatas"] = full_stash(SLOTS_NO_SAVE)
        uid = 1
        for bloco in BLOCOS_DO_SAVE:
            for index in bloco:
                player["stashSaveDatas"][index]["ItemUniqueId"] = uid
                player["itemSaveDatas"].append(gear(uid))
                uid += 1
        return headless(player), player

    def test_the_stash_has_seven_tabs_however_many_slots_the_save_allocates(self):
        self.assertEqual(STASH_PAGE_COUNT, 7)
        self.assertEqual(STASH_REACHABLE_SLOTS, 343)
        self.assertGreater(SLOTS_NO_SAVE, STASH_REACHABLE_SLOTS, "premissa do teste")

    def test_the_editor_offers_exactly_the_tabs_the_game_draws(self):
        editor, _ = self.real_save()
        destinos = [alvo for alvo in legacy_editor.ITEM_DESTINATIONS if alvo.startswith("Armazem ")]
        self.assertEqual(destinos, [f"Armazem {p}" for p in range(1, 8)])
        self.assertEqual(editor.destination_sources("Armazem 8"), [("inventorySaveDatas", None)])
        self.assertEqual(editor.slots_for_destination("Armazem 8"), [])

    def test_each_tab_holds_what_the_screenshots_show(self):
        editor, player = self.real_save()
        contagem = {pagina: 0 for pagina in ABAS_NA_TELA}
        for slot in player["stashSaveDatas"]:
            if not safe_int(slot.get("ItemUniqueId")):
                continue
            pagina = editor.stash_page_for_index(safe_int(slot.get("Index")))
            if pagina in contagem:
                contagem[pagina] += 1
        self.assertEqual(contagem, ABAS_NA_TELA)

    def test_what_sits_past_the_last_tab_is_exactly_the_stuck_block(self):
        """26 itens: 18 no bloco 361-378 e 8 no 419-426, gravados pelo editor
        antigo, que achava que a faixa útil ia até 461."""
        editor, _ = self.real_save()
        presos = editor.unreachable_stash_rows()
        self.assertEqual(len(presos), 26)
        indices = sorted(safe_int(row["slot"].get("Index")) for row in presos)
        self.assertEqual(indices, list(range(361, 379)) + list(range(419, 427)))

    def test_the_rescue_brings_all_of_them_into_a_visible_tab(self):
        editor, player = self.real_save()
        antes = {safe_int(i.get("UniqueId")) for i in player["itemSaveDatas"]}
        self.assertEqual(editor.rescue_unreachable_stash_items(), (26, 0))
        depois = {safe_int(i.get("UniqueId")) for i in player["itemSaveDatas"]}
        self.assertEqual(antes, depois, "o resgate criou ou apagou item")
        ocupados = [
            safe_int(slot.get("Index")) for slot in player["stashSaveDatas"]
            if safe_int(slot.get("ItemUniqueId"))
        ]
        self.assertEqual(len(ocupados), len(set(ocupados)))
        self.assertLess(max(ocupados), STASH_REACHABLE_SLOTS)
        self.assertEqual(editor.unreachable_stash_rows(), [])


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
        self.assertEqual({issue["severity"] for issue in avisos}, {"ERRO"})
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
