"""Moedas comemorativas (Anniversary Coins) do TBH: Task Bar Hero.

As dez moedas ocupam a faixa 160001-160010 do catálogo, são do tipo MATERIAL e
cobrem uma raridade cada, de Comum a Cósmico. Elas entram na aba Oferenda do
Cubo e devolvem um equipamento aleatório; caem de baús e não são fabricadas.
Por serem MATERIAL, negociam no Mercado em qualquer raridade — ao contrário do
equipamento, que só negocia de Lendário para cima.

Este módulo é a parte de dados e de planejamento de quem já existe no save. Ele
não toca em tkinter e não grava nada: monta um plano de movimentação que a
interface confirma e o editor aplica pelo mesmo caminho transacional das
demais filas.

Criar moedas novas não é responsabilidade deste módulo: a aba Moedas usa o
fluxo genérico de criação de itens do editor (``ProEditor.create_item``), o
mesmo caminho usado para qualquer outro item do catálogo.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Sequence

FIRST_COIN_KEY = 160001
LAST_COIN_KEY = 160010

KINGDOM = "Kingdom"
EMPIRE = "Empire"


@dataclass(frozen=True)
class CoinDefinition:
    item_key: int
    name: str
    rarity: str
    faction: str
    anniversary: int

    @property
    def display_name(self) -> str:
        faction = "Reino" if self.faction == KINGDOM else "Império"
        return f"{faction} · {self.anniversary}º aniversário"


#: Registro canônico. Os nomes seguem o catálogo oficial em inglês; a coluna de
#: raridade é a mesma publicada em tbh_items_cache.json e é reconferida em teste.
COIN_DEFINITIONS: tuple[CoinDefinition, ...] = (
    CoinDefinition(160001, "Kingdom 1st Anniversary Coin", "COMMON", KINGDOM, 1),
    CoinDefinition(160002, "Empire 1st Anniversary Coin", "UNCOMMON", EMPIRE, 1),
    CoinDefinition(160003, "Kingdom 10th Anniversary Coin", "RARE", KINGDOM, 10),
    CoinDefinition(160004, "Empire 10th Anniversary Coin", "LEGENDARY", EMPIRE, 10),
    CoinDefinition(160005, "Kingdom 50th Anniversary Coin", "IMMORTAL", KINGDOM, 50),
    CoinDefinition(160006, "Empire 50th Anniversary Coin", "ARCANA", EMPIRE, 50),
    CoinDefinition(160007, "Kingdom 100th Anniversary Coin", "BEYOND", KINGDOM, 100),
    CoinDefinition(160008, "Empire 100th Anniversary Coin", "CELESTIAL", EMPIRE, 100),
    CoinDefinition(160009, "Sacred Kingdom 1000th Anniversary Coin", "DIVINE", KINGDOM, 1000),
    CoinDefinition(160010, "Eternal Empire 1000th Anniversary Coin", "COSMIC", EMPIRE, 1000),
)

COIN_BY_KEY: dict[int, CoinDefinition] = {coin.item_key: coin for coin in COIN_DEFINITIONS}
COIN_KEYS: frozenset[int] = frozenset(COIN_BY_KEY)

USAGE_NOTICE = (
    "Moedas comemorativas são consumidas na aba Oferenda do Cubo e devolvem um "
    "equipamento aleatório. Caem de baús; não existe receita para fabricá-las."
)

MARKET_NOTICE = (
    "Por serem MATERIAL, negociam no Mercado em qualquer raridade — inclusive "
    "Divino e Cósmico, que ficam bloqueados quando são equipamento."
)


def is_coin_key(item_key: object) -> bool:
    try:
        return int(item_key) in COIN_KEYS
    except (TypeError, ValueError):
        return False


def coin_for_item(item: Mapping | None) -> CoinDefinition | None:
    if not isinstance(item, Mapping):
        return None
    try:
        return COIN_BY_KEY.get(int(item.get("ItemKey")))
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class CoinGroup:
    """Uma linha do resumo: uma moeda e onde suas cópias estão."""

    definition: CoinDefinition
    rows: tuple[Mapping, ...]
    locations: tuple[str, ...]

    @property
    def count(self) -> int:
        return len(self.rows)


@dataclass
class CoinPlan:
    """Plano de consolidação para uma página do armazém."""

    stash_page: int
    movable: list[Mapping] = field(default_factory=list)
    already_there: list[Mapping] = field(default_factory=list)
    capacity: int = 0
    page_unlocked: bool = True
    total_found: int = 0

    @property
    def left_out(self) -> int:
        """Moedas que ficaram de fora por falta de espaço na página."""
        return max(0, len(self.movable) - self.moving)

    @property
    def moving(self) -> int:
        return min(len(self.movable), max(0, self.capacity))

    @property
    def rows_to_apply(self) -> list[Mapping]:
        return self.movable[: self.moving]

    def summary(self) -> str:
        if not self.total_found:
            return "Nenhuma moeda comemorativa encontrada no inventário ou no armazém."
        if not self.page_unlocked:
            return (
                f"{self.total_found} moeda(s) encontrada(s), mas o Armazém {self.stash_page} "
                "está bloqueado neste save. Escolha uma página já liberada."
            )
        parts = [f"{self.total_found} moeda(s) encontrada(s)"]
        if self.already_there:
            parts.append(f"{len(self.already_there)} já no Armazém {self.stash_page}")
        if self.moving:
            parts.append(f"{self.moving} a mover")
        if self.left_out:
            parts.append(f"{self.left_out} sem espaço nesta página")
        if not self.moving and not self.left_out:
            parts.append("nada a mover")
        return " · ".join(parts) + "."


def collect_coin_rows(
    storage_rows: Iterable[Mapping],
    *,
    item_key_of: Callable[[Mapping], object] = lambda item: item.get("ItemKey"),
) -> list[Mapping]:
    """Filtra as linhas de armazenamento que são moedas comemorativas.

    ``storage_rows`` usa o mesmo formato de ``ProEditor.storage_item_rows``:
    dicionários com ``item``, ``source`` e ``source_slot``.
    """
    result: list[Mapping] = []
    for row in storage_rows:
        item = row.get("item") if isinstance(row, Mapping) else None
        if isinstance(item, Mapping) and is_coin_key(item_key_of(item)):
            result.append(row)
    return result


def group_coins(
    coin_rows: Sequence[Mapping],
    *,
    location_of: Callable[[Mapping], str] = lambda row: "",
) -> list[CoinGroup]:
    """Agrupa as moedas por chave, na ordem crescente de raridade do registro."""
    buckets: dict[int, list[Mapping]] = {}
    for row in coin_rows:
        coin = coin_for_item(row.get("item"))
        if coin is not None:
            buckets.setdefault(coin.item_key, []).append(row)
    groups: list[CoinGroup] = []
    for definition in COIN_DEFINITIONS:
        rows = buckets.get(definition.item_key)
        if not rows:
            continue
        seen: list[str] = []
        for row in rows:
            label = location_of(row)
            if label and label not in seen:
                seen.append(label)
        groups.append(CoinGroup(definition, tuple(rows), tuple(seen)))
    return groups


def build_coin_plan(
    coin_rows: Sequence[Mapping],
    stash_page: int,
    *,
    capacity: int,
    page_unlocked: bool = True,
    page_of_row: Callable[[Mapping], int | None] = lambda row: None,
) -> CoinPlan:
    """Monta o plano de consolidação sem alterar nada.

    ``page_of_row`` devolve a página do armazém em que a linha já está, ou
    ``None`` quando ela está no inventário. Moedas que já ocupam a página de
    destino não são movidas — evita gastar espaço trocando um slot por outro.
    """
    plan = CoinPlan(stash_page=stash_page, capacity=max(0, capacity), page_unlocked=page_unlocked)
    plan.total_found = len(coin_rows)
    if not page_unlocked:
        plan.capacity = 0
    for row in coin_rows:
        if page_of_row(row) == stash_page:
            plan.already_there.append(row)
        else:
            plan.movable.append(row)
    # Ordem estável e previsível: raridade mais alta primeiro, depois a chave.
    plan.movable.sort(key=_coin_sort_key)
    plan.already_there.sort(key=_coin_sort_key)
    return plan


_RARITY_ORDER = {
    "COMMON": 1, "UNCOMMON": 2, "RARE": 3, "LEGENDARY": 4, "IMMORTAL": 5,
    "ARCANA": 6, "BEYOND": 7, "CELESTIAL": 8, "DIVINE": 9, "COSMIC": 10,
}


def _coin_sort_key(row: Mapping) -> tuple[int, int, int]:
    coin = coin_for_item(row.get("item"))
    if coin is None:
        return (0, 0, 0)
    item = row.get("item") or {}
    try:
        uid = int(item.get("UniqueId") or 0)
    except (TypeError, ValueError):
        uid = 0
    return (-_RARITY_ORDER.get(coin.rarity, 0), coin.item_key, uid)
