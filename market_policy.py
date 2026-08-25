"""Fonte única da política de Mercado do TBH: Task Bar Hero.

Antes da 3.4.0 a mesma política vivia em dois lugares com valores divergentes:
``legacy_editor.MARKET_POLICY_CHECKED_AT`` ("12/08/2026") e
``market_intelligence.POLICY_CHECKED_AT`` ("2026-07-06"). As duas datas
apareciam na mesma janela do editor. Este módulo passa a ser a única
definição; os demais módulos importam daqui.

Regras públicas confirmadas para a data em POLICY_CHECKED_AT:

* o Navio de Trocas — a única porta entre o save e o inventário Steam — só
  abre com o Cubo no nível 10; abaixo disso nenhum item do save pode virar
  item Steam, por mais elegível que a raridade seja;
* equipamento (GEAR) só é negociável a partir de Lendário: Comum, Incomum e
  Raro foram retirados do Mercado;
* equipamento Celestial, Divino e Cósmico segue bloqueado "por enquanto",
  com exceção conhecida para Soulstones;
* material (MATERIAL) é negociável em qualquer raridade — é por isso que as
  moedas comemorativas entram mesmo sendo Cósmicas;
* a conta precisa de Steam Guard ativo para listar.

Nada aqui promete aceitação, preço ou venda: a decisão final é do jogo e da
Steam no momento da listagem.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

from app_meta import STEAM_APP_ID as STEAM_APP_ID_FROM_META

# Data da última conferência das regras públicas descritas acima.
POLICY_CHECKED_AT = "2026-08-21"

# Aviso oficial do jogo; continua sendo a fonte final de verdade.
OFFICIAL_NEWS_URL = "https://steamcommunity.com/app/3678970/allnews/"

#: Reexportado de app_meta, que é a fonte única. O nome continua disponível aqui
#: porque market_intelligence o importa deste módulo e o publica no ``__all__``.
STEAM_APP_ID = STEAM_APP_ID_FROM_META

#: Nível do Cubo que libera o Navio de Trocas (e, por consequência, o Mercado).
CUBE_MARKET_UNLOCK_LEVEL = 10

#: Slots de anúncio considerados por rodada. Conservador por padrão.
BASE_LISTING_SLOTS = 4

#: Equipamento abaixo de Lendário foi removido do Mercado.
LOW_GRADE_GEAR_BLOCKED = frozenset({"COMMON", "UNCOMMON", "RARE"})

#: Os três graus do topo seguem restritos, salvo Soulstones.
HIGH_GRADE_GEAR_BLOCKED = frozenset({"CELESTIAL", "DIVINE", "COSMIC"})

#: Origens que o editor não consegue verificar como legítimas.
SOURCE_TYPES_EXCLUDED = frozenset({0, 10})

#: Chaves toleradas para o nível do Cubo em ``player["cubeSaveLevelData"]``.
_CUBE_LEVEL_KEYS = ("Level", "CubeLevel", "level", "cubeLevel")

STEAM_GUARD_NOTICE = (
    "A Steam exige Steam Guard ativo na conta para listar itens no Mercado. "
    "O editor não verifica nem altera esse estado."
)


@dataclass(frozen=True)
class MarketEligibility:
    allowed: bool
    reason: str
    policy_checked_at: str = POLICY_CHECKED_AT


@dataclass(frozen=True)
class TradeShipStatus:
    """Estado do Navio de Trocas deduzido do save carregado.

    ``unlocked`` é ``True`` quando o nível lido alcança o requisito e ``False``
    quando ele comprovadamente não alcança. Quando o save não expõe o nível de
    forma reconhecível, ``level`` é ``None`` e ``unlocked`` fica ``True``: o
    editor informa a incerteza em vez de bloquear uma conta que talvez já
    tenha acesso.
    """

    unlocked: bool
    level: int | None
    required_level: int = CUBE_MARKET_UNLOCK_LEVEL

    @property
    def known(self) -> bool:
        return self.level is not None

    @property
    def reason(self) -> str:
        if not self.known:
            return (
                "nível do Cubo não reconhecido neste save; o Navio de Trocas exige "
                f"nível {self.required_level} e a verificação real acontece no jogo"
            )
        if self.unlocked:
            return f"Navio de Trocas liberado (Cubo nível {self.level})"
        return (
            f"Cubo nível {self.level}: o Navio de Trocas abre no nível {self.required_level}. "
            "Enquanto isso nenhum item do save pode ser enviado à Steam"
        )

    @property
    def short_reason(self) -> str:
        """Versão curta para colunas estreitas de tabela."""
        if not self.known:
            return f"nível do Cubo não reconhecido; exigido {self.required_level}"
        if self.unlocked:
            return f"Cubo nível {self.level} (exigido {self.required_level})"
        return f"Cubo nível {self.level}; abre no nível {self.required_level}"


def cube_level(player: Mapping | None) -> int | None:
    """Lê o nível do Cubo tolerando as formas conhecidas de ``cubeSaveLevelData``."""
    if not isinstance(player, Mapping):
        return None
    raw = player.get("cubeSaveLevelData")
    records: list[Mapping] = []
    if isinstance(raw, Mapping):
        records = [raw]
    elif isinstance(raw, (list, tuple)):
        records = [row for row in raw if isinstance(row, Mapping)]
    best: int | None = None
    for record in records:
        for key in _CUBE_LEVEL_KEYS:
            if key not in record:
                continue
            try:
                value = int(record[key])
            except (TypeError, ValueError):
                continue
            if 0 <= value <= 9999 and (best is None or value > best):
                best = value
    return best


def trade_ship_status(player: Mapping | None) -> TradeShipStatus:
    """Diz se o save já tem o Navio de Trocas liberado."""
    level = cube_level(player)
    if level is None:
        return TradeShipStatus(True, None)
    return TradeShipStatus(level >= CUBE_MARKET_UNLOCK_LEVEL, level)


def market_eligibility(item_type: str, rarity: str, *, is_soulstone: bool = False) -> MarketEligibility:
    """Elegibilidade por tipo e raridade, sem considerar o estado da conta."""
    kind = str(item_type or "").upper()
    grade = str(rarity or "").upper()
    if kind == "GEAR" and grade in LOW_GRADE_GEAR_BLOCKED:
        return MarketEligibility(False, f"equipamento {grade} ou inferior não é elegível pela política conhecida")
    if kind == "GEAR" and grade in HIGH_GRADE_GEAR_BLOCKED and not is_soulstone:
        return MarketEligibility(False, f"equipamento {grade} permanece bloqueado pela última política oficial confirmada")
    return MarketEligibility(True, "pré-candidato; a confirmação final continua sendo feita pelo Navio de Trocas")


def policy_summary(player: Mapping | None = None, *, compact: bool = False) -> str:
    """Texto único usado pela interface, sem duplicar datas nem regras."""
    status = trade_ship_status(player) if player is not None else None
    if compact:
        return (
            f"Política conferida em {POLICY_CHECKED_AT}: equipamento negocia de Lendário para cima; "
            "Celestial, Divino e Cósmico seguem restritos (exceto Soulstones); material negocia em "
            "qualquer raridade. A conta precisa de Steam Guard. O editor usa apenas snapshot público "
            "do Community Market: não acessa login nem promete preço, venda ou aceitação."
        )
    lines = [
        f"Política conferida em {POLICY_CHECKED_AT}.",
        "Equipamento negocia a partir de Lendário; Comum, Incomum e Raro saíram do Mercado.",
        "Celestial, Divino e Cósmico seguem restritos, com exceção conhecida para Soulstones.",
        "Material negocia em qualquer raridade — inclusive as moedas comemorativas.",
        f"O Navio de Trocas abre com o Cubo no nível {CUBE_MARKET_UNLOCK_LEVEL}.",
        STEAM_GUARD_NOTICE,
        "O editor usa apenas snapshot público do Community Market como referência: "
        "não acessa login, inventário ou cookies e não promete preço, venda nem aceitação.",
    ]
    if status is not None:
        lines.insert(1, f"Este save: {status.reason}.")
    return " ".join(lines)
