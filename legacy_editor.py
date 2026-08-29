#!/usr/bin/env python3
from __future__ import annotations
 
import html
import copy
import ctypes
import json
import math
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import time
import unicodedata
import urllib.request
import webbrowser
from pathlib import Path
from tkinter import BOTH, END, LEFT, RIGHT, X, Y, BooleanVar, StringVar, Tk, filedialog, messagebox
from tkinter import font as tkfont
from tkinter import ttk
import tkinter as tk

from app_meta import APP_NAME, APP_VERSION
import commemorative_coins as coins
from intelligence_engine import (
    RARITY_RANK as INTELLIGENCE_RARITY_RANK,
    SLOT_NAMES as INTELLIGENCE_SLOT_NAMES,
    slot_prefixes as intelligence_slot_prefixes,
)
from market_policy import (
    BASE_LISTING_SLOTS,
    HIGH_GRADE_GEAR_BLOCKED,
    OFFICIAL_NEWS_URL,
    POLICY_CHECKED_AT,
    SOURCE_TYPES_EXCLUDED,
    market_eligibility,
    policy_summary,
    trade_ship_status,
)
import platform_support
from save_layer import ES3_PASSWORD, SaveFile
 
 
APP_TITLE = f"{APP_NAME} v{APP_VERSION}"
BASE_URL = "https://tbh.city"
APP_DIR = Path(sys.executable).resolve().parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
RESOURCE_DIR = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
USER_DATA_DIR = platform_support.user_data_dir(APP_NAME, APP_DIR, frozen=bool(getattr(sys, "frozen", False)))
CACHE_FILE = USER_DATA_DIR / "tbh_items_cache.json"
ICON_DIR = USER_DATA_DIR / "tbh_item_icons"
HERO_PORTRAIT_DIR = RESOURCE_DIR / "hero_portraits"
# Windows guarda o save em ``AppData/LocalLow``; no Linux e no macOS o jogo roda
# sob Proton/Wine e a mesma árvore vive dentro do prefixo. platform_support
# procura os dois casos em vez de montar um caminho Windows em qualquer sistema.
GAME_SAVE_DIR = platform_support.default_game_save_dir()
DEFAULT_SAVE_FILE = GAME_SAVE_DIR / platform_support.SAVE_FILE_NAME

#: Família de fonte da interface. ``setup_style`` troca por uma realmente
#: instalada no sistema: "Segoe UI" não existe no Linux nem no macOS, e pedir
#: uma família ausente faz o Tk cair numa fonte bitmap antiga.
UI_FONT = "Segoe UI"
 
THEME = {
    "base": "#08111F",
    "top": "#0F1B2D",
    "panel": "#111F33",
    "card": "#172A43",
    "selected": "#1D3C5F",
    "hover": "#213B5C",
    "input": "#0B1728",
    "border": "#2B4566",
    "text": "#F4F7FB",
    "muted": "#A9B8CC",
    "muted2": "#7F93AD",
    "accent": "#53D6C5",
    "accent_hover": "#6FE6D6",
    "accent_dim": "#3FB8A9",
    "accent_text": "#061712",
    "selection": "#2F6FED",
    "danger": "#FF8C82",
    "danger_soft": "#5B2530",
    "success": "#77D6AE",
    "warning": "#F5C66A",
    "disabled": "#475569",
    "recipe_decoration": "#9D64FF",
    "recipe_engraving": "#55C8FF",
    "recipe_inscription": "#69DB5B",
}

HERO_NAMES = {
    101: "Cavaleiro",
    201: "Arqueira",
    301: "Feiticeiro",
    401: "Sacerdotisa",
    501: "Caçador",
    601: "Matador",
}
 
# Nomes e prefixos de espaço vivem em intelligence_engine, que não depende de
# tkinter e é o módulo compartilhado com os testes. Até a 3.3.2 existiam duas
# tabelas: a daqui trazia "ANEL" no espaço 6 e o prefixo 62 tanto no 6 quanto no
# 8, de modo que nenhum amuleto era aceito no espaço do amuleto. A divergência
# só não aparecia no produto porque a camada intermediária sobrescrevia o dict
# do módulo em tempo de importação.
SLOT_NAMES = dict(INTELLIGENCE_SLOT_NAMES)

#: Uma aba do armazém tem 7x7 espaços e o jogo mostra 7 abas. Até a 3.4.0 o
#: editor usava 66, número que não corresponde a nenhuma aba do jogo: com ele a
#: "Armazém 3" do editor caía no meio da aba 4 do jogo, e os destinos das filas
#: mandavam item para a página errada.
#:
#: Os dois números estão confirmados por captura da tela do jogo: a grade é 7x7,
#: as abas vão de 1 a 7, e a ocupação de cada uma bate com o save — aba 1 vazia,
#: aba 2 com 13 itens, abas 5, 6 e 7 cheias com 49. Os blocos contíguos do save
#: também começam exatamente em múltiplos de 49.
STASH_PAGE_SIZE = 49
STASH_PAGE_COUNT = 7

#: Quantos espaços do armazém a interface do jogo exibe — uma **contagem**, não
#: um índice: os espaços visíveis vão de 0 a ``STASH_REACHABLE_SLOTS - 1``, e a
#: comparação certa é ``Index < STASH_REACHABLE_SLOTS``. Com 7 abas de 49 são 343
#: espaços e o último índice é 342.
#:
#: ``stashSaveDatas`` costuma vir maior que isso; escrever além do último espaço
#: visível deixa o item gravado no save e invisível no jogo, sem qualquer aviso.
#:
#: **Não derive este limite de ``len(stashSaveDatas)``.** O save aloca 528
#: espaços, todos com ``IsUnLock`` verdadeiro, e o jogo mostra 343 — a diferença
#: é folga do vetor, não aba escondida. A 3.4.2 tentou medir o número de abas
#: assim e chegou a 11, o que fez o editor oferecer destinos que a tela do jogo
#: não tem. Os itens que ocupam os índices acima de 342 num save real vieram do
#: editor antigo, que escrevia até o 461; é exatamente o que o resgate desfaz.
STASH_REACHABLE_SLOTS = STASH_PAGE_SIZE * STASH_PAGE_COUNT
STASH_TARGETS = [f"Armazem {page}" for page in range(1, STASH_PAGE_COUNT + 1)]
STASH_DISPLAY_TARGETS = [f"Armazém {page}" for page in range(1, STASH_PAGE_COUNT + 1)]
ITEM_DESTINATIONS = ["Automatico", "Inventario", *STASH_TARGETS]

# A política de Mercado vive em market_policy.py. Estes nomes continuam
# exportados porque a interface e os testes históricos os importam daqui.
MARKET_POLICY_CHECKED_AT = POLICY_CHECKED_AT
MARKET_RESTRICTED_RARITIES = set(HIGH_GRADE_GEAR_BLOCKED)
MARKET_SOURCE_TYPES_EXCLUDED = set(SOURCE_TYPES_EXCLUDED)
MARKET_OFFICIAL_NEWS_URL = OFFICIAL_NEWS_URL
PROTECTED_BATCH_LIMIT = 10
KNOWN_ATTRIBUTE_GROUP_KEYS = list(range(10002, 10009))
KNOWN_CUBE_RECIPE_MAX_BY_VERSION = {
    "1.01.05": {
        100001: 100081,
        200001: 200011,
        300001: 300011,
        400001: 400011,
        500001: 500011,
        600001: 600081,
        700001: 700101,
        900001: 900011,
    }
}


def display_scale_factor() -> float:
    """Retorna a escala real do Windows mesmo quando o Tk usa virtualização de DPI."""
    if sys.platform != "win32":
        return 1.0
    try:
        return max(1.0, float(ctypes.windll.shcore.GetScaleFactorForDevice(0)) / 100.0)
    except (AttributeError, OSError, ValueError):
        return 1.0

DESTINATION_LABELS = {
    "Automatico": "Automático",
    "Inventario": "Inventário",
    **{target: target.replace("Armazem", "Armazém") for target in STASH_TARGETS},
}
DESTINATION_VALUES = list(DESTINATION_LABELS.values())
DESTINATION_FROM_LABEL = {label: value for value, label in DESTINATION_LABELS.items()}

#: Fonte única em intelligence_engine; SLOT_NAMES já seguia esse padrão (ver
#: comentário acima) depois de duas tabelas divergentes causarem um bug real.
RARITY_RANK = dict(INTELLIGENCE_RARITY_RANK)

RARITY_LABELS = {
    "COMMON": "Comum",
    "UNCOMMON": "Incomum",
    "RARE": "Raro",
    "LEGENDARY": "Lendário",
    "IMMORTAL": "Imortal",
    "ARCANA": "Arcano",
    "BEYOND": "Além",
    "CELESTIAL": "Celestial",
    "DIVINE": "Divino",
    "COSMIC": "Cósmico",
}
RARITY_FILTER_ALL = "Todas as raridades"
RARITY_FILTER_VALUES = [RARITY_FILTER_ALL, *RARITY_LABELS.values()]
RARITY_FROM_LABEL = {label: rarity for rarity, label in RARITY_LABELS.items()}

ITEM_TYPE_LABELS = {
    "GEAR": "Equipamento",
    "MATERIAL": "Material",
    "CONSUMABLE": "Consumível",
    "CURRENCY": "Moeda",
}
TYPE_FILTER_ALL = "Todos os tipos"
TYPE_FILTER_VALUES = [TYPE_FILTER_ALL, *ITEM_TYPE_LABELS.values()]
TYPE_FROM_LABEL = {label: item_type for item_type, label in ITEM_TYPE_LABELS.items()}

# Os nomes oficiais vêm do catálogo em inglês. Estes sinônimos permitem buscar em PT-BR.
ITEM_NAME_SEARCH_ALIASES = {
    "sword": "espada",
    "axe": "machado",
    "bow": "arco",
    "crossbow": "besta",
    "dagger": "adaga",
    "spear": "lança",
    "staff": "cajado",
    "wand": "varinha",
    "shield": "escudo",
    "helmet": "capacete",
    "hood": "capuz",
    "armor": "armadura",
    "glove": "luva",
    "boot": "bota",
    "ring": "anel",
    "earring": "brinco",
    "bracelet": "abraçadeira bracelete",
    "gem": "gema",
    "crystal": "cristal",
    "ore": "minério",
    "ingot": "lingote",
    "scroll": "pergaminho",
}

HERO_STAT_WEIGHTS = {
    101: {1: 1.25, 3: 1.45, 4: 1.15, 5: 1.5, 11: 1.2, 12: 1.45, 14: 1.35, 15: 1.25},
    201: {1: 1.5, 2: 1.5, 8: 1.35, 10: 1.45, 13: 1.15, 20: 1.35, 24: 1.25, 25: 1.25},
    301: {1: 1.45, 7: 1.5, 8: 1.3, 9: 1.45, 10: 1.25, 19: 1.35, 21: 1.2, 28: 1.4},
    401: {3: 1.25, 7: 1.5, 9: 1.5, 15: 1.2, 22: 1.7, 23: 1.35, 28: 1.45},
    501: {1: 1.5, 2: 1.4, 8: 1.4, 10: 1.45, 20: 1.3, 24: 1.5, 25: 1.45},
    601: {1: 1.5, 2: 1.45, 8: 1.4, 10: 1.4, 16: 1.35, 17: 1.2, 20: 1.3},
}
 
ENCHANT_RECIPE_TYPES = {
    0: (),
    2: (3, 3),
    4: (3, 3, 4, 4),
    6: (1, 1, 2, 2, 3, 3),
}
ENCHANT_GROUPS = ("DECORAÇÃO", "DECORAÇÃO", "GRAVAÇÃO", "GRAVAÇÃO", "INSCRIÇÃO", "INSCRIÇÃO")

RARITY_ENCHANT_SLOT_COUNT = {
    "COMMON": 0,
    "UNCOMMON": 0,
    "RARE": 2,
    "LEGENDARY": 2,
    "IMMORTAL": 4,
    "ARCANA": 6,
    "BEYOND": 6,
    "CELESTIAL": 6,
    "DIVINE": 6,
    "COSMIC": 6,
}
 
RECIPE_COLORS = {
    "DECORAÇÃO": THEME["recipe_decoration"],
    "GRAVAÇÃO": THEME["recipe_engraving"],
    "INSCRIÇÃO": THEME["recipe_inscription"],
    "VAZIO": THEME["muted2"],
}
 
STAT_TYPES = {
    0: "indisponível",
    1: "Dano de ataque",
    2: "Velocidade de ataque",
    3: "Vida máxima",
    4: "Regeneração de vida por segundo",
    5: "Armadura",
    6: "Velocidade de movimento",
    7: "Velocidade de conjuração",
    8: "Dano crítico",
    9: "Redução de recarga",
    10: "Chance de crítico",
    11: "Resistência a todos os elementos",
    12: "Chance de bloqueio",
    13: "Chance de esquiva",
    14: "Redução de dano",
    15: "Absorção de dano",
    16: "Roubo de vida",
    17: "Vida por acerto",
    18: "Vida por abate",
    19: "Área de efeito",
    20: "Ataques múltiplos",
    21: "Alcance de habilidade",
    22: "Cura de habilidade",
    23: "Duração de habilidade",
    24: "Dano de projétil",
    25: "Quantidade de projéteis",
    26: "Redução de ataques básicos",
    27: "Experiência recebida",
    28: "Nível de todas as habilidades",
}
 
STAT_MODS = {
    0: "nenhum",
    **{STAT_TYPE_TO_MOD_KEY: STAT_TYPES[STAT_TYPE_ID] for STAT_TYPE_ID, STAT_TYPE_TO_MOD_KEY in {
        1: 100101, 2: 100201, 3: 100301, 4: 100401, 5: 100501, 6: 100601,
        7: 101801, 8: 100801, 9: 100901, 10: 100701, 11: 101001, 12: 101101,
        13: 101201, 14: 101301, 15: 101401, 16: 101501, 17: 101601, 18: 101701,
        19: 101901, 20: 102001, 21: 102101, 22: 102201, 23: 102301, 24: 102401,
        25: 102501, 26: 102601, 27: 102701, 28: 102801,
    }.items()},
}
 
STAT_NAME_TO_TYPE = {
    "AttackDamage": 1,
    "AttackSpeed": 2,
    "MaxHp": 3,
    "HpRegenPerSec": 4,
    "Armor": 5,
    "MovementSpeed": 6,
    "CastSpeed": 7,
    "CriticalDamage": 8,
    "CooldownReduction": 9,
    "CriticalChance": 10,
    "AllElementalResistance": 11,
    "BlockChance": 12,
    "DodgeChance": 13,
    "DamageReduction": 14,
    "DamageAbsorption": 15,
    "HpLeech": 16,
    "AddHpPerHit": 17,
    "AddHpPerKill": 18,
    "AreaOfEffect": 19,
    "Multistrike": 20,
    "SkillRangeExpansion": 21,
    "SkillHealIncrease": 22,
    "SkillDurationIncrease": 23,
    "IncreaseProjectileDamage": 24,
    "ProjectileCount": 25,
    "BaseAttackCountReduction": 26,
    "IncreaseExpAmount": 27,
    "AddAllSkillLevel": 28,
}
 
TIERS = ["0 | vazio"] + [f"{i} | T{i}" for i in range(1, 31)]
STAT_TYPE_CHOICES = [f"{k} | {v}" for k, v in STAT_TYPES.items()]
STAT_MOD_CHOICES = [f"{k} | {v}" for k, v in STAT_MODS.items()]
EMPTY_ENCHANT = {
    "StatModKey": 0,
    "Tier": 0,
    "Value": 0,
    "RecipeType": 0,
    "ModType": 0,
    "MaterialKey": 0,
    "StatType": 0,
    "EnchantVersion": None,
}

STAT_TYPE_TO_MOD = {
    1: 100101,
    2: 100201,
    3: 100301,
    4: 100401,
    5: 100501,
    6: 100601,
    7: 101801,
    8: 100801,
    9: 100901,
    10: 100701,
    11: 101001,
    12: 101101,
    13: 101201,
    14: 101301,
    15: 101401,
    16: 101501,
    17: 101601,
    18: 101701,
    19: 101901,
    20: 102001,
    21: 102101,
    22: 102201,
    23: 102301,
    24: 102401,
    25: 102501,
    26: 102601,
    27: 102701,
    28: 102801,
}

COLLECTIONS = {
    "Moedas": "currenySaveDatas",
    "Atributos": "attributeSaveDatas",
    "Runas": "RuneSaveData",
    "Pets": "PetSaveData",
    "Receitas do cubo": "cubeRecipeSaveDatas",
    "Estatísticas": "aggregateSaveDatas",
}

FIELD_LABELS = {
    "heroKey": "Código do herói", "HeroLevel": "Nível do herói", "IsUnLock": "Desbloqueado",
    "HeroExp": "Experiência do herói", "AbilityPoint": "Pontos de habilidade",
    "AllocatedHeroAbilityPoint": "Pontos de habilidade usados", "equippedSKillKey": "Habilidade equipada",
    "unlockedAttributeGroupKeys": "Grupos de atributos desbloqueados", "version": "Versão do save",
    "lastSavedTime": "Último salvamento", "playTime": "Tempo de jogo", "isFirstPlay": "Primeira partida",
    "LastRollingBackUpTime": "Último backup rotativo", "LastDailyBackUpTime": "Último backup diário",
    "SendSteamId": "Enviar ID Steam", "TutorialCleared": "Tutorial concluído", "ArrangedPetKey": "Pet selecionado",
    "arrangedHeroKey": "Herói selecionado", "maxCompletedStage": "Maior fase concluída",
    "currentStageKey": "Fase atual", "currentStageWave": "Onda atual", "useStorage": "Usar armazenamento",
    "isOpeningDirectionPlayed": "Introdução exibida", "FirstUnlockHeroKey": "Primeiro herói desbloqueado",
    "language": "Idioma", "isAlwaysOnTop": "Sempre visível", "maxFps": "Limite de FPS",
    "windowZoomRate": "Escala da janela", "windowLayoutPreset": "Modelo de layout", "FixingLog": "Fixar registro",
    "LogFilter": "Filtro do registro", "LogShowTime": "Mostrar horário no registro", "isAutoStart": "Iniciar automaticamente",
    "StageRepeatStageFailed": "Repetir fase após derrota", "RepeatActBossDuringConsumeAllStone": "Repetir chefe até acabar a pedra",
    "AskWarningAlchemy": "Avisar antes da alquimia", "AskWarningTradingStash": "Avisar antes do armazém de trocas",
    "BoxAlphaValue": "Transparência da caixa", "BoxShowWhenHover": "Mostrar caixa ao passar o mouse",
    "ShowQuickMenu": "Mostrar menu rápido", "ForceSynthesisOnCubeOpen": "Forçar síntese ao abrir o cubo",
    "AlwaysShowCoolTimeSlider": "Sempre mostrar controle de recarga", "IsTooltipExpanded": "Dicas expandidas",
    "Level": "Nível", "Exp": "Experiência", "Key": "Código", "Quantity": "Quantidade",
    "RuneKey": "Código da runa", "PetKey": "Código do pet", "IsUnlock": "Desbloqueado", "IsViewed": "Visualizado",
    "CubeRecipeTypeInt": "Tipo de receita", "CubeKey": "Código do cubo",
    "MaxUnlockRecipeKey": "Maior receita desbloqueada", "Type": "Tipo", "SubKey": "Subcódigo", "Value": "Valor",
    "ownerSteamId": "ID Steam do proprietário", "playerId": "ID do jogador",
}
 
 
def read_json(path: str | os.PathLike[str]) -> object:
    with open(path, "r", encoding="utf-8-sig") as f:
        return json.load(f)
 
 
def write_json(path: str | os.PathLike[str], data: object) -> None:
    output = Path(path)
    output.parent.mkdir(parents=True, exist_ok=True)
    with open(output, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def versioned_backup_path(path: Path) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    candidate = path.with_name(f"{path.stem}_backup_{stamp}{path.suffix}")
    suffix = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_backup_{stamp}_{suffix}{path.suffix}")
        suffix += 1
    return candidate


def atomic_write_json(path: Path, data: object) -> None:
    temp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    try:
        write_json(temp, data)
        os.replace(temp, path)
    finally:
        if temp.exists():
            temp.unlink()
 
 
def normalize_choice(value: str) -> str:
    if "|" not in value:
        return value.strip()
    prefix = value.split("|", 1)[0].strip()
    return prefix if re.fullmatch(r"-?\d+", prefix) else value.strip()


def normalize_search_text(value: object) -> str:
    """Normaliza busca para ignorar maiúsculas, acentos e espaços repetidos."""
    text = unicodedata.normalize("NFKD", str(value or ""))
    text = "".join(char for char in text if not unicodedata.combining(char))
    return " ".join(text.casefold().split())


def rarity_label(value: object) -> str:
    raw = str(value or "").upper()
    return RARITY_LABELS.get(raw, str(value or ""))


def item_type_label(value: object) -> str:
    raw = str(value or "").upper()
    return ITEM_TYPE_LABELS.get(raw, str(value or "").title())


def destination_value(label_or_value: str) -> str:
    return DESTINATION_FROM_LABEL.get(label_or_value, label_or_value)


def destination_label(value: str) -> str:
    return DESTINATION_LABELS.get(value, value)


def item_name_search_aliases(name: object) -> str:
    normalized_name = normalize_search_text(name)
    aliases = [pt for en, pt in ITEM_NAME_SEARCH_ALIASES.items() if en in normalized_name]
    return " ".join(aliases)


def item_matches_filters(item: dict, query: str = "", rarity_filter: str = RARITY_FILTER_ALL, type_filter: str = TYPE_FILTER_ALL) -> bool:
    raw_rarity = str(item.get("Rarity", "")).upper()
    raw_type = str(item.get("Type", "")).upper()
    selected_rarity = RARITY_FROM_LABEL.get(rarity_filter, rarity_filter if rarity_filter != RARITY_FILTER_ALL else "")
    selected_type = TYPE_FROM_LABEL.get(type_filter, type_filter if type_filter != TYPE_FILTER_ALL else "")
    if selected_rarity and raw_rarity != str(selected_rarity).upper():
        return False
    if selected_type and raw_type != str(selected_type).upper():
        return False
    terms = normalize_search_text(query).split()
    if not terms:
        return True
    haystack = normalize_search_text(
        " ".join(
            [
                str(item.get("ItemKey", "")),
                str(item.get("Name", "")),
                item_name_search_aliases(item.get("Name", "")),
                raw_rarity,
                rarity_label(raw_rarity),
                raw_type,
                item_type_label(raw_type),
                " ".join(str(stat) for stat in item.get("StatTypes") or []),
                " ".join(
                    STAT_TYPES.get(STAT_NAME_TO_TYPE.get(str(stat)), str(stat))
                    for stat in item.get("StatTypes") or []
                ),
                str(item.get("SearchExtras", "")),
            ]
        )
    )
    return all(term in haystack for term in terms)


def stage_label(value: object) -> str:
    """Converte a chave 4309 no formato amigável 43-09."""
    number = max(0, safe_int(value))
    return f"{number // 100}-{number % 100:02d}" if number >= 100 else str(number)


def taskbar_hero_is_running() -> bool:
    """Detecta o executável do jogo sem depender de módulos externos."""
    if os.name != "nt":
        return False
    try:
        completed = subprocess.run(
            ["tasklist", "/FI", "IMAGENAME eq TaskBarHero.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
        return "taskbarhero.exe" in completed.stdout.casefold()
    except (OSError, subprocess.SubprocessError):
        return False


def safe_int(value: object, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def unique_paths(*paths: Path) -> list[Path]:
    result: list[Path] = []
    for path in paths:
        resolved = path.resolve()
        if resolved not in result:
            result.append(resolved)
    return result


def cache_candidates() -> list[Path]:
    return unique_paths(CACHE_FILE, APP_DIR / "tbh_items_cache.json", RESOURCE_DIR / "tbh_items_cache.json")


def icon_candidates(key: str) -> list[Path]:
    filename = f"{key}.png"
    return unique_paths(ICON_DIR / filename, APP_DIR / "tbh_item_icons" / filename, RESOURCE_DIR / "tbh_item_icons" / filename)


def hero_portrait_candidates(hero_key: int) -> list[Path]:
    filename = f"{hero_key}.png"
    return unique_paths(APP_DIR / "hero_portraits" / filename, HERO_PORTRAIT_DIR / filename)


def find_icon_file(key: str) -> Path | None:
    return next((path for path in icon_candidates(key) if path.is_file()), None)


def validate_dump_structure(data: object) -> dict:
    if not isinstance(data, dict):
        raise ValueError("o arquivo precisa conter um objeto JSON")
    if not isinstance(data.get("account"), dict):
        raise ValueError("arquivo sem a estrutura account esperada")
    if not isinstance(data.get("player"), dict):
        raise ValueError("arquivo sem a estrutura player esperada")
    player = data["player"]
    for field in (
        "itemSaveDatas",
        "heroSaveDatas",
        "inventorySaveDatas",
        "stashSaveDatas",
        "remakeTradingStashSaveDatas",
    ):
        records = player.get(field, [])
        if not isinstance(records, list):
            raise ValueError(f"{field} não é uma lista")
        invalid = next((index for index, record in enumerate(records) if not isinstance(record, dict)), None)
        if invalid is not None:
            raise ValueError(f"{field}[{invalid}] não é um objeto")
    return data
 
 
def fetch_url(url: str, timeout: int = 20) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": f"{APP_NAME}/{APP_VERSION}"})
    with urllib.request.urlopen(req, timeout=timeout) as response:
        return response.read()
 
 
def parse_embedded_items(page_html: str) -> list[dict]:
    pattern = re.compile(
        r'\{\\"id\\":(\d+),\\"name\\":\{\\"en\\":\\"([^\\"]*)\\"\},'
        r'\\"icon\\":\\"([^\\"]*)\\".*?\\"grade\\":\\"([^\\"]*)\\",\\"type\\":\\"([^\\"]*)\\"'
        r'.*?\\"stat_types\\":\[(.*?)\]',
        re.DOTALL,
    )
    items = []
    seen = set()
    for key, name, icon, rarity, item_type, stat_blob in pattern.findall(page_html):
        if key in seen:
            continue
        seen.add(key)
        stat_types = re.findall(r'\\"([^\\"]+)\\"', stat_blob)
        items.append(
            {
                "ItemKey": key,
                "Name": html.unescape(name),
                "Icon": icon.replace("\\/", "/"),
                "Rarity": rarity,
                "Type": item_type,
                "StatTypes": stat_types,
            }
        )
    items.sort(key=lambda x: int(x["ItemKey"]))
    return items
 
 
def download_db(progress: queue.Queue) -> list[dict]:
    progress.put(("status", "Baixando base do tbh.city/items..."))
    page = fetch_url(f"{BASE_URL}/items").decode("utf-8", errors="replace")
    items = parse_embedded_items(page)
    if not items:
        raise ValueError("a página foi recebida, mas nenhum item foi reconhecido")
    atomic_write_json(CACHE_FILE, {"downloadedAt": time.strftime("%Y-%m-%d %H:%M:%S"), "items": items})
    progress.put(("status", f"Base carregada: {len(items)} itens"))
    return items
 
 
class ProEditor:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title(APP_TITLE)
        display_scale = display_scale_factor()
        screen_width = self.root.winfo_screenwidth()
        screen_height = self.root.winfo_screenheight()
        logical_screen_width = max(1, round(screen_width / display_scale))
        logical_screen_height = max(1, round(screen_height / display_scale))
        window_width = min(1500, max(900, logical_screen_width - 32))
        window_height = min(800, max(560, logical_screen_height - 64))
        window_x = max(0, (logical_screen_width - window_width) // 2)
        window_y = max(0, (logical_screen_height - window_height) // 2)
        self.root.geometry(f"{window_width}x{window_height}+{window_x}+{window_y}")
        self.root.minsize(min(900, window_width), min(560, window_height))
 
        self.path: Path | None = None
        self.loaded_file_signature: tuple[int, int] | None = None
        self.save_file: SaveFile | None = None
        self.loaded_kind = "json"
        self.data: dict | None = None
        self.items: list[dict] = []
        self.db: list[dict] = []
        self.db_by_key: dict[str, dict] = {}
        self.item_choice_cache: list[str] = []
        self.material_choice_cache: list[str] = ["0 | nenhum"]
        self.items_by_uid: dict[int, dict] = {}
        self.selected_hero: dict | None = None
        self.selected_item: dict | None = None
        self.enchant_clipboard: dict | None = None
        self.enchant_list_clipboard: list[dict] | None = None
        self.icon_images: dict[str, tk.PhotoImage] = {}
        self.hero_images: dict[int, tk.PhotoImage] = {}
        self.table_refresh_job: str | None = None
        self.jobs: queue.Queue = queue.Queue()
        self.icon_requests: queue.Queue[str] = queue.Queue()
        self.icon_pending: set[str] = set()
        self.icon_refreshers: list[tuple[tk.Misc, object]] = []
        self.icon_refresh_scheduled = False
        self.manual_icon_remaining: set[str] = set()
        self.manual_icon_total = 0
        self.manual_icon_downloaded = 0
        self.dirty = False
        self.last_validation: list[dict] = []
        self.original_item_uids: set[int] = set()
        self.session_created_uids: set[int] = set()
        self.session_modified_uids: set[int] = set()
        self.protected_mode = True
        # Tamanho do conjunto elegível antes do corte por capacidade, para que o
        # resumo saiba distinguir "não há candidato" de "não há espaço".
        self.last_market_pool = 0
        self.last_recycle_pool = 0
 
        self.path_var = StringVar(value="Nenhum save aberto")
        self.status_var = StringVar(value="Passo 1: clique em Abrir save para começar.")
        self.filter_var = StringVar(value="")
        self.rarity_filter_var = StringVar(value=RARITY_FILTER_ALL)
        self.type_filter_var = StringVar(value=TYPE_FILTER_ALL)
        self.stash_page_var = StringVar(value="Todas as páginas")
        self.only_non_empty = BooleanVar(value=True)
        self.protected_mode_var = BooleanVar(value=True)
 
        self.setup_style()
        self.build_ui()
        self.load_cache()
        self.start_icon_worker()
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.bind_all("<Control-o>", lambda _event: self.open_dump())
        self.root.bind_all("<Control-s>", lambda _event: self.save_dump())
        self.root.bind_all("<Control-Shift-E>", lambda _event: self.export_json())
        self.root.after(120, self.poll_jobs)
 
    def resolve_ui_font(self) -> str:
        """Fixa uma família realmente instalada antes de qualquer widget nascer.

        Pedir "Segoe UI" fora do Windows não gera erro: o Tk silenciosamente cai
        numa fonte bitmap antiga, e a interface inteira fica com aparência de
        aplicação dos anos 90 no Linux e no macOS."""
        global UI_FONT
        try:
            families = tkfont.families(self.root)
        except tk.TclError:
            families = ()
        chosen = platform_support.preferred_font_family(families)
        if chosen:
            UI_FONT = chosen
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont"):
            try:
                tkfont.nametofont(name, root=self.root).configure(family=UI_FONT, size=9)
            except (tk.TclError, RuntimeError):
                continue
        return UI_FONT

    def setup_style(self) -> None:
        self.root.configure(bg=THEME["base"])
        self.resolve_ui_font()
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(
            ".",
            background=THEME["base"],
            foreground=THEME["text"],
            fieldbackground=THEME["top"],
            bordercolor=THEME["border"],
            font=(UI_FONT, 9),
        )
        style.configure("Top.TFrame", background=THEME["top"])
        style.configure("Panel.TFrame", background=THEME["panel"], relief="flat", borderwidth=0)
        style.configure("Card.TFrame", background=THEME["card"], relief="flat", borderwidth=0)
        style.configure("Selected.TFrame", background=THEME["selected"], relief="flat", borderwidth=0)
        style.configure("TLabel", background=THEME["panel"], foreground=THEME["text"], font=(UI_FONT, 9))
        style.configure("Top.TLabel", background=THEME["top"], foreground=THEME["muted"], font=(UI_FONT, 9))
        style.configure("Section.TLabel", background=THEME["panel"], foreground=THEME["muted"], font=(UI_FONT, 9, "bold"))
        style.configure("TCheckbutton", background=THEME["panel"], foreground=THEME["text"], font=(UI_FONT, 9))
        style.map(
            "TCheckbutton",
            background=[("active", THEME["panel"])],
            foreground=[("disabled", THEME["muted2"])],
            indicatorcolor=[("selected", THEME["accent"]), ("!selected", THEME["input"])],
        )
        style.configure("Top.TCheckbutton", background=THEME["top"], foreground=THEME["text"], font=(UI_FONT, 9))
        style.map(
            "Top.TCheckbutton",
            background=[("active", THEME["top"])],
            indicatorcolor=[("selected", THEME["accent"]), ("!selected", THEME["input"])],
        )
        style.configure("TButton", background=THEME["card"], foreground=THEME["text"], borderwidth=0, padding=(11, 7), font=(UI_FONT, 9))
        style.map(
            "TButton",
            background=[("pressed", THEME["selection"]), ("active", THEME["hover"]), ("disabled", THEME["input"])],
            foreground=[("disabled", THEME["muted2"])],
        )
        style.configure("Accent.TButton", background=THEME["accent"], foreground=THEME["accent_text"], borderwidth=0, padding=(13, 8), font=(UI_FONT, 9, "bold"))
        style.map(
            "Accent.TButton",
            background=[("pressed", THEME["accent_dim"]), ("active", THEME["accent_hover"]), ("disabled", THEME["input"])],
            foreground=[("disabled", THEME["muted2"])],
        )
        style.configure("Danger.TButton", background=THEME["card"], foreground=THEME["danger"], borderwidth=0, padding=(11, 7), font=(UI_FONT, 9))
        style.map("Danger.TButton", background=[("active", THEME["danger_soft"])], foreground=[("active", THEME["text"]), ("disabled", THEME["muted2"])])
        style.configure("Compact.TButton", background=THEME["card"], foreground=THEME["text"], borderwidth=0, padding=(8, 3), font=(UI_FONT, 8))
        style.map("Compact.TButton", background=[("active", THEME["hover"]), ("disabled", THEME["input"])], foreground=[("disabled", THEME["muted2"])])
        style.configure("TMenubutton", background=THEME["card"], foreground=THEME["text"], borderwidth=0, padding=(11, 7), arrowcolor=THEME["muted"], font=(UI_FONT, 9))
        style.map("TMenubutton", background=[("active", THEME["hover"])])
        style.configure("TEntry", fieldbackground=THEME["input"], foreground=THEME["text"], bordercolor=THEME["border"], insertcolor=THEME["text"], padding=6)
        style.map("TEntry", bordercolor=[("focus", THEME["accent"])], lightcolor=[("focus", THEME["accent"])])
        style.configure("TCombobox", fieldbackground=THEME["input"], background=THEME["card"], foreground=THEME["text"], arrowcolor=THEME["muted"], bordercolor=THEME["border"], padding=5)
        style.map(
            "TCombobox",
            fieldbackground=[("readonly", THEME["input"])],
            foreground=[("readonly", THEME["text"])],
            bordercolor=[("focus", THEME["accent"])],
            arrowcolor=[("active", THEME["accent"])],
        )
        # A lista suspensa do Combobox é um Listbox Tk puro: sem estas opções ela
        # abre branca sobre a interface escura.
        self.root.option_add("*TCombobox*Listbox.background", THEME["card"])
        self.root.option_add("*TCombobox*Listbox.foreground", THEME["text"])
        self.root.option_add("*TCombobox*Listbox.selectBackground", THEME["selection"])
        self.root.option_add("*TCombobox*Listbox.selectForeground", THEME["text"])
        self.root.option_add("*TCombobox*Listbox.font", (UI_FONT, 9))
        self.root.option_add("*Menu.background", THEME["card"])
        self.root.option_add("*Menu.foreground", THEME["text"])
        self.root.option_add("*Menu.activeBackground", THEME["selection"])
        self.root.option_add("*Menu.activeForeground", THEME["text"])
        self.root.option_add("*Menu.font", (UI_FONT, 9))
        style.configure("TSpinbox", fieldbackground=THEME["input"], foreground=THEME["text"], background=THEME["card"], arrowcolor=THEME["muted"], bordercolor=THEME["border"], padding=5)
        style.map("TSpinbox", bordercolor=[("focus", THEME["accent"])], arrowcolor=[("active", THEME["accent"])])
        style.configure("TSeparator", background=THEME["border"])
        style.configure("TNotebook", background=THEME["base"], borderwidth=0, tabmargins=(2, 4, 2, 0))
        style.configure("TNotebook.Tab", background=THEME["top"], foreground=THEME["muted"], padding=(16, 9), borderwidth=0, font=(UI_FONT, 9))
        style.map(
            "TNotebook.Tab",
            background=[("selected", THEME["panel"]), ("active", THEME["hover"])],
            foreground=[("selected", THEME["accent"]), ("active", THEME["text"])],
            font=[("selected", (UI_FONT, 9, "bold"))],
        )
        style.configure(
            "Treeview",
            background=THEME["panel"],
            foreground=THEME["text"],
            fieldbackground=THEME["panel"],
            bordercolor=THEME["border"],
            lightcolor=THEME["panel"],
            darkcolor=THEME["panel"],
            borderwidth=0,
            rowheight=36,
            font=(UI_FONT, 9),
        )
        style.map(
            "Treeview",
            background=[("selected", THEME["selection"])],
            foreground=[("selected", THEME["text"])],
        )
        style.configure(
            "Treeview.Heading",
            background=THEME["top"],
            foreground=THEME["muted"],
            bordercolor=THEME["border"],
            relief="flat",
            padding=(8, 7),
            font=(UI_FONT, 9, "bold"),
        )
        style.map(
            "Treeview.Heading",
            background=[("active", THEME["hover"])],
            foreground=[("active", THEME["text"])],
        )
        for orientation in ("Vertical", "Horizontal"):
            style.configure(
                f"{orientation}.TScrollbar",
                background=THEME["border"],
                troughcolor=THEME["base"],
                bordercolor=THEME["base"],
                arrowcolor=THEME["muted2"],
                borderwidth=0,
                relief="flat",
            )
            style.map(f"{orientation}.TScrollbar", background=[("active", THEME["accent"])])

    def scrollable_area(self, parent: tk.Misc) -> ttk.Frame:
        """Área rolável para abas cujo conteúdo é mais alto que a janela.

        A aba Moedas empilha duas seções e, num monitor de 1366x768, o botão
        "Adicionar ao armazém" ficava fora da janela: o assistente encolhe para
        caber na tela, mas o conteúdo da aba não encolhe junto."""
        canvas = tk.Canvas(parent, bg=THEME["panel"], highlightthickness=0, bd=0)
        bar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, style="Panel.TFrame")
        window = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=bar.set)
        bar.pack(side=RIGHT, fill=Y)
        canvas.pack(side=LEFT, fill=BOTH, expand=True)

        def resize(_event=None) -> None:
            canvas.configure(scrollregion=canvas.bbox("all"))
            canvas.itemconfigure(window, width=canvas.winfo_width())

        def on_wheel(event) -> None:
            step = -1 if getattr(event, "delta", 0) > 0 or event.num == 4 else 1
            canvas.yview_scroll(step, "units")

        inner.bind("<Configure>", resize)
        canvas.bind("<Configure>", resize)
        for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            canvas.bind(sequence, on_wheel)
            inner.bind(sequence, on_wheel)
        return inner

    def attach_scrollbars(self, parent: tk.Misc, tree: ttk.Treeview, horizontal: bool = False) -> ttk.Frame:
        """Empacota a tabela com barra de rolagem própria.

        Até a 3.4.0 nenhuma tabela do editor tinha barra: as 462 posições do
        armazém e os milhares de registros da aba "Todos os itens" só podiam ser
        percorridos pela roda do mouse, sem indicação de quanto havia abaixo."""
        holder = ttk.Frame(parent, style="Panel.TFrame")
        holder.rowconfigure(0, weight=1)
        holder.columnconfigure(0, weight=1)
        tree.grid(in_=holder, row=0, column=0, sticky="nsew")
        # A tabela é irmã do container, não filha: como foi criada antes dele,
        # fica embaixo na ordem de empilhamento e o fundo do container a esconde
        # por inteiro — a tabela continua populada, mas invisível.
        tree.lift(holder)
        vertical = ttk.Scrollbar(holder, orient="vertical", command=tree.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        tree.configure(yscrollcommand=vertical.set)
        if horizontal:
            sideways = ttk.Scrollbar(holder, orient="horizontal", command=tree.xview)
            sideways.grid(row=1, column=0, sticky="ew")
            tree.configure(xscrollcommand=sideways.set)
        return holder

    def configure_dialog(self, win: tk.Toplevel, width: int, height: int, resizable: bool = False) -> None:
        """Mantém janelas auxiliares centralizadas e visíveis em qualquer escala do Windows.

        O tamanho pedido é um teto, não uma imposição: em telas menores a janela
        encolhe para caber em vez de empurrar a barra de ações para fora."""
        win.transient(self.root)
        win.state("normal")
        win.resizable(resizable, resizable)
        self.root.update_idletasks()
        display_scale = display_scale_factor()
        screen_width = max(320, round(self.root.winfo_screenwidth() / display_scale))
        screen_height = max(320, round(self.root.winfo_screenheight() / display_scale))
        width = min(width, screen_width - 16)
        height = min(height, screen_height - 48)
        x = max(8, (screen_width - width) // 2)
        y = max(8, (screen_height - height) // 2)
        win.geometry(f"{width}x{height}+{x}+{y}")
        win.lift()
 
    def build_ui(self) -> None:
        top = ttk.Frame(self.root, style="Top.TFrame", padding=(12, 8))
        top.pack(fill=X)
        primary = ttk.Frame(top, style="Top.TFrame")
        primary.pack(fill=X)
        brand = tk.Frame(primary, bg=THEME["top"])
        brand.grid(row=0, column=0, sticky="w")
        tk.Label(brand, text="Holly", fg=THEME["text"], bg=THEME["top"], font=(UI_FONT, 12, "bold")).pack(side=LEFT)
        tk.Label(brand, text="EditTBH", fg=THEME["accent"], bg=THEME["top"], font=(UI_FONT, 12, "bold")).pack(side=LEFT)
        tk.Label(brand, text=f"  v{APP_VERSION}", fg=THEME["muted2"], bg=THEME["top"], font=(UI_FONT, 8)).pack(side=LEFT)
        ttk.Entry(primary, textvariable=self.path_var, state="readonly").grid(row=0, column=1, sticky="ew", padx=12)
        ttk.Button(primary, text="Abrir save...", command=self.open_dump).grid(row=0, column=2, padx=4)
        ttk.Button(primary, text="Salvar alterações", style="Accent.TButton", command=self.save_dump).grid(row=0, column=3, padx=(4, 0))
        primary.columnconfigure(1, weight=1)
        tools = ttk.Frame(top, style="Top.TFrame")
        tools.pack(fill=X, pady=(5, 0))
        ttk.Button(tools, text="Criar item", command=self.open_create_item_dialog).pack(side=LEFT)
        ttk.Button(tools, text="Inteligência", style="Accent.TButton", command=self.open_smart_center).pack(side=LEFT, padx=4)
        ttk.Button(tools, text="Validar save", command=self.open_validation_dialog).pack(side=LEFT, padx=4)
        more_button = ttk.Menubutton(tools, text="Mais opções")
        more_menu = tk.Menu(more_button, tearoff=False)
        more_menu.add_command(label="Organizar itens sem local", command=self.auto_place_unlocated_items)
        more_menu.add_command(label="Exportar cópia em JSON", command=self.export_json)
        more_menu.add_separator()
        more_menu.add_command(label="Atualizar catálogo de itens", command=self.start_db_download)
        more_menu.add_command(label="Baixar ícones do save", command=self.start_icon_download)
        more_menu.add_separator()
        more_menu.add_command(label="Abrir pasta do save", command=self.open_game_save_folder)
        more_menu.add_command(label=f"Sobre o {APP_NAME}", command=self.show_about)
        more_button.configure(menu=more_menu)
        more_button.pack(side=LEFT, padx=4)
        protected_check = ttk.Checkbutton(
            tools,
            text="Modo protegido",
            style="Top.TCheckbutton",
            variable=self.protected_mode_var,
            command=self.on_protected_mode_changed,
        )
        protected_check.pack(side=RIGHT, padx=6)
        ttk.Label(tools, style="Top.TLabel", text="Abra o save  ›  escolha um herói  ›  selecione um item").pack(side=RIGHT, padx=6)

        main = ttk.Frame(self.root, padding=8)
        main.pack(fill=BOTH, expand=True)

        self.hero_panel = ttk.Frame(main, style="Panel.TFrame", padding=10)
        self.hero_panel.pack(side=LEFT, fill=Y, padx=(0, 8))
        tk.Label(self.hero_panel, text="HERÓIS", fg=THEME["muted"], bg=THEME["panel"], font=(UI_FONT, 9, "bold")).pack(anchor="w")
        tk.Label(
            self.hero_panel,
            text="Clique para escolher quem você está editando",
            fg=THEME["muted2"],
            bg=THEME["panel"],
            font=(UI_FONT, 8),
        ).pack(anchor="w", pady=(1, 0))
        self.hero_list = ttk.Frame(self.hero_panel, style="Panel.TFrame")
        self.hero_list.pack(fill=Y, expand=True, pady=(8, 6))
        ttk.Button(
            self.hero_panel,
            text="Otimizar todos os heróis",
            style="Compact.TButton",
            command=self.open_auto_equip_all_preview,
        ).pack(fill=X)

        self.equip_panel = ttk.Frame(main, style="Panel.TFrame", padding=10)
        self.equip_panel.pack(side=LEFT, fill=Y, padx=(0, 8))
        equip_header = tk.Frame(self.equip_panel, bg=THEME["panel"])
        equip_header.pack(fill=X)
        tk.Label(equip_header, text="ITENS EQUIPADOS", fg=THEME["muted"], bg=THEME["panel"], font=(UI_FONT, 9, "bold")).pack(side=LEFT)
        ttk.Button(equip_header, text="Equipar melhor", style="Compact.TButton", command=self.open_auto_equip_preview).pack(side=RIGHT)
        # Sem este rótulo os dez cartões de equipamento não dizem de quem são: a
        # única pista do herói ativo ficava no painel ao lado.
        self.equip_owner = tk.Label(
            self.equip_panel,
            text="Nenhum herói selecionado",
            fg=THEME["accent"],
            bg=THEME["panel"],
            font=(UI_FONT, 9, "bold"),
            anchor="w",
        )
        self.equip_owner.pack(fill=X, pady=(3, 0))
        self.equip_grid = ttk.Frame(self.equip_panel, style="Panel.TFrame")
        self.equip_grid.pack(fill=Y, expand=True, pady=(8, 0))

        right = ttk.Frame(main, style="Panel.TFrame", padding=10)
        right.pack(side=LEFT, fill=BOTH, expand=True)

        detail_header = tk.Frame(right, bg=THEME["panel"], height=52)
        detail_header.pack(fill=X)
        detail_header.pack_propagate(False)
        self.detail_icon = tk.Label(detail_header, bg=THEME["panel"], width=34)
        self.detail_icon.pack(side=LEFT, padx=(0, 9))
        detail_text = tk.Frame(detail_header, bg=THEME["panel"])
        detail_text.pack(side=LEFT, fill=BOTH, expand=True)
        self.detail_title = tk.Label(detail_text, text="SELECIONE UM ITEM", fg=THEME["muted"], bg=THEME["panel"], font=(UI_FONT, 10, "bold"), anchor="w")
        self.detail_title.pack(fill=X, anchor="w")
        # Onde o item está: sem isso o cabeçalho dizia o que estava sendo
        # editado, mas nunca de onde ele veio.
        self.detail_origin = tk.Label(
            detail_text,
            text="Nenhum item selecionado",
            fg=THEME["muted2"],
            bg=THEME["panel"],
            font=(UI_FONT, 8),
            anchor="w",
        )
        self.detail_origin.pack(fill=X, anchor="w", pady=(2, 0))

        self.detail_body = ttk.Frame(right, style="Panel.TFrame")
        self.detail_body.pack(fill=BOTH, expand=True, pady=(8, 0))
 
        self.notebook = ttk.Notebook(self.detail_body)
        self.notebook.pack(fill=BOTH, expand=True)
        self.enchant_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=8)
        self.inventory_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=8)
        self.stash_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=8)
        self.trading_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=8)
        self.all_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=8)
        self.hero_edit_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=8)
        self.data_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=8)
        self.collections_tab = ttk.Frame(self.notebook, style="Panel.TFrame", padding=8)
        self.notebook.add(self.enchant_tab, text="Encantamentos")
        self.notebook.add(self.inventory_tab, text="Inventário")
        self.notebook.add(self.stash_tab, text="Armazém")
        self.notebook.add(self.trading_tab, text="Trocas")
        self.notebook.add(self.all_tab, text="Todos os itens")
        self.notebook.add(self.hero_edit_tab, text="Dados do herói")
        self.notebook.add(self.data_tab, text="Progresso")
        self.notebook.add(self.collections_tab, text="Coleções")
 
        enchant_bar = ttk.Frame(self.enchant_tab, style="Panel.TFrame")
        enchant_bar.pack(fill=X, pady=(0, 8))
        self.edit_item_button = ttk.Button(enchant_bar, text="Editar item", command=self.edit_selected_item)
        self.edit_item_button.pack(side=LEFT)
        self.duplicate_item_button = ttk.Button(enchant_bar, text="Duplicar item", command=self.duplicate_selected_item)
        self.duplicate_item_button.pack(side=LEFT, padx=(6, 12))
        self.equip_item_button = ttk.Button(enchant_bar, text="Equipar", command=self.equip_selected_item)
        self.equip_item_button.pack(side=LEFT, padx=(0, 6))
        ttk.Button(enchant_bar, text="Mover", command=self.move_selected_item).pack(side=LEFT, padx=(0, 12))
        self.enchant_action_buttons = [
            ttk.Button(enchant_bar, text="Copiar todos", command=self.copy_all_enchants),
            ttk.Button(enchant_bar, text="Colar todos", command=self.paste_all_enchants),
            ttk.Button(enchant_bar, text="Limpar todos", command=self.clear_all_enchants),
        ]
        self.enchant_action_buttons[0].pack(side=LEFT)
        self.enchant_action_buttons[1].pack(side=LEFT, padx=(6, 0))
        self.enchant_action_buttons[2].pack(side=LEFT, padx=(6, 0))
 
        self.enchant_rows = ttk.Frame(self.enchant_tab, style="Panel.TFrame")
        self.enchant_rows.pack(fill=BOTH, expand=True)
 
        self.build_item_table(self.inventory_tab, "inventory")
        self.build_item_table(self.stash_tab, "stash")
        self.build_item_table(self.trading_tab, "trading")
        self.build_item_table(self.all_tab, "all")
        self.build_hero_editor()
        self.build_data_editor()
        self.build_collections_editor()
 
        bottom = ttk.Frame(self.root, style="Top.TFrame", padding=(12, 6))
        bottom.pack(side="bottom", fill=X, before=main)
        ttk.Label(bottom, style="Top.TLabel", textvariable=self.status_var).pack(side=LEFT)
        ttk.Label(bottom, style="Top.TLabel", text=f"{APP_NAME} v{APP_VERSION} · {platform_support.current_platform()}").pack(side=RIGHT)

    def show_about(self) -> None:
        messagebox.showinfo(
            APP_NAME,
            f"{APP_NAME}\nVersão {APP_VERSION}\n\nEditor de saves do Taskbar Hero.\n"
            "Salvamento atômico, backup automático, validação de integridade e Modo Protegido.\n\n"
            "Este programa não torna itens negociáveis na Steam e não oferece proteção contra banimento.",
        )

    def on_protected_mode_changed(self) -> None:
        enabled = bool(self.protected_mode_var.get())
        if not enabled:
            if not messagebox.askyesno(
                APP_NAME,
                "Desativar o Modo Protegido remove limites de lote e permite salvar enquanto o jogo estiver aberto.\n\n"
                "Isso não evita restrições do jogo ou da Steam. Deseja continuar?",
            ):
                self.protected_mode_var.set(True)
                enabled = True
        self.protected_mode = enabled
        self.status_var.set("Modo Protegido ativado." if enabled else "Modo Protegido desativado por esta sessão.")

    def protected_mode_enabled(self) -> bool:
        var = getattr(self, "protected_mode_var", None)
        return bool(var.get()) if var is not None else bool(getattr(self, "protected_mode", True))

    def flag_item_modified(self, item: dict | None) -> None:
        if isinstance(item, dict):
            uid = safe_int(item.get("UniqueId"))
            if uid:
                if not hasattr(self, "session_modified_uids"):
                    self.session_modified_uids = set()
                self.session_modified_uids.add(uid)

    def flag_item_created(self, item: dict | None) -> None:
        if isinstance(item, dict):
            uid = safe_int(item.get("UniqueId"))
            if uid:
                if not hasattr(self, "session_created_uids"):
                    self.session_created_uids = set()
                self.session_created_uids.add(uid)

    def file_signature(self, path: Path | None = None) -> tuple[int, int] | None:
        target = path or self.path
        if target is None:
            return None
        try:
            stat = target.stat()
            return (stat.st_mtime_ns, stat.st_size)
        except OSError:
            return None

    def item_is_session_changed(self, item: dict | None) -> bool:
        uid = safe_int(item.get("UniqueId")) if isinstance(item, dict) else 0
        return uid in getattr(self, "session_created_uids", set()) or uid in getattr(self, "session_modified_uids", set())

    def open_game_save_folder(self) -> None:
        if not GAME_SAVE_DIR.is_dir():
            checked = "\n".join(f"• {candidate}" for candidate in platform_support.game_save_dir_candidates())
            messagebox.showerror(
                APP_NAME,
                "A pasta do save do Taskbar Hero não foi encontrada.\n\nLocais verificados:\n"
                f"{checked}\n\nSe o jogo estiver instalado em outro lugar, abra o save "
                "manualmente com Abrir save.",
            )
            return
        if not platform_support.open_in_file_manager(GAME_SAVE_DIR):
            messagebox.showinfo(
                APP_NAME,
                "O gerenciador de arquivos do sistema não pôde ser aberto.\n\nA pasta do save é:\n"
                f"{GAME_SAVE_DIR}",
            )
 
    def build_item_table(self, parent: ttk.Frame, name: str) -> None:
        bar = ttk.Frame(parent, style="Panel.TFrame")
        bar.pack(fill=X, pady=(0, 8))
        filter_bar = ttk.Frame(bar, style="Panel.TFrame")
        filter_bar.pack(fill=X)
        search_row = ttk.Frame(filter_bar, style="Panel.TFrame")
        search_row.pack(fill=X)
        ttk.Label(search_row, text="Buscar").pack(side=LEFT)
        entry = ttk.Entry(search_row, textvariable=self.filter_var)
        entry.pack(side=LEFT, fill=X, expand=True, padx=(6, 0))
        entry.bind("<KeyRelease>", lambda _e: self.schedule_table_refresh())
        options_row = ttk.Frame(filter_bar, style="Panel.TFrame")
        options_row.pack(fill=X, pady=(6, 0))
        if name == "stash":
            ttk.Label(options_row, text="Página").pack(side=LEFT)
            page_filter = ttk.Combobox(
                options_row,
                textvariable=self.stash_page_var,
                values=["Todas as páginas", *STASH_DISPLAY_TARGETS],
                state="readonly",
                width=16,
            )
            page_filter.pack(side=LEFT, padx=(4, 12))
            page_filter.bind("<<ComboboxSelected>>", lambda _e: self.refresh_tables())
        ttk.Label(options_row, text="Raridade").pack(side=LEFT)
        rarity_filter = ttk.Combobox(
            options_row,
            textvariable=self.rarity_filter_var,
            values=RARITY_FILTER_VALUES,
            state="readonly",
            width=16,
        )
        rarity_filter.pack(side=LEFT, padx=(4, 12))
        rarity_filter.bind("<<ComboboxSelected>>", lambda _e: self.refresh_tables())
        ttk.Label(options_row, text="Tipo").pack(side=LEFT)
        type_filter = ttk.Combobox(
            options_row,
            textvariable=self.type_filter_var,
            values=TYPE_FILTER_VALUES,
            state="readonly",
            width=14,
        )
        type_filter.pack(side=LEFT, padx=(4, 12))
        type_filter.bind("<<ComboboxSelected>>", lambda _e: self.refresh_tables())
        ttk.Checkbutton(options_row, text="Ocultar espaços vazios", variable=self.only_non_empty, command=self.refresh_tables).pack(side=LEFT)
        actions = ttk.Frame(bar, style="Panel.TFrame")
        actions.pack(fill=X, pady=(5, 0))
        actions_top = ttk.Frame(actions, style="Panel.TFrame")
        actions_top.pack(fill=X)
        actions_bottom = ttk.Frame(actions, style="Panel.TFrame")
        actions_bottom.pack(fill=X, pady=(4, 0))
        ttk.Button(actions_top, text="Editar item", command=lambda n=name: self.edit_selected_table_item(getattr(self, f"{n}_tree"))).pack(side=LEFT)
        ttk.Button(actions_top, text="Duplicar", command=lambda n=name: self.duplicate_selected_table_item(getattr(self, f"{n}_tree"))).pack(side=LEFT, padx=(4, 0))
        ttk.Button(actions_top, text="Mover", command=lambda n=name: self.move_selected_table_item(getattr(self, f"{n}_tree"))).pack(side=LEFT, padx=(4, 0))
        ttk.Button(actions_bottom, text="Equipar", command=lambda n=name: self.equip_selected_table_item(getattr(self, f"{n}_tree"))).pack(side=LEFT)
        ttk.Button(actions_bottom, text="Ver encantamentos", command=lambda n=name: self.open_selected_table_enchants(getattr(self, f"{n}_tree"))).pack(side=LEFT, padx=(4, 0))
        ttk.Button(actions_bottom, text="Excluir", command=lambda n=name: self.delete_selected_table_item(getattr(self, f"{n}_tree"))).pack(side=LEFT, padx=(4, 0))
        result_var = StringVar(value="0 itens")
        ttk.Label(actions_bottom, textvariable=result_var).pack(side=RIGHT, padx=4)
        setattr(self, f"{name}_result_var", result_var)
 
        columns = ("where", "key", "name", "rarity", "uid")
        tree = ttk.Treeview(parent, columns=columns, show="tree headings", height=18)
        tree.heading("#0", text="")
        tree.column("#0", width=44, minwidth=44, stretch=False, anchor="center")
        tree.tag_configure("odd", background=THEME["base"], foreground=THEME["text"])
        tree.tag_configure("even", background=THEME["card"], foreground=THEME["text"])
        for col, text, width, minimum, stretch in [
            ("where", "Local", 205, 120, False),
            ("key", "Código", 80, 60, False),
            ("name", "Nome", 260, 140, True),
            ("rarity", "Raridade", 95, 70, False),
            ("uid", "ID único", 90, 70, False),
        ]:
            tree.heading(col, text=text)
            tree.column(col, width=width, minwidth=minimum, stretch=stretch, anchor="w")
        self.attach_scrollbars(parent, tree).pack(fill=BOTH, expand=True)
        tree.bind("<<TreeviewSelect>>", lambda _e, t=tree: self.select_from_tree(t))
        setattr(self, f"{name}_tree", tree)

    def build_hero_editor(self) -> None:
        bar = ttk.Frame(self.hero_edit_tab, style="Panel.TFrame")
        bar.pack(fill=X, pady=(0, 8))
        ttk.Button(bar, text="Editar campo", command=self.edit_selected_hero_field).pack(side=LEFT)
        ttk.Button(bar, text="Desbloquear", command=self.unlock_selected_hero).pack(side=LEFT, padx=6)
        ttk.Button(bar, text="Desequipar tudo", command=self.unequip_all_selected_hero).pack(side=LEFT)
        self.hero_edit_tree = ttk.Treeview(self.hero_edit_tab, columns=("field", "value"), show="headings", height=18)
        self.hero_edit_tree.heading("field", text="Campo")
        self.hero_edit_tree.heading("value", text="Valor")
        self.hero_edit_tree.column("field", width=200, anchor="w")
        self.hero_edit_tree.column("value", width=450, anchor="w")
        self.attach_scrollbars(self.hero_edit_tab, self.hero_edit_tree).pack(fill=BOTH, expand=True)
        self.hero_edit_tree.bind("<Double-Button-1>", lambda _e: self.edit_selected_hero_field())

    def build_data_editor(self) -> None:
        bar = ttk.Frame(self.data_tab, style="Panel.TFrame")
        bar.pack(fill=X, pady=(0, 8))
        ttk.Button(bar, text="Editar campo", command=self.edit_selected_data_field).pack(side=LEFT)
        ttk.Label(bar, text="Campos de identidade da conta são protegidos.").pack(side=LEFT, padx=12)
        self.data_tree = ttk.Treeview(self.data_tab, columns=("section", "field", "value"), show="headings", height=18)
        for col, label, width in [("section", "Seção", 150), ("field", "Campo", 210), ("value", "Valor", 300)]:
            self.data_tree.heading(col, text=label)
            self.data_tree.column(col, width=width, anchor="w")
        self.attach_scrollbars(self.data_tab, self.data_tree).pack(fill=BOTH, expand=True)
        self.data_tree.bind("<Double-Button-1>", lambda _e: self.edit_selected_data_field())

    def build_collections_editor(self) -> None:
        bar = ttk.Frame(self.collections_tab, style="Panel.TFrame")
        bar.pack(fill=X, pady=(0, 8))
        self.collection_var = StringVar(value="Moedas")
        combo = ttk.Combobox(bar, textvariable=self.collection_var, values=list(COLLECTIONS), state="readonly", width=22)
        combo.pack(side=LEFT)
        combo.bind("<<ComboboxSelected>>", lambda _e: self.refresh_collections())
        ttk.Button(bar, text="Editar campo", command=self.edit_selected_collection_field).pack(side=LEFT, padx=6)
        ttk.Button(bar, text="Definir em todos", command=self.bulk_edit_collection).pack(side=LEFT)
        ttk.Button(bar, text="Desbloquear pets", command=self.unlock_all_pets).pack(side=LEFT, padx=6)
        self.collection_tree = ttk.Treeview(self.collections_tab, columns=("record", "field", "value"), show="headings", height=18)
        for col, label, width in [("record", "Registro", 150), ("field", "Campo", 210), ("value", "Valor", 300)]:
            self.collection_tree.heading(col, text=label)
            self.collection_tree.column(col, width=width, anchor="w")
        self.attach_scrollbars(self.collections_tab, self.collection_tree).pack(fill=BOTH, expand=True)
        self.collection_tree.bind("<Double-Button-1>", lambda _e: self.edit_selected_collection_field())

    def mark_dirty(self, message: str = "Alteração pendente") -> None:
        self.dirty = True
        self.root.title(f"{APP_TITLE} *")
        self.status_var.set(message)

    def mark_clean(self) -> None:
        self.dirty = False
        self.root.title(APP_TITLE)

    def confirm_discard_or_save(self) -> bool:
        if not self.dirty:
            return True
        answer = messagebox.askyesnocancel(APP_NAME, "Existem alterações não salvas. Deseja salvar agora?")
        if answer is None:
            return False
        if answer:
            self.save_dump()
            return not self.dirty
        return True

    def on_close(self) -> None:
        if self.confirm_discard_or_save():
            self.root.destroy()

    def display_value(self, value: object) -> str:
        if isinstance(value, bool):
            return "Sim" if value else "Não"
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        return str(value)

    def parse_edited_value(self, text: str, original: object) -> object:
        if isinstance(original, bool):
            value = text.strip().lower()
            if value not in {"sim", "não", "nao", "true", "false"}:
                raise ValueError("use Sim ou Não")
            return value in {"sim", "true"}
        if isinstance(original, int) and not isinstance(original, bool):
            return int(text.strip())
        if isinstance(original, float):
            return float(text.strip().replace(",", "."))
        if isinstance(original, (list, dict)):
            parsed = json.loads(text)
            if not isinstance(parsed, type(original)):
                raise ValueError(f"o valor deve continuar sendo {type(original).__name__}")
            return parsed
        return text

    def open_value_editor(self, title: str, field: str, original: object, callback) -> None:
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=THEME["base"])
        self.configure_dialog(win, 650, 300) if isinstance(original, (list, dict)) else self.configure_dialog(win, 520, 190)
        tk.Label(win, text=field, fg=THEME["muted"], bg=THEME["base"]).pack(anchor="w", padx=14, pady=(14, 6))
        if isinstance(original, bool):
            var = StringVar(value="Sim" if original else "Não")
            widget = ttk.Combobox(win, textvariable=var, values=["Não", "Sim"], state="readonly")
            getter = var.get
        elif isinstance(original, (list, dict)):
            widget = tk.Text(win, bg=THEME["input"], fg=THEME["text"], insertbackground=THEME["text"], wrap="word", height=8)
            widget.insert("1.0", json.dumps(original, ensure_ascii=False, indent=2))
            getter = lambda: widget.get("1.0", "end-1c")
        else:
            var = StringVar(value=str(original))
            widget = ttk.Entry(win, textvariable=var)
            getter = var.get
        widget.pack(fill=BOTH if isinstance(original, (list, dict)) else X, expand=isinstance(original, (list, dict)), padx=14, pady=6)

        def apply() -> None:
            try:
                callback(self.parse_edited_value(getter(), original))
                win.destroy()
            except Exception as exc:
                messagebox.showerror(APP_NAME, f"Valor inválido:\n{exc}")

        ttk.Button(win, text="Cancelar", command=win.destroy).pack(side=LEFT, padx=14, pady=12)
        ttk.Button(win, text="Aplicar", style="Accent.TButton", command=apply).pack(side=RIGHT, padx=14, pady=12)
        win.bind("<Escape>", lambda _event: win.destroy())
        win.grab_set()
        widget.focus_set()

    def render_hero_editor(self) -> None:
        if not hasattr(self, "hero_edit_tree"):
            return
        self.hero_edit_tree.delete(*self.hero_edit_tree.get_children())
        if not self.selected_hero:
            return
        self.hero_field_keys: dict[str, str] = {}
        for key, value in self.selected_hero.items():
            if key == "equippedItemIds":
                continue
            iid = self.hero_edit_tree.insert("", END, values=(FIELD_LABELS.get(key, key), self.display_value(value)))
            self.hero_field_keys[iid] = key

    def edit_selected_hero_field(self) -> None:
        selected = self.hero_edit_tree.selection()
        if not selected or not self.selected_hero:
            messagebox.showinfo(APP_NAME, "Selecione um campo do herói.")
            return
        key = self.hero_field_keys.get(selected[0], str(self.hero_edit_tree.item(selected[0], "values")[0]))
        if key == "heroKey":
            messagebox.showinfo(APP_NAME, "O código identifica o herói e não deve ser alterado.")
            return
        original = self.selected_hero.get(key)

        def apply(value: object) -> None:
            self.selected_hero[key] = value
            self.mark_dirty(f"Campo {key} do herói alterado.")
            self.refresh_all()

        self.open_value_editor("Editar herói", FIELD_LABELS.get(key, key), original, apply)

    def unlock_selected_hero(self) -> None:
        if not self.selected_hero:
            return
        self.selected_hero["IsUnLock"] = True
        self.mark_dirty("Herói desbloqueado.")
        self.refresh_all()

    def unequip_all_selected_hero(self) -> None:
        if not self.selected_hero:
            return
        if not messagebox.askyesno(APP_NAME, "Desequipar todos os itens deste herói e mover para o Inventário?"):
            return
        ids = list(self.selected_hero.get("equippedItemIds", []))
        needed = sum(1 for uid in ids if safe_int(uid))
        if self.free_slot_count("Inventario") < needed:
            messagebox.showerror(APP_NAME, "Não há espaço suficiente no Inventário.")
            return
        self.selected_hero["equippedItemIds"] = [0] * 10
        for uid in ids:
            if safe_int(uid) in self.items_by_uid:
                self.place_item(safe_int(uid), "Inventario")
        self.mark_dirty("Todos os itens do herói foram desequipados.")
        self.refresh_all()

    def render_data_editor(self) -> None:
        if not hasattr(self, "data_tree"):
            return
        self.data_tree.delete(*self.data_tree.get_children())
        if not self.data:
            return
        sections = [
            ("Conta", self.data.get("account", {})),
            ("Progresso", self.data["player"].get("commonSaveData", {})),
            ("Configurações", self.data["player"].get("settingSaveData", {})),
            ("Cubo", self.data["player"].get("cubeSaveLevelData", {})),
        ]
        protected = {"ownerSteamId", "playerId"}
        self.data_field_refs: dict[str, tuple[str, str]] = {}
        for section, values in sections:
            for key, value in values.items():
                label = FIELD_LABELS.get(key, key)
                if key in protected:
                    label += " (protegido)"
                iid = self.data_tree.insert("", END, values=(section, label, self.display_value(value)))
                self.data_field_refs[iid] = (section, key)

    def edit_selected_data_field(self) -> None:
        selected = self.data_tree.selection()
        if not selected or not self.data:
            messagebox.showinfo(APP_NAME, "Selecione um campo.")
            return
        section, key = self.data_field_refs.get(selected[0], ("", ""))
        if key in {"ownerSteamId", "playerId"}:
            messagebox.showinfo(APP_NAME, "Esse campo identifica a conta e foi protegido.")
            return
        mapping = {
            "Conta": self.data.get("account", {}),
            "Progresso": self.data["player"].get("commonSaveData", {}),
            "Configurações": self.data["player"].get("settingSaveData", {}),
            "Cubo": self.data["player"].get("cubeSaveLevelData", {}),
        }[section]
        original = mapping.get(key)

        def apply(value: object) -> None:
            mapping[key] = value
            self.mark_dirty(f"{section}: {key} alterado.")
            self.render_data_editor()

        self.open_value_editor(f"Editar {section}", FIELD_LABELS.get(key, key), original, apply)

    def refresh_collections(self) -> None:
        if not hasattr(self, "collection_tree"):
            return
        self.collection_tree.delete(*self.collection_tree.get_children())
        if not self.data:
            return
        source = COLLECTIONS.get(self.collection_var.get(), "currenySaveDatas")
        records = self.data["player"].get(source, [])
        self.collection_field_refs: dict[str, tuple[int, str]] = {}
        for index, record in enumerate(records):
            if not isinstance(record, dict):
                self.collection_tree.insert("", END, values=(index, "valor", self.display_value(record)))
                continue
            identity = next((record.get(k) for k in ("Key", "RuneKey", "PetKey", "CubeKey", "Type") if k in record), index)
            for key, value in record.items():
                iid = self.collection_tree.insert("", END, values=(f"{index}: {identity}", FIELD_LABELS.get(key, key), self.display_value(value)))
                self.collection_tree.set(iid, "record", f"{index}: {identity}")
                self.collection_field_refs[iid] = (index, key)

    def edit_selected_collection_field(self) -> None:
        selected = self.collection_tree.selection()
        if not selected or not self.data:
            messagebox.showinfo(APP_NAME, "Selecione um campo da coleção.")
            return
        index, key = self.collection_field_refs.get(selected[0], (-1, ""))
        source = COLLECTIONS.get(self.collection_var.get(), "currenySaveDatas")
        records = self.data["player"].get(source, [])
        if index < 0 or index >= len(records) or not isinstance(records[index], dict):
            return
        original = records[index].get(key)

        def apply(value: object) -> None:
            records[index][key] = value
            self.mark_dirty(f"{self.collection_var.get()}: {key} alterado.")
            self.refresh_collections()

        self.open_value_editor(f"Editar {self.collection_var.get()}", FIELD_LABELS.get(str(key), str(key)), original, apply)

    def bulk_edit_collection(self) -> None:
        if not self.data:
            return
        source = COLLECTIONS.get(self.collection_var.get(), "currenySaveDatas")
        field_by_source = {
            "currenySaveDatas": "Quantity",
            "attributeSaveDatas": "Level",
            "RuneSaveData": "Level",
            "cubeRecipeSaveDatas": "MaxUnlockRecipeKey",
            "aggregateSaveDatas": "Value",
        }
        field = field_by_source.get(source)
        if not field:
            messagebox.showinfo(APP_NAME, "Use Desbloquear pets para essa coleção.")
            return
        collection = self.collection_var.get()
        records = self.data["player"].get(source, [])
        # Só conta o que a operação realmente alcança: registros sem o campo
        # ficam de fora, e prometer "atualizado em N" contando todos escondia
        # do usuário quantos registros seriam de fato tocados.
        targets = [record for record in records if isinstance(record, dict) and field in record]
        label = FIELD_LABELS.get(field, field)
        if not targets:
            messagebox.showinfo(
                APP_NAME,
                f"Nenhum registro de {collection} possui o campo {label}. Nada foi alterado.",
            )
            return
        value = self.ask_quantity("Definir em todos", f"Novo valor de {label}:", 100)
        if value <= 0:
            return
        if not messagebox.askyesno(
            APP_NAME,
            f"Definir {label} = {value} em {len(targets)} registro(s) de {collection}?\n\n"
            "Esta é uma alteração em massa e substitui o valor atual de todos eles de uma vez. "
            "Nada é gravado até você usar Salvar alterações.",
        ):
            return
        for record in targets:
            record[field] = value
        self.mark_dirty(f"{collection}: {label} definido como {value} em {len(targets)} registro(s).")
        self.refresh_collections()
        messagebox.showinfo(
            APP_NAME,
            f"{len(targets)} registro(s) de {collection} atualizados.\nUse Salvar alterações para gravar.",
        )

    def unlock_all_pets(self) -> None:
        if not self.data:
            messagebox.showinfo(APP_NAME, "Abra um save primeiro.")
            return
        pets = [pet for pet in self.data["player"].get("PetSaveData", []) if isinstance(pet, dict)]
        pending = [pet for pet in pets if not (pet.get("IsUnlock") and pet.get("IsViewed"))]
        if not pets:
            messagebox.showinfo(APP_NAME, "Este save não possui registros de pets.")
            return
        if not pending:
            self.collection_var.set("Pets")
            self.refresh_collections()
            messagebox.showinfo(APP_NAME, "Todos os pets deste save já estão desbloqueados.")
            return
        if not messagebox.askyesno(
            APP_NAME,
            f"Desbloquear {len(pending)} pet(s) ainda bloqueado(s) neste save?\n\n"
            "Esta é uma alteração em massa. Nada é gravado até você usar Salvar alterações.",
        ):
            return
        for pet in pending:
            pet["IsUnlock"] = True
            pet["IsViewed"] = True
        self.collection_var.set("Pets")
        self.mark_dirty(f"{len(pending)} pet(s) desbloqueado(s).")
        self.refresh_collections()
        messagebox.showinfo(
            APP_NAME,
            f"{len(pending)} pet(s) desbloqueado(s).\nUse Salvar alterações para gravar.",
        )
 
    def load_cache(self) -> None:
        failures: list[str] = []
        for candidate in cache_candidates():
            if not candidate.is_file():
                continue
            try:
                data = read_json(candidate)
                rows = list(data.get("items", [])) if isinstance(data, dict) else list(data)
                self.set_item_db(rows)
                if not self.db:
                    raise ValueError("cache sem itens validos")
                self.status_var.set(f"Catálogo local: {len(self.db)} itens")
                return
            except Exception as exc:
                failures.append(f"{candidate.name}: {exc}")
        if failures:
            self.status_var.set(f"Falha no cache: {failures[0]}")

    def set_item_db(self, rows: list[dict]) -> None:
        self.db = [item for item in rows if isinstance(item, dict) and safe_int(item.get("ItemKey")) > 0]
        self.db_by_key = {str(item.get("ItemKey")): item for item in self.db}
        self.item_choice_cache = [
            f"{item.get('ItemKey')} | {rarity_label(item.get('Rarity', ''))} | {item.get('Name', '')}"
            for item in self.db
        ]
        self.material_choice_cache = ["0 | nenhum"] + [
            f"{item.get('ItemKey')} | {item.get('Name')}"
            for item in self.db
            if str(item.get("Type")) == "MATERIAL"
        ]
 
    def open_dump(self) -> None:
        if not self.confirm_discard_or_save():
            return
        initial_dir = GAME_SAVE_DIR if GAME_SAVE_DIR.is_dir() else (self.path.parent if self.path else APP_DIR)
        dialog_options = {
            "initialdir": str(initial_dir),
            "filetypes": [
                ("Save do Taskbar Hero", "*.es3"),
                ("Dump JSON", "*.json"),
                ("Todos os arquivos", "*.*"),
            ],
            "title": "Abrir save do Taskbar Hero",
        }
        if DEFAULT_SAVE_FILE.is_file():
            dialog_options["initialfile"] = DEFAULT_SAVE_FILE.name
        path = filedialog.askopenfilename(**dialog_options)
        if not path:
            return
        self.load_dump(path)
 
    def load_dump(self, path: str | os.PathLike[str]) -> None:
        try:
            new_path = Path(path)
            new_save_file = None
            if new_path.suffix.lower() == ".es3":
                new_save_file = SaveFile.load(new_path, password=ES3_PASSWORD)
                loaded_kind = "es3"
                data = {"account": new_save_file.account, "player": new_save_file.player}
            else:
                loaded_kind = "json"
                data = read_json(path)
            data = validate_dump_structure(data)
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Não foi possível carregar o arquivo:\n{exc}")
            return
        self.path = new_path
        self.loaded_file_signature = self.file_signature(new_path)
        self.save_file = new_save_file
        self.loaded_kind = loaded_kind
        self.data = data
        player = data["player"]
        self.items = list(player.get("itemSaveDatas", []))
        self.rebuild_item_index()
        self.original_item_uids = set(self.items_by_uid)
        self.session_created_uids = set()
        self.session_modified_uids = set()
        self.path_var.set(str(self.path))
        self.status_var.set(f"Save carregado: {len(self.items)} itens")
        heroes = player.get("heroSaveDatas", [])
        self.selected_hero = heroes[0] if heroes else None
        self.selected_item = None
        self.mark_clean()
        self.refresh_all()
        self.notebook.select(self.inventory_tab)
        issues = self.validate_save()
        errors = sum(issue["severity"] == "ERRO" for issue in issues)
        warnings = sum(issue["severity"] == "AVISO" for issue in issues)
        infos = sum(issue["severity"] == "INFO" for issue in issues)
        self.status_var.set(
            f"Save pronto: {len(self.items)} itens | {errors} erro(s) | {warnings} aviso(s) | "
            f"Modo protegido {'ativo' if self.protected_mode_enabled() else 'inativo'} | Agora selecione um item no Inventário."
        )
 
    def start_db_download(self) -> None:
        def worker() -> None:
            try:
                rows = download_db(self.jobs)
                self.jobs.put(("db", rows))
            except Exception as exc:
                self.jobs.put(("error", str(exc)))
 
        threading.Thread(target=worker, daemon=True).start()
 
    def start_icon_download(self) -> None:
        if not self.items:
            messagebox.showinfo(APP_NAME, "Abra um save primeiro.")
            return
        if not self.db_by_key or not any("Icon" in x for x in self.db):
            messagebox.showinfo(APP_NAME, "Atualize o catálogo primeiro para obter os caminhos dos ícones.")
            return
 
        keys = {
            str(item.get("ItemKey"))
            for item in self.items
            if str(self.db_by_key.get(str(item.get("ItemKey")), {}).get("Icon") or "")
        }
        missing = {key for key in keys if find_icon_file(key) is None}
        self.manual_icon_remaining = set(missing)
        self.manual_icon_total = len(missing)
        self.manual_icon_downloaded = 0
        for key in missing:
            self.queue_icon_download(key)
        if not missing:
            messagebox.showinfo(APP_NAME, f"Todos os {len(keys)} ícones usados pelo save já estão prontos.")
        else:
            self.status_var.set(f"Baixando {len(missing)} ícone(s) do save em segundo plano...")

    def start_icon_worker(self) -> None:
        def worker() -> None:
            while True:
                key = self.icon_requests.get()
                try:
                    db = self.db_by_key.get(key, {})
                    icon = str(db.get("Icon") or "")
                    local = ICON_DIR / f"{key}.png"
                    if icon and find_icon_file(key) is None:
                        ICON_DIR.mkdir(parents=True, exist_ok=True)
                        url = icon if icon.startswith("http") else f"{BASE_URL}/{icon.lstrip('/')}"
                        data = fetch_url(url, timeout=12)
                        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
                            raise ValueError("a resposta do ícone não é PNG")
                        temp = local.with_suffix(".png.tmp")
                        try:
                            temp.write_bytes(data)
                            os.replace(temp, local)
                        finally:
                            if temp.exists():
                                temp.unlink()
                        self.jobs.put(("icon_ready", key))
                    else:
                        self.jobs.put(("icon_cached", key))
                except Exception:
                    self.jobs.put(("icon_failed", key))
                finally:
                    self.icon_requests.task_done()

        for _ in range(4):
            threading.Thread(target=worker, daemon=True).start()

    def queue_icon_download(self, key: str) -> bool:
        key = str(key)
        if not key or key in self.icon_pending or find_icon_file(key) is not None:
            return False
        if not str(self.db_by_key.get(key, {}).get("Icon") or ""):
            return False
        self.icon_pending.add(key)
        self.icon_requests.put(key)
        return True

    def register_icon_refresher(self, widget: tk.Misc, callback) -> None:
        self.icon_refreshers.append((widget, callback))

    def schedule_icon_refresh(self) -> None:
        if self.icon_refresh_scheduled:
            return
        self.icon_refresh_scheduled = True
        self.root.after(500, self.refresh_icon_views)

    def refresh_icon_views(self) -> None:
        self.icon_refresh_scheduled = False
        self.refresh_all()
        active: list[tuple[tk.Misc, object]] = []
        for widget, callback in self.icon_refreshers:
            try:
                if widget.winfo_exists():
                    callback()
                    active.append((widget, callback))
            except tk.TclError:
                continue
        self.icon_refreshers = active
 
    def poll_jobs(self) -> None:
        try:
            while True:
                kind, payload = self.jobs.get_nowait()
                if kind == "status":
                    self.status_var.set(str(payload))
                elif kind == "refresh":
                    self.refresh_all()
                elif kind == "db":
                    self.set_item_db(list(payload))
                    self.status_var.set(f"Catálogo de itens carregado: {len(self.db)} itens")
                    self.refresh_all()
                    messagebox.showinfo(APP_NAME, f"Catálogo de itens carregado com sucesso.\nItens no catálogo: {len(self.db)}")
                elif kind in {"icon_ready", "icon_cached", "icon_failed"}:
                    key = str(payload)
                    self.icon_pending.discard(key)
                    if kind in {"icon_ready", "icon_cached"}:
                        self.icon_images.pop(key, None)
                        self.schedule_icon_refresh()
                    if key in self.manual_icon_remaining:
                        self.manual_icon_remaining.discard(key)
                        if kind == "icon_ready":
                            self.manual_icon_downloaded += 1
                        done = self.manual_icon_total - len(self.manual_icon_remaining)
                        self.status_var.set(f"Ícones do save: {done}/{self.manual_icon_total}")
                        if not self.manual_icon_remaining and self.manual_icon_total:
                            failed = self.manual_icon_total - self.manual_icon_downloaded
                            total = self.manual_icon_total
                            downloaded = self.manual_icon_downloaded
                            self.manual_icon_total = 0
                            messagebox.showinfo(APP_NAME, f"Ícones do save prontos.\nNovos: {downloaded}\nFalhas: {failed}\nProcessados: {total}")
                elif kind == "info":
                    self.status_var.set(str(payload).replace("\n", " "))
                    messagebox.showinfo(APP_NAME, str(payload))
                elif kind == "error":
                    messagebox.showerror(
                        APP_NAME,
                        "A tarefa em segundo plano não pôde ser concluída.\n\n"
                        f"{payload}\n\nO save aberto não foi alterado.",
                    )
        except queue.Empty:
            pass
        self.root.after(120, self.poll_jobs)
 
    def refresh_all(self) -> None:
        self.render_heroes()
        self.render_equipped()
        self.render_enchants()
        self.refresh_tables()
        self.render_hero_editor()
        self.render_data_editor()
        self.refresh_collections()

    def rebuild_item_index(self) -> None:
        self.items_by_uid = {}
        for item in self.items:
            uid = safe_int(item.get("UniqueId")) if isinstance(item, dict) else 0
            if uid and uid not in self.items_by_uid:
                self.items_by_uid[uid] = item

    def validate_save(self) -> list[dict]:
        if not self.data:
            return []
        player = self.data["player"]
        issues: list[dict] = []

        def add(severity: str, code: str, message: str) -> None:
            issues.append({"severity": severity, "code": code, "message": message})

        if self.loaded_kind == "es3" and self.save_file is not None and not self.save_file.integrity_valid:
            add(
                "AVISO",
                "source_integrity",
                "A assinatura SystemInfo do arquivo original não confere. Ao salvar, ela será recalculada.",
            )

        item_map: dict[int, dict] = {}
        for index, item in enumerate(player.get("itemSaveDatas", [])):
            if not isinstance(item, dict):
                add("ERRO", "invalid_item", f"Registro de item #{index} não é um objeto.")
                continue
            uid = safe_int(item.get("UniqueId"))
            if uid <= 0:
                add("ERRO", "invalid_uid", f"Item #{index} possui UniqueId inválido.")
            elif uid in item_map:
                add("ERRO", "duplicate_uid", f"UniqueId {uid} aparece em mais de um item.")
            else:
                item_map[uid] = item
            if str(item.get("ItemKey")) not in self.db_by_key:
                add("INFO", "unknown_key", f"Item especial {uid}: ItemKey {item.get('ItemKey')} não está no catálogo local e foi mantido.")
            enchants = item.get("EnchantData")
            if not isinstance(enchants, list):
                add("ERRO", "enchant_shape", f"Item {uid}: EnchantData não é uma lista.")
                continue
            expected_slot_count = self.expected_enchant_slot_count(item)
            if expected_slot_count is not None and len(enchants) != expected_slot_count:
                add(
                    "ERRO",
                    "enchant_shape",
                    f"Item {uid}: EnchantData possui {len(enchants)} slot(s), mas a raridade permite {expected_slot_count}.",
                )
            elif expected_slot_count is None and len(enchants) not in ENCHANT_RECIPE_TYPES:
                add("ERRO", "enchant_shape", f"Item {uid}: EnchantData possui {len(enchants)} espaço(s), formato não reconhecido.")
            recipe_types = ENCHANT_RECIPE_TYPES.get(len(enchants), ())
            counts = [0, 0, 0]
            for enchant_index, enchant in enumerate(enchants):
                if not isinstance(enchant, dict):
                    add("ERRO", "enchant_shape", f"Item {uid}: encantamento #{enchant_index + 1} inválido.")
                    continue
                if set(EMPTY_ENCHANT) - set(enchant):
                    add("ERRO", "enchant_shape", f"Item {uid}: enchant #{enchant_index + 1} tem campos ausentes.")
                if not self.enchant_is_filled(enchant):
                    continue
                if enchant_index >= 6:
                    continue
                counts[enchant_index // 2] += 1
                if enchant_index < len(recipe_types) and safe_int(enchant.get("RecipeType")) != recipe_types[enchant_index]:
                    add("ERRO", "recipe_type", f"Item {uid}: tipo incorreto no enchant #{enchant_index + 1}.")
                expected_mod = STAT_TYPE_TO_MOD.get(safe_int(enchant.get("StatType")), 0)
                if safe_int(enchant.get("StatModKey")) != expected_mod:
                    add("ERRO", "stat_mod", f"Item {uid}: StatType e StatModKey divergem no enchant #{enchant_index + 1}.")
                tier = safe_int(enchant.get("Tier"), -1)
                if tier < 0 or tier > 30:
                    add("ERRO", "tier", f"Item {uid}: tier {tier} fora do intervalo 0-30.")
            if item.get("EnchantCount") != counts:
                add("ERRO", "enchant_count", f"Item {uid}: EnchantCount {item.get('EnchantCount')} deveria ser {counts}.")

        refs: dict[int, list[str]] = {}

        def add_ref(uid: int, label: str) -> None:
            if uid:
                refs.setdefault(uid, []).append(label)

        for hero in player.get("heroSaveDatas", []):
            ids = hero.get("equippedItemIds", [])
            if not isinstance(ids, list) or len(ids) != 10:
                add("ERRO", "hero_slots", f"Hero {hero.get('heroKey')} deve possuir 10 slots de equipamento.")
                ids = ids if isinstance(ids, list) else []
            for index, uid_value in enumerate(ids):
                uid = safe_int(uid_value)
                add_ref(uid, f"Hero {hero.get('heroKey')} slot {index}")
                item = item_map.get(uid)
                if item and index < 10 and not self.item_compatible_with_slot(item, hero, index):
                    add("AVISO", "slot_incompatible", f"Hero {hero.get('heroKey')} slot {index}: item {uid} parece incompativel.")
        for source in ("inventorySaveDatas", "stashSaveDatas", "remakeTradingStashSaveDatas"):
            seen_indices: set[int] = set()
            for slot in player.get(source, []):
                index = safe_int(slot.get("Index"), -1)
                if index in seen_indices:
                    add("ERRO", "duplicate_index", f"{source}: indice {index} duplicado.")
                seen_indices.add(index)
                add_ref(safe_int(slot.get("ItemUniqueId")), f"{source} #{index}")
        for uid, labels in refs.items():
            if uid not in item_map:
                add("ERRO", "missing_ref", f"Referência a item inexistente {uid}: {', '.join(labels)}.")
            if len(labels) > 1:
                add("ERRO", "duplicate_location", f"Item {uid} aparece em varios locais: {', '.join(labels)}.")
        for uid in item_map:
            if uid not in refs:
                add("AVISO", "orphan_item", f"Item {uid} não possui local; aparece somente na aba Todos os itens.")
        for row in self.unreachable_stash_rows():
            add(
                "AVISO",
                "unreachable_slot",
                f"Item {safe_int(row['item'].get('UniqueId'))} está no espaço {safe_int(row['slot'].get('Index'))} "
                f"do armazém, além da última aba que o jogo exibe. Ele existe no save, mas não aparece no jogo. "
                f"Use Reparar para trazê-lo de volta.",
            )
        self.last_validation = issues
        return issues

    def unreachable_stash_rows(self) -> list[dict]:
        """Itens gravados em espaços do armazém que o jogo não consegue exibir.

        ``stashSaveDatas`` costuma trazer mais espaços do que as abas mostradas.
        Enquanto o editor calculou a página com o tamanho errado, ele encheu essa
        faixa: o item continua íntegro no save e some da tela do jogo."""
        if not self.data:
            return []
        rows: list[dict] = []
        for slot in self.data["player"].get("stashSaveDatas", []):
            if safe_int(slot.get("Index")) < STASH_REACHABLE_SLOTS:
                continue
            item = self.items_by_uid.get(safe_int(slot.get("ItemUniqueId")))
            if item is not None:
                rows.append({"slot": slot, "item": item})
        return rows

    def rescue_unreachable_stash_items(self) -> tuple[int, int]:
        """Traz os itens presos para espaços que o jogo exibe.

        Devolve ``(resgatados, sem espaço)``. Nada é criado nem apagado: só o
        índice do espaço muda."""
        pendentes = self.unreachable_stash_rows()
        if not pendentes:
            return 0, 0
        livres = [
            slot for slot in self.data["player"].get("stashSaveDatas", [])
            if safe_int(slot.get("Index")) < STASH_REACHABLE_SLOTS
            and not safe_int(slot.get("ItemUniqueId"))
            and self.slot_is_unlocked("stashSaveDatas", slot)
        ]
        livres.sort(key=lambda slot: safe_int(slot.get("Index")))
        resgatados = 0
        for row in pendentes:
            if not livres:
                break
            destino = livres.pop(0)
            destino["ItemUniqueId"] = safe_int(row["slot"].get("ItemUniqueId"))
            row["slot"]["ItemUniqueId"] = 0
            resgatados += 1
        return resgatados, len(pendentes) - resgatados

    def repair_save(self, show_message: bool = True) -> int:
        if not self.data:
            return 0
        player = self.data["player"]
        changes = 0
        seen_ids: set[int] = set()
        for item in player.get("itemSaveDatas", []):
            if not isinstance(item, dict):
                continue
            item_before = copy.deepcopy(item)
            uid = safe_int(item.get("UniqueId"))
            if uid <= 0 or uid in seen_ids:
                item["UniqueId"] = self.next_unique_id()
                uid = safe_int(item["UniqueId"])
                changes += 1
            seen_ids.add(uid)
            defaults = {
                "PrevUniqueId": 0, "IsChaotic": False, "IsBlocked": False,
                "ItemGetSourceType": 0, "DecorationAppliedTotalCount": 0,
                "EngravingAppliedTotalCount": 0, "InscriptionAppliedTotalCount": 0,
            }
            for key, value in defaults.items():
                if key not in item:
                    item[key] = value
                    changes += 1
            if "IsServerPendingItem" in item:
                item.pop("IsServerPendingItem", None)
                changes += 1
            if self.sync_enchant_metadata(item):
                changes += 1
            if item != item_before:
                self.flag_item_modified(item)
        self.items = list(player.get("itemSaveDatas", []))
        self.rebuild_item_index()
        valid_ids = set(self.items_by_uid)
        seen_locations: set[int] = set()
        for hero in player.get("heroSaveDatas", []):
            ids = hero.get("equippedItemIds")
            if not isinstance(ids, list):
                ids = []
                hero["equippedItemIds"] = ids
                changes += 1
            if len(ids) > 10:
                del ids[10:]
                changes += 1
            while len(ids) < 10:
                ids.append(0)
                changes += 1
            for index, value in enumerate(ids):
                uid = safe_int(value)
                if uid and (uid not in valid_ids or uid in seen_locations):
                    ids[index] = 0
                    changes += 1
                elif uid:
                    seen_locations.add(uid)
        for source in ("inventorySaveDatas", "stashSaveDatas", "remakeTradingStashSaveDatas"):
            slots = player.get(source, [])
            used_indices: set[int] = set()
            next_index = max((safe_int(slot.get("Index"), -1) for slot in slots), default=-1) + 1
            for slot in slots:
                index = safe_int(slot.get("Index"), -1)
                if index in used_indices or index < 0:
                    slot["Index"] = next_index
                    next_index += 1
                    changes += 1
                used_indices.add(safe_int(slot.get("Index")))
                uid = safe_int(slot.get("ItemUniqueId"))
                if uid and (uid not in valid_ids or uid in seen_locations):
                    slot["ItemUniqueId"] = 0
                    changes += 1
                elif uid:
                    seen_locations.add(uid)
        for uid in valid_ids - seen_locations:
            if self.free_slot_count("Automatico") > 0:
                self.place_item(uid, "Automatico")
                changes += 1
        # Itens presos além da última aba exibida pelo jogo: só o índice muda,
        # nada é criado nem apagado.
        resgatados, _sem_espaco = self.rescue_unreachable_stash_items()
        changes += resgatados
        self.items = list(player.get("itemSaveDatas", []))
        self.rebuild_item_index()
        if changes:
            self.mark_dirty(f"Reparação concluída: {changes} ajuste(s).")
            self.refresh_all()
        if show_message:
            remaining = self.validate_save()
            errors = sum(issue["severity"] == "ERRO" for issue in remaining)
            warnings = sum(issue["severity"] == "AVISO" for issue in remaining)
            special = sum(issue["code"] == "unknown_key" for issue in remaining)
            messagebox.showinfo(
                APP_NAME,
                f"Reparação concluída.\nAjustes realizados: {changes}\nErros restantes: {errors}\nAvisos restantes: {warnings}\nItens especiais mantidos: {special}",
            )
        return changes

    def open_validation_dialog(self) -> None:
        if not self.data:
            messagebox.showinfo(APP_NAME, "Abra um save primeiro.")
            return
        win = tk.Toplevel(self.root)
        win.title("Validação do save")
        win.configure(bg=THEME["base"])
        self.configure_dialog(win, 950, 600, resizable=True)
        summary_var = StringVar(value="")
        show_info_var = BooleanVar(value=False)
        summary_bar = ttk.Frame(win, style="Panel.TFrame", padding=8)
        summary_bar.pack(fill=X)
        ttk.Label(summary_bar, textvariable=summary_var).pack(side=LEFT)
        ttk.Checkbutton(summary_bar, text="mostrar informações", variable=show_info_var, command=lambda: refresh()).pack(side=RIGHT)
        tree = ttk.Treeview(win, columns=("severity", "message"), show="headings", height=20)
        tree.heading("severity", text="Nivel")
        tree.heading("message", text="Problema")
        tree.column("severity", width=90, anchor="w")
        tree.column("message", width=820, anchor="w")
        table = self.attach_scrollbars(win, tree)
        table.pack(fill=BOTH, expand=True, padx=10, pady=(0, 10))

        def refresh() -> None:
            # repair() abre um messagebox modal antes de chamar refresh(); se a
            # janela de validação for fechada durante esse modal (Esc está ligado
            # a win.destroy), a Treeview já não existe e tree.delete levantaria
            # TclError. winfo_exists é seguro de chamar em widget destruído.
            if not tree.winfo_exists():
                return
            issues = self.validate_save()
            tree.delete(*tree.get_children())
            for issue in issues:
                if issue["severity"] == "INFO" and not show_info_var.get():
                    continue
                tree.insert("", END, values=(issue["severity"], issue["message"]))
            errors = sum(issue["severity"] == "ERRO" for issue in issues)
            warnings = sum(issue["severity"] == "AVISO" for issue in issues)
            infos = sum(issue["severity"] == "INFO" for issue in issues)
            summary_var.set(f"Erros: {errors}    Avisos: {warnings}    Informações: {infos}" if issues else "Nenhum problema encontrado.")

        def repair() -> None:
            self.repair_save(show_message=True)
            refresh()

        buttons = ttk.Frame(win, style="Panel.TFrame", padding=8)
        buttons.pack(side="bottom", fill=X, before=table)
        ttk.Button(buttons, text="Fechar", command=win.destroy).pack(side=LEFT)
        ttk.Button(buttons, text="Reparar erros", style="Accent.TButton", command=repair).pack(side=RIGHT)
        refresh()
        win.bind("<Escape>", lambda _event: win.destroy())
        win.grab_set()

    def validate_before_save(self) -> bool:
        issues = self.validate_save()
        errors = [issue for issue in issues if issue["severity"] == "ERRO"]
        if not errors:
            return True
        if not messagebox.askyesno(APP_NAME, f"Foram encontrados {len(errors)} erro(s) de integridade.\n\nExecutar a reparação segura antes de salvar?"):
            return False
        self.repair_save(show_message=False)
        remaining = [issue for issue in self.validate_save() if issue["severity"] == "ERRO"]
        if remaining:
            messagebox.showerror(APP_NAME, f"Ainda existem {len(remaining)} erro(s). Use Validar save para revisar.")
            return False
        return True
 
    def item_db(self, item: dict | None) -> dict:
        if not item:
            return {}
        return self.db_by_key.get(str(item.get("ItemKey")), {})
 
    def item_name(self, item: dict | None) -> str:
        if not item:
            return "Vazio"
        db = self.item_db(item)
        return str(db.get("Name") or f"Item {item.get('ItemKey')}")
 
    def item_rarity(self, item: dict | None) -> str:
        if not item:
            return ""
        return str(self.item_db(item).get("Rarity") or "")

    def get_hero_portrait(self, hero_key: int) -> tk.PhotoImage | None:
        if hero_key in self.hero_images:
            return self.hero_images[hero_key]
        for path in hero_portrait_candidates(hero_key):
            if not path.is_file():
                continue
            try:
                image = tk.PhotoImage(file=str(path))
                self.hero_images[hero_key] = image
                return image
            except tk.TclError:
                continue
        return None
 
    def render_heroes(self) -> None:
        for child in self.hero_list.winfo_children():
            child.destroy()
        if not self.data:
            return
        for hero in self.data["player"].get("heroSaveDatas", []):
            selected = hero is self.selected_hero
            background = THEME["selected"] if selected else THEME["card"]
            frame = tk.Frame(
                self.hero_list,
                bg=background,
                bd=0,
                relief="solid",
                width=196,
                height=82,
                highlightthickness=2 if selected else 1,
                highlightbackground=THEME["accent"] if selected else THEME["border"],
            )
            frame.pack(fill=X, pady=4)
            frame.pack_propagate(False)
            hero_key = safe_int(hero.get("heroKey"))
            portrait = self.get_hero_portrait(hero_key)
            if portrait:
                tk.Label(frame, image=portrait, bg=background, bd=0).pack(side=LEFT, padx=(4, 8), pady=4)
            name = HERO_NAMES.get(hero_key, f"Herói {hero_key}")
            text_frame = tk.Frame(frame, bg=background)
            text_frame.pack(side=LEFT, fill=BOTH, expand=True, pady=15)
            tk.Label(text_frame, text=name, fg=THEME["text"], bg=background, font=(UI_FONT, 10, "bold"), anchor="w").pack(fill=X)
            tk.Label(
                text_frame,
                text=f"Nível {hero.get('HeroLevel', 0)}",
                fg=THEME["muted"],
                bg=background,
                font=(UI_FONT, 8),
                anchor="w",
            ).pack(fill=X, pady=(3, 0))
            def bind_hero_click(widget: tk.Misc, selected_hero: dict = hero) -> None:
                widget.bind("<Button-1>", lambda _e, h=selected_hero: self.select_hero(h))
                for nested in widget.winfo_children():
                    bind_hero_click(nested, selected_hero)

            bind_hero_click(frame)
 
    def select_hero(self, hero: dict) -> None:
        self.selected_hero = hero
        self.selected_item = None
        self.refresh_all()
 
    def render_equipped(self) -> None:
        for child in self.equip_grid.winfo_children():
            child.destroy()
        owner = getattr(self, "equip_owner", None)
        if not self.selected_hero:
            if owner is not None:
                owner.configure(text="Nenhum herói selecionado", fg=THEME["muted2"])
            return
        if owner is not None:
            hero_key = safe_int(self.selected_hero.get("heroKey"))
            owner.configure(
                text=f"{HERO_NAMES.get(hero_key, f'Herói {hero_key}')} · nível {self.selected_hero.get('HeroLevel', 0)}",
                fg=THEME["accent"],
            )
        ids = list(self.selected_hero.get("equippedItemIds", []))
        for index in range(10):
            uid = ids[index] if index < len(ids) else 0
            item = self.items_by_uid.get(safe_int(uid), None) if uid else None
            card = self.make_item_card(self.equip_grid, item, SLOT_NAMES.get(index, "SLOT"), index)
            card.grid(row=index // 2, column=index % 2, padx=4, pady=4, sticky="nsew")
 
    def make_item_card(self, parent: ttk.Frame, item: dict | None, slot: str, slot_index: int) -> tk.Frame:
        selected = item is self.selected_item and item is not None
        frame = tk.Frame(parent, bg=THEME["card"], bd=1, relief="solid", width=145, height=94, highlightthickness=1)
        frame.configure(highlightbackground=THEME["accent"] if selected else THEME["border"])
        frame.grid_propagate(False)
        icon = self.get_icon(item)
        if icon:
            tk.Label(frame, image=icon, bg=THEME["card"]).pack(pady=(3, 0))
        else:
            canvas = tk.Canvas(frame, width=30, height=30, bg=THEME["input"], highlightthickness=1, highlightbackground=THEME["border"])
            canvas.create_text(15, 15, text="?", fill=THEME["muted2"], font=(UI_FONT, 13, "bold"))
            canvas.pack(pady=(3, 0))
        tk.Label(frame, text=self.item_name(item), fg=THEME["text"], bg=THEME["card"], font=(UI_FONT, 8), wraplength=110).pack()
        tk.Label(frame, text=slot, fg=THEME["muted"], bg=THEME["card"], font=(UI_FONT, 7)).pack(side="bottom", pady=0)
        swap_button = ttk.Button(frame, text="Trocar" if item else "Equipar", style="Compact.TButton", command=lambda: self.open_equip_dialog(self.selected_hero, slot_index))
        swap_button.pack(side="bottom", pady=(2, 2))
        frame.bind("<Button-1>", lambda _e, it=item: self.select_item(it))
        frame.bind("<Double-Button-1>", lambda _e, it=item: self.open_item_editor(it) if it else None)
        for child in frame.winfo_children():
            if child is swap_button:
                continue
            child.bind("<Button-1>", lambda _e, it=item: self.select_item(it))
            child.bind("<Double-Button-1>", lambda _e, it=item: self.open_item_editor(it) if it else None)
        return frame
 
    def get_icon(self, item: dict | None) -> tk.PhotoImage | None:
        if not item:
            return None
        db = self.item_db(item)
        icon_path = str(db.get("Icon") or "")
        if not icon_path:
            return None
        key = str(item.get("ItemKey"))
        if key in self.icon_images:
            return self.icon_images[key]
        for local in icon_candidates(key):
            if not local.is_file():
                continue
            try:
                img = tk.PhotoImage(file=str(local))
                if img.width() > 34 or img.height() > 34:
                    img = img.subsample(max(1, (img.width() + 29) // 30), max(1, (img.height() + 29) // 30))
                self.icon_images[key] = img
                return img
            except Exception:
                if local.parent == ICON_DIR:
                    try:
                        local.unlink()
                    except OSError:
                        pass
        self.queue_icon_download(key)
        return None
 
    def get_icon_by_key(self, key: str) -> tk.PhotoImage | None:
        return self.get_icon({"ItemKey": key})
 
    def select_item(self, item: dict | None) -> None:
        self.selected_item = item
        self.render_equipped()
        self.render_enchants()
 
    def render_enchants(self) -> None:
        for child in self.enchant_rows.winfo_children():
            child.destroy()
        item = self.selected_item
        origin_label = getattr(self, "detail_origin", None)
        if not item:
            self.detail_title.configure(text="SELECIONE UM ITEM")
            self.detail_icon.configure(image="")
            if origin_label is not None:
                origin_label.configure(text="Nenhum item selecionado", fg=THEME["muted2"])
            for button in [self.edit_item_button, self.duplicate_item_button, self.equip_item_button, *self.enchant_action_buttons]:
                button.configure(state="disabled")
            return
        db = self.item_db(item)
        is_gear = str(db.get("Type", "")).upper() == "GEAR"
        slot_count = self.expected_enchant_slot_count(item) or 0
        self.edit_item_button.configure(state="normal")
        self.duplicate_item_button.configure(state="normal")
        self.equip_item_button.configure(state="normal" if is_gear else "disabled")
        for button in self.enchant_action_buttons:
            button.configure(state="normal" if is_gear and slot_count else "disabled")
        title = f"{self.item_name(item).upper()}  ·  {rarity_label(self.item_rarity(item)) or 'ITEM'}  ·  CÓDIGO {item.get('ItemKey')}"
        self.detail_title.configure(text=title)
        self.detail_icon.configure(image=self.get_icon(item) or "")
        if origin_label is not None:
            uid = safe_int(item.get("UniqueId"))
            places = self.uid_location_labels(uid)
            origin_label.configure(
                text=f"Onde está: {' · '.join(places)}  ·  ID único {uid}" if places
                else f"Sem local no save (aparece só na aba Todos os itens)  ·  ID único {uid}",
                fg=THEME["muted"] if places else THEME["warning"],
            )
        if self.ensure_enchant_shape(item):
            self.mark_dirty("Estrutura de encantamentos normalizada; salve para confirmar.")
        enchants = item.get("EnchantData", [])
        if not enchants:
            reason = (
                "Materiais não recebem encantamentos. Escolha um equipamento."
                if not is_gear
                else "Esta raridade não possui espaços de encantamento."
            )
            tk.Label(
                self.enchant_rows,
                text=reason,
                fg=THEME["muted"],
                bg=THEME["panel"],
                font=(UI_FONT, 10, "italic"),
            ).pack(pady=28)
        for index, enchant in enumerate(enchants):
            self.make_enchant_row(index, enchant).pack(fill=X, pady=4)
 
    def make_enchant_row(self, index: int, enchant: dict) -> tk.Frame:
        recipe = ENCHANT_GROUPS[index] if index < len(ENCHANT_GROUPS) else "VAZIO"
        non_empty = self.enchant_is_filled(enchant)
        color = RECIPE_COLORS.get(recipe, THEME["muted2"]) if non_empty else THEME["disabled"]
        bg = THEME["card"] if non_empty else THEME["card"]
        row = tk.Frame(self.enchant_rows, bg=bg, bd=1, relief="solid", height=72)
        row.pack_propagate(False)
        badge = tk.Label(row, text=recipe, fg=THEME["text"], bg=color, font=(UI_FONT, 7, "bold"), padx=6, pady=2)
        badge.pack(side=LEFT, padx=10)
        stat = STAT_TYPES.get(safe_int(enchant.get("StatType")), f"StatType {enchant.get('StatType')}")
        mat = self.db_by_key.get(str(enchant.get("MaterialKey")), {}).get("Name", f"Material {enchant.get('MaterialKey')}")
        if non_empty:
            text = f"{mat}  ·  {stat}  ·  T{enchant.get('Tier')}  ·  valor {enchant.get('Value')}"
        else:
            text = "Espaço vazio — use Editar ou Colar"
        tk.Label(row, text=text, fg=THEME["text"] if non_empty else THEME["muted2"], bg=bg, font=(UI_FONT, 9, "bold" if non_empty else "italic")).pack(side=LEFT, padx=8)
        ttk.Button(row, text="Editar", command=lambda: self.open_enchant_editor(index)).pack(side=RIGHT, padx=8)
        ttk.Button(row, text="Limpar", command=lambda: self.clear_enchant(index), state="normal" if non_empty else "disabled").pack(side=RIGHT)
        ttk.Button(row, text="Colar", command=lambda: self.paste_enchant(index)).pack(side=RIGHT, padx=(0, 6))
        ttk.Button(row, text="Copiar", command=lambda: self.copy_enchant(index), state="normal" if non_empty else "disabled").pack(side=RIGHT, padx=(0, 6))
        return row
 
    def open_enchant_editor(self, index: int) -> None:
        if not self.selected_item:
            return
        if str(self.item_db(self.selected_item).get("Type", "")).upper() != "GEAR":
            messagebox.showinfo(APP_NAME, "Somente equipamentos podem receber encantamentos.")
            return
        if index < 0 or index >= len(self.selected_item.get("EnchantData", [])):
            messagebox.showinfo(APP_NAME, "Este espaço de encantamento não está disponível para o item.")
            return
        enchant = self.selected_item["EnchantData"][index]
        win = tk.Toplevel(self.root)
        win.title(f"Editar encantamento #{index + 1}")
        win.configure(bg=THEME["base"])
        self.configure_dialog(win, 660, 360)
        vars_by_key: dict[str, StringVar] = {}
        recipe_label = ENCHANT_GROUPS[index].lower()
        recipe_types = ENCHANT_RECIPE_TYPES.get(len(self.selected_item.get("EnchantData", [])), ())
        expected_recipe = recipe_types[index] if index < len(recipe_types) else safe_int(enchant.get("RecipeType"))
        tk.Label(
            win,
            text=f"Grupo: {recipe_label.capitalize()}  ·  espaço {index + 1}",
            fg=THEME["text"],
            bg=THEME["base"],
            font=(UI_FONT, 11, "bold"),
        ).grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(14, 8))
        fields = [
            ("MaterialKey", self.material_choices()),
            ("StatType", self.stat_type_choices_for_item(self.selected_item)),
            ("Tier", TIERS),
            ("Value", None),
        ]
        field_labels = {
            "MaterialKey": "Material",
            "StatType": "Atributo permitido",
            "Tier": "Nível",
            "Value": "Valor",
        }
        for row, (key, choices) in enumerate(fields, start=1):
            tk.Label(win, text=field_labels.get(key, key), fg=THEME["muted"], bg=THEME["base"]).grid(row=row, column=0, sticky="w", padx=14, pady=6)
            raw_value = str(enchant.get(key, 0))
            display_value = raw_value
            if choices:
                display_value = next((choice for choice in choices if normalize_choice(choice) == raw_value), raw_value)
            var = StringVar(value=display_value)
            vars_by_key[key] = var
            if choices:
                state = "readonly"
                ttk.Combobox(win, textvariable=var, values=choices, state=state).grid(row=row, column=1, sticky="ew", padx=10, pady=6)
            else:
                ttk.Entry(win, textvariable=var).grid(row=row, column=1, sticky="ew", padx=10, pady=6)
        win.columnconfigure(1, weight=1)
 
        def apply() -> None:
            try:
                values = {key: int(normalize_choice(var.get()) or "0") for key, var in vars_by_key.items()}
                filled = any(values.get(key, 0) for key in ("MaterialKey", "StatType", "Tier", "Value"))
                if filled:
                    material = self.db_by_key.get(str(values["MaterialKey"]), {})
                    if str(material.get("Type", "")).upper() != "MATERIAL":
                        messagebox.showerror(APP_NAME, "Escolha um material válido da lista.")
                        return
                    if values["StatType"] <= 0 or not self.stat_allowed_for_item(self.selected_item, values["StatType"]):
                        messagebox.showerror(APP_NAME, "Escolha um atributo permitido para este equipamento.")
                        return
                    if not 1 <= values["Tier"] <= 30:
                        messagebox.showerror(APP_NAME, "O nível deve ficar entre T1 e T30.")
                        return
                    values.update(
                        {
                            "StatModKey": STAT_TYPE_TO_MOD.get(values["StatType"], 0),
                            "RecipeType": expected_recipe,
                            "ModType": 0,
                            "EnchantVersion": None,
                        }
                    )
                else:
                    values = self.empty_enchant()
                enchant.clear()
                enchant.update(values)
                self.sync_enchant_metadata(self.selected_item)
                self.flag_item_modified(self.selected_item)
                win.destroy()
                self.render_enchants()
                self.mark_dirty(f"Encantamento #{index + 1} alterado.")
            except Exception as exc:
                messagebox.showerror(APP_NAME, f"Valor inválido:\n{exc}")
 
        ttk.Button(win, text="Cancelar", command=win.destroy).grid(row=len(fields) + 1, column=0, sticky="w", padx=14, pady=12)
        ttk.Button(win, text="Aplicar", style="Accent.TButton", command=apply).grid(row=len(fields) + 1, column=1, sticky="e", padx=10, pady=12)
        win.bind("<Escape>", lambda _event: win.destroy())
        win.grab_set()
 
    def stat_type_choices_for_item(self, item: dict | None) -> list[str]:
        db = self.item_db(item)
        raw_stats = list(db.get("StatTypes") or [])
        choices = []
        for raw in raw_stats:
            stat_id = STAT_NAME_TO_TYPE.get(str(raw))
            if stat_id is not None:
                choices.append(f"{stat_id} | {STAT_TYPES.get(stat_id, raw)}")
        if choices:
            return ["0 | nenhum", *choices]
        return ["0 | nenhum"] if db else STAT_TYPE_CHOICES
 
    def stat_mod_choices_for_item(self, item: dict | None) -> list[str]:
        allowed_names = {choice.split("|", 1)[1].strip() for choice in self.stat_type_choices_for_item(item) if "|" in choice}
        choices = [f"{key} | {name}" for key, name in STAT_MODS.items() if key == 0 or name in allowed_names]
        return choices
 
    def clear_enchant(self, index: int) -> None:
        if not self.selected_item:
            return
        self.selected_item["EnchantData"][index] = self.empty_enchant()
        self.sync_enchant_metadata(self.selected_item)
        self.flag_item_modified(self.selected_item)
        self.mark_dirty(f"Enchant #{index + 1} limpo.")
        self.render_enchants()
 
    def empty_enchant(self) -> dict:
        return EMPTY_ENCHANT.copy()

    def enchant_is_filled(self, enchant: dict) -> bool:
        return any(safe_int(enchant.get(key)) for key in ("StatModKey", "Tier", "Value", "RecipeType", "MaterialKey", "StatType"))

    def expected_enchant_slot_count(self, item: dict) -> int | None:
        db = self.item_db(item)
        if not db:
            return None
        if str(db.get("Type", "")).upper() != "GEAR":
            return 0
        return RARITY_ENCHANT_SLOT_COUNT.get(str(db.get("Rarity", "")).upper())

    def ensure_enchant_shape(self, item: dict) -> bool:
        changed = False
        enchants = item.get("EnchantData")
        if not isinstance(enchants, list):
            enchants = []
            item["EnchantData"] = enchants
            changed = True
        expected_count = self.expected_enchant_slot_count(item)
        if expected_count is not None and len(enchants) > expected_count:
            extras = enchants[expected_count:]
            if all(isinstance(enchant, dict) and not self.enchant_is_filled(enchant) for enchant in extras):
                del enchants[expected_count:]
                changed = True
        while expected_count is not None and len(enchants) < expected_count:
            enchants.append(self.empty_enchant())
            changed = True
        for index, enchant in enumerate(list(enchants)):
            if not isinstance(enchant, dict):
                enchants[index] = self.empty_enchant()
                changed = True
                continue
            for key, value in EMPTY_ENCHANT.items():
                if key not in enchant:
                    enchant[key] = value
                    changed = True
        return changed

    def sync_enchant_metadata(self, item: dict, normalize_slots: bool = True) -> bool:
        changed = self.ensure_enchant_shape(item)
        counts = [0, 0, 0]
        recipe_types = ENCHANT_RECIPE_TYPES.get(len(item["EnchantData"]), ())
        for index, enchant in enumerate(item["EnchantData"]):
            if not self.enchant_is_filled(enchant):
                if enchant != self.empty_enchant():
                    item["EnchantData"][index] = self.empty_enchant()
                    changed = True
                continue
            if index >= 6:
                continue
            group = index // 2
            counts[group] += 1
            expected_recipe = recipe_types[index] if index < len(recipe_types) else None
            if normalize_slots and expected_recipe is not None and safe_int(enchant.get("RecipeType")) != expected_recipe:
                enchant["RecipeType"] = expected_recipe
                changed = True
            expected_mod = STAT_TYPE_TO_MOD.get(safe_int(enchant.get("StatType")), 0)
            if safe_int(enchant.get("StatModKey")) != expected_mod:
                enchant["StatModKey"] = expected_mod
                changed = True
            if "EnchantVersion" not in enchant:
                enchant["EnchantVersion"] = None
                changed = True
        if item.get("EnchantCount") != counts:
            item["EnchantCount"] = counts
            changed = True
        total_fields = ["DecorationAppliedTotalCount", "EngravingAppliedTotalCount", "InscriptionAppliedTotalCount"]
        for index, field in enumerate(total_fields):
            current = max(0, safe_int(item.get(field)))
            expected = max(current, counts[index])
            if item.get(field) != expected:
                item[field] = expected
                changed = True
        return changed

    def stat_allowed_for_item(self, item: dict, stat_type: int) -> bool:
        db = self.item_db(item)
        allowed = {STAT_NAME_TO_TYPE.get(str(raw)) for raw in db.get("StatTypes", [])}
        allowed.discard(None)
        return stat_type in allowed if db else True
 
    def copy_enchant(self, index: int) -> None:
        if not self.selected_item:
            return
        enchants = self.selected_item.get("EnchantData", [])
        if index >= len(enchants):
            return
        self.enchant_clipboard = copy.deepcopy(enchants[index])
        self.status_var.set(f"Encantamento #{index + 1} copiado.")
 
    def paste_enchant(self, index: int) -> None:
        if not self.selected_item:
            return
        expected_count = self.expected_enchant_slot_count(self.selected_item) or 0
        if index < 0 or index >= expected_count:
            messagebox.showinfo(APP_NAME, "Este item não aceita encantamento neste espaço.")
            return
        if self.enchant_clipboard is None:
            messagebox.showinfo(APP_NAME, "Copie um encantamento primeiro.")
            return
        stat_type = safe_int(self.enchant_clipboard.get("StatType"))
        if stat_type and not self.stat_allowed_for_item(self.selected_item, stat_type):
            messagebox.showerror(APP_NAME, "Esse atributo não se aplica ao item selecionado e não será colado.")
            return
        enchants = self.selected_item.setdefault("EnchantData", [])
        while len(enchants) <= index:
            enchants.append(self.empty_enchant())
        enchants[index] = copy.deepcopy(self.enchant_clipboard)
        recipe_types = ENCHANT_RECIPE_TYPES.get(len(enchants), ())
        if index < len(recipe_types):
            enchants[index]["RecipeType"] = recipe_types[index]
        enchants[index]["StatModKey"] = STAT_TYPE_TO_MOD.get(safe_int(enchants[index].get("StatType")), 0)
        enchants[index].setdefault("EnchantVersion", None)
        self.sync_enchant_metadata(self.selected_item)
        self.flag_item_modified(self.selected_item)
        self.mark_dirty(f"Encantamento colado no espaço #{index + 1}.")
        self.render_enchants()
 
    def copy_all_enchants(self) -> None:
        if not self.selected_item:
            messagebox.showinfo(APP_NAME, "Selecione um item primeiro.")
            return
        if not (self.expected_enchant_slot_count(self.selected_item) or 0):
            messagebox.showinfo(APP_NAME, "Este item não possui espaços de encantamento.")
            return
        self.enchant_list_clipboard = copy.deepcopy(self.selected_item.get("EnchantData", []))
        self.status_var.set(f"{len(self.enchant_list_clipboard)} encantamentos copiados do item.")
 
    def paste_all_enchants(self) -> None:
        if not self.selected_item:
            messagebox.showinfo(APP_NAME, "Selecione um item primeiro.")
            return
        if self.enchant_list_clipboard is None:
            messagebox.showinfo(APP_NAME, "Copie os enchants de um item primeiro.")
            return
        incompatible = sum(
            1
            for enchant in self.enchant_list_clipboard
            if safe_int(enchant.get("StatType")) and not self.stat_allowed_for_item(self.selected_item, safe_int(enchant.get("StatType")))
        )
        if incompatible:
            messagebox.showerror(
                APP_NAME,
                f"{incompatible} encantamento(s) não se aplicam ao item selecionado. Nada foi colado.",
            )
            return
        target_count = self.expected_enchant_slot_count(self.selected_item) or 0
        if target_count == 0:
            messagebox.showinfo(APP_NAME, "Este item não possui espaços de encantamento.")
            return
        pasted = copy.deepcopy(self.enchant_list_clipboard[:target_count])
        while len(pasted) < target_count:
            pasted.append(self.empty_enchant())
        self.selected_item["EnchantData"] = pasted
        self.sync_enchant_metadata(self.selected_item)
        self.flag_item_modified(self.selected_item)
        self.mark_dirty(f"{min(len(self.enchant_list_clipboard), target_count)} encantamentos colados no item.")
        self.render_enchants()
 
    def clear_all_enchants(self) -> None:
        if not self.selected_item:
            return
        slot_count = len(self.selected_item.get("EnchantData", []))
        self.selected_item["EnchantData"] = [self.empty_enchant() for _ in range(slot_count)]
        self.sync_enchant_metadata(self.selected_item)
        self.flag_item_modified(self.selected_item)
        self.mark_dirty("Todos os encantamentos do item foram limpos.")
        self.render_enchants()

    def edit_selected_item(self) -> None:
        if not self.selected_item:
            messagebox.showinfo(APP_NAME, "Selecione um item primeiro.")
            return
        self.open_item_editor(self.selected_item)

    def duplicate_selected_item(self) -> None:
        if not self.selected_item:
            messagebox.showinfo(APP_NAME, "Selecione um item primeiro.")
            return
        duplicates = self.duplicate_item(self.selected_item, self.ask_quantity("Duplicar item", "Quantas cópias deseja criar?", 1))
        if duplicates:
            self.select_item(duplicates[-1])
            self.notebook.select(self.inventory_tab)

    def duplicate_item(self, item: dict, quantity: int = 1) -> list[dict]:
        if not self.data:
            messagebox.showinfo(APP_NAME, "Abra um save primeiro.")
            return []
        if quantity <= 0:
            return []
        if self.protected_mode_enabled() and quantity > PROTECTED_BATCH_LIMIT:
            messagebox.showerror(
                APP_NAME,
                f"O Modo Protegido limita a duplicação a {PROTECTED_BATCH_LIMIT} itens por operação.",
            )
            return []
        if self.free_slot_count("Inventario") < quantity:
            messagebox.showerror(APP_NAME, f"O Inventário tem apenas {self.free_slot_count('Inventario')} espaço(s) livre(s).")
            return []
        player = self.data["player"]
        created: list[dict] = []
        last_slot = 0
        for _ in range(quantity):
            new_item = copy.deepcopy(item)
            new_uid = self.next_unique_id()
            new_item["UniqueId"] = new_uid
            new_item["PrevUniqueId"] = 0
            new_item.pop("IsServerPendingItem", None)
            self.sync_enchant_metadata(new_item)
            player.setdefault("itemSaveDatas", []).append(new_item)
            self.items.append(new_item)
            self.items_by_uid[new_uid] = new_item
            self.flag_item_created(new_item)
            last_slot = self.place_item(new_uid, "Inventario")
            created.append(new_item)
        self.selected_item = created[-1]
        self.mark_dirty(f"{len(created)} cópia(s) criada(s). Último espaço: Inventário #{last_slot}")
        self.refresh_all()
        messagebox.showinfo(APP_NAME, f"{len(created)} cópia(s) criada(s) no Inventário.")
        return created

    def ask_quantity(self, title: str, prompt: str, default: int = 1) -> int:
        win = tk.Toplevel(self.root)
        win.title(title)
        win.configure(bg=THEME["base"])
        win.resizable(False, False)
        value = StringVar(value=str(default))
        result = {"value": 0}
        tk.Label(win, text=prompt, fg=THEME["text"], bg=THEME["base"]).grid(row=0, column=0, columnspan=2, sticky="w", padx=14, pady=(14, 8))
        spin = ttk.Spinbox(win, from_=1, to=999999999999, textvariable=value, width=16)
        spin.grid(row=1, column=0, sticky="w", padx=14, pady=8)
        def ok() -> None:
            result["value"] = max(1, safe_int(value.get(), default))
            win.destroy()
        def cancel() -> None:
            win.destroy()
        ttk.Button(win, text="Cancelar", command=cancel).grid(row=2, column=0, sticky="w", padx=14, pady=14)
        ttk.Button(win, text="OK", style="Accent.TButton", command=ok).grid(row=2, column=1, sticky="e", padx=14, pady=14)
        win.bind("<Return>", lambda _e: ok())
        win.transient(self.root)
        win.grab_set()
        spin.focus_set()
        self.root.wait_window(win)
        return result["value"]

    def next_unique_id(self) -> int:
        used = [safe_int(item.get("UniqueId")) for item in self.items if isinstance(item, dict)]
        if self.data:
            player = self.data["player"]
            for hero in player.get("heroSaveDatas", []):
                used.extend(safe_int(uid) for uid in hero.get("equippedItemIds", []))
            for source in ("inventorySaveDatas", "stashSaveDatas", "remakeTradingStashSaveDatas"):
                used.extend(safe_int(slot.get("ItemUniqueId")) for slot in player.get(source, []))
        return (max(used) if used else 0) + 1

    def place_item_in_inventory(self, uid: int) -> int:
        return self.place_item(uid, "Inventario")

    def stash_page_for_index(self, index: int) -> int:
        return index // STASH_PAGE_SIZE + 1

    def stash_local_slot(self, index: int) -> int:
        return index % STASH_PAGE_SIZE + 1

    def destination_sources(self, target: str) -> list[tuple[str, int | None]]:
        if target == "Automatico":
            return [("inventorySaveDatas", None), *[("stashSaveDatas", page) for page in range(1, STASH_PAGE_COUNT + 1)]]
        if target == "Armazem":
            return [("stashSaveDatas", page) for page in range(1, STASH_PAGE_COUNT + 1)]
        if target.startswith("Armazem "):
            page = safe_int(target.rsplit(" ", 1)[-1])
            if 1 <= page <= STASH_PAGE_COUNT:
                return [("stashSaveDatas", page)]
        return [("inventorySaveDatas", None)]

    def slots_for_destination(self, target: str) -> list[tuple[str, dict]]:
        if not self.data:
            return []
        player = self.data["player"]
        result: list[tuple[str, dict]] = []
        for source, page in self.destination_sources(target):
            for slot in player.get(source, []):
                index = safe_int(slot.get("Index"), -1)
                if page is not None and not ((page - 1) * STASH_PAGE_SIZE <= index < page * STASH_PAGE_SIZE):
                    continue
                result.append((source, slot))
        return result

    def slot_is_available(self, source: str, slot: dict) -> bool:
        return not safe_int(slot.get("ItemUniqueId")) and self.slot_is_unlocked(source, slot)

    @staticmethod
    def slot_is_unlocked(source: str, slot: dict) -> bool:
        """Só considera livre um espaço comprovadamente desbloqueado.

        O jogo grava ``IsUnLock`` no armazém e ``IsUnlock`` no inventário. Antes
        da 3.4.0 a ausência das duas chaves era lida como "desbloqueado", o que
        faria o editor ocupar — e marcar como liberadas — páginas de armazém que
        o jogador não possui. Aceitar as duas grafias e negar o desconhecido é o
        comportamento seguro."""
        for key in ("IsUnLock", "IsUnlock"):
            if key in slot:
                return bool(slot.get(key))
        return source != "stashSaveDatas"

    def place_item(self, uid: int, target: str) -> int:
        for source, slot in self.slots_for_destination(target):
            if self.slot_is_available(source, slot):
                slot["ItemUniqueId"] = uid
                if source == "stashSaveDatas":
                    slot["IsUnLock"] = True
                else:
                    slot["IsUnlock"] = True
                return safe_int(slot.get("Index"))
        return -1

    def free_slot_count(self, target: str) -> int:
        return sum(self.slot_is_available(source, slot) for source, slot in self.slots_for_destination(target))

    def stash_page_is_unlocked(self, stash_page: int) -> bool:
        """Uma página só está disponível se algum de seus espaços estiver liberado.

        As páginas de armazém acima das iniciais vêm de DLC. Sem esta checagem,
        uma página bloqueada aparecia apenas como "0 espaços livres" e as filas
        do assistente relatavam "capacidade atendida" quando na verdade não
        havia para onde mover nada."""
        slots = self.slots_for_destination(f"Armazem {stash_page}")
        if not slots:
            return False
        return any(self.slot_is_unlocked(source, slot) for source, slot in slots)

    def stash_page_capacity(self, stash_page: int) -> tuple[bool, int]:
        """Devolve ``(página liberada, espaços livres)`` em uma única leitura."""
        unlocked = self.stash_page_is_unlocked(stash_page)
        return unlocked, self.free_slot_count(f"Armazem {stash_page}") if unlocked else 0

    def storage_page_of_row(self, row: dict) -> int | None:
        """Página do armazém de uma linha de armazenamento; ``None`` no inventário."""
        if row.get("source") != "stashSaveDatas":
            return None
        return self.stash_page_for_index(safe_int(row.get("source_slot", {}).get("Index")))

    def commemorative_coin_rows(self) -> list[dict]:
        """Moedas comemorativas presentes no inventário e no armazém."""
        return coins.collect_coin_rows(self.storage_item_rows())

    def commemorative_coin_groups(self) -> list[coins.CoinGroup]:
        return coins.group_coins(
            self.commemorative_coin_rows(),
            location_of=lambda row: self.storage_label(row["source"], row["source_slot"]).split(" - ")[0],
        )

    def build_commemorative_coin_plan(self, stash_page: int) -> coins.CoinPlan:
        """Planeja juntar todas as moedas em uma página, sem alterar o save."""
        unlocked, capacity = self.stash_page_capacity(stash_page)
        return coins.build_coin_plan(
            self.commemorative_coin_rows(),
            stash_page,
            capacity=capacity,
            page_unlocked=unlocked,
            page_of_row=self.storage_page_of_row,
        )

    def trade_ship_status(self):
        """Estado do Navio de Trocas para o save aberto."""
        return trade_ship_status(self.data["player"] if self.data else None)

    def configured_market_slots(self) -> int:
        """Slots de anúncio considerados por rodada."""
        return BASE_LISTING_SLOTS

    def page_block_reason(self, stash_page: int) -> str:
        """Explica por que uma página não aceita a fila, em vez de só mostrar zero."""
        if not self.stash_page_is_unlocked(stash_page):
            return (
                f"O Armazém {stash_page} está bloqueado neste save. As páginas extras vêm do "
                "jogo/DLC e o editor não as libera. Escolha uma página já disponível."
            )
        return f"O Armazém {stash_page} não possui espaços livres."

    def queue_summary_text(self, stash_page: int, shown: int, pool: int, noun: str) -> str:
        """Resumo que separa 'não há candidato' de 'não há espaço' de 'limite da rodada'.

        Até a 3.3.2 uma página bloqueada produzia "0 pré-candidato(s) seguro(s) ·
        capacidade disponível atendida", texto que sugeria que o save não tinha
        nada a oferecer quando o problema era o destino."""
        unlocked, free_slots = self.stash_page_capacity(stash_page)
        if not unlocked:
            return self.page_block_reason(stash_page)
        if not pool:
            return f"Nenhum {noun} seguro encontrado fora do Armazém {stash_page}."
        if not free_slots:
            return f"{pool} {noun}(s) disponível(is), mas o Armazém {stash_page} está cheio."
        held_back = max(0, pool - shown)
        text = f"{shown} {noun}(s) nesta rodada"
        if held_back:
            text += f" · {held_back} fora do limite desta rodada"
        text += f" · {free_slots} espaço(s) livre(s) no Armazém {stash_page}"
        return text + "."

    def market_round_capacity(self, stash_page: int) -> int:
        """Quantos itens cabem na rodada: o menor entre espaço real e slots.

        Ponto de extensão explícito. Até a 3.3.2 a camada final obtinha esse
        número interceptando ``free_slot_count`` e inspecionando o nome do
        chamador com ``sys._getframe``; qualquer renomeação silenciava o limite."""
        unlocked, free_slots = self.stash_page_capacity(stash_page)
        if not unlocked:
            return 0
        return max(0, min(free_slots, self.configured_market_slots()))

    def slot_prefixes(self, hero_key: int, slot_index: int) -> set[str]:
        return intelligence_slot_prefixes(hero_key, slot_index)

    def item_compatible_with_slot(self, item: dict, hero: dict, slot_index: int) -> bool:
        if self.item_db(item).get("Type") != "GEAR":
            return False
        prefix = str(item.get("ItemKey", ""))[:2]
        return prefix in self.slot_prefixes(safe_int(hero.get("heroKey")), slot_index)

    def storage_label(self, source: str, slot: dict) -> str:
        index = safe_int(slot.get("Index"))
        if source == "stashSaveDatas":
            return f"Armazém {self.stash_page_for_index(index)} - espaço {self.stash_local_slot(index)}"
        if source == "remakeTradingStashSaveDatas":
            return f"Trocas - espaço {index + 1}"
        return f"Inventário - espaço {index + 1}"

    def auto_equip_score(self, item: dict | None, hero: dict) -> tuple[float, ...]:
        if not item:
            return (0.0, 0.0, 0.0, 0.0, 0.0, 0.0)
        db = self.item_db(item)
        rarity = RARITY_RANK.get(str(db.get("Rarity", "")).upper(), 0)
        weights = HERO_STAT_WEIGHTS.get(safe_int(hero.get("heroKey")), {})
        filled = 0
        total_tier = 0
        weighted_tier = 0.0
        value_score = 0.0
        for enchant in item.get("EnchantData", []):
            if not isinstance(enchant, dict) or not self.enchant_is_filled(enchant):
                continue
            filled += 1
            tier = max(0, safe_int(enchant.get("Tier")))
            stat_type = safe_int(enchant.get("StatType"))
            weight = weights.get(stat_type, 1.0)
            total_tier += tier
            weighted_tier += tier * weight
            value_score += math.log10(abs(safe_int(enchant.get("Value"))) + 1) * weight
        return (
            float(rarity),
            float(bool(item.get("IsChaotic"))),
            round(weighted_tier, 4),
            float(total_tier),
            float(filled),
            round(value_score, 4),
        )

    def auto_equip_score_label(self, item: dict | None, hero: dict) -> str:
        if not item:
            return "Vazio"
        score = self.auto_equip_score(item, hero)
        chaos = " + caos" if item.get("IsChaotic") else ""
        return f"{self.item_rarity(item) or 'SEM DB'}{chaos} | afinidade {score[2]:.0f} | tiers {score[3]:.0f}"

    def enchant_quality_label(self, item: dict | None, hero: dict) -> str:
        if not item:
            return "Sem item"
        enchants = item.get("EnchantData", [])
        filled = sum(isinstance(row, dict) and self.enchant_is_filled(row) for row in enchants)
        score = self.auto_equip_score(item, hero)
        if not enchants:
            return "Sem espaços"
        return f"{filled}/{len(enchants)} ativos · AF {score[2]:.0f} · T{score[3]:.0f}"

    def build_auto_equip_plan(self, hero: dict) -> list[dict]:
        if not self.data:
            return []
        player = self.data["player"]
        available: list[tuple[dict, str, dict]] = []
        for source in ("inventorySaveDatas", "stashSaveDatas"):
            for slot in player.get(source, []):
                index = safe_int(slot.get("Index"))
                if source == "stashSaveDatas" and self.stash_page_for_index(index) > STASH_PAGE_COUNT:
                    continue
                item = self.items_by_uid.get(safe_int(slot.get("ItemUniqueId")))
                if item and self.item_db(item).get("Type") == "GEAR":
                    available.append((item, source, slot))

        equipped_ids = list(hero.get("equippedItemIds", []))
        used_candidates: set[int] = set()
        plans: list[dict] = []
        for slot_index in range(10):
            current_uid = safe_int(equipped_ids[slot_index]) if slot_index < len(equipped_ids) else 0
            current = self.items_by_uid.get(current_uid)
            if current and not self.item_db(current):
                continue
            current_score = self.auto_equip_score(current, hero)
            choices = [
                (self.auto_equip_score(candidate, hero), candidate, source, source_slot)
                for candidate, source, source_slot in available
                if safe_int(candidate.get("UniqueId")) not in used_candidates
                and self.item_compatible_with_slot(candidate, hero, slot_index)
            ]
            if not choices:
                continue
            best_score, best, source, source_slot = max(choices, key=lambda row: row[0])
            if best_score <= current_score:
                continue
            used_candidates.add(safe_int(best.get("UniqueId")))
            plans.append(
                {
                    "slot_index": slot_index,
                    "current": current,
                    "replacement": best,
                    "source": source,
                    "source_slot": source_slot,
                    "current_score": current_score,
                    "replacement_score": best_score,
                }
            )
        return plans

    def apply_auto_equip_plan(self, hero: dict, plans: list[dict]) -> int:
        ids = hero.setdefault("equippedItemIds", [])
        while len(ids) < 10:
            ids.append(0)
        for plan in plans:
            slot_index = safe_int(plan.get("slot_index"), -1)
            replacement = plan.get("replacement")
            source_slot = plan.get("source_slot")
            if not 0 <= slot_index < 10 or not isinstance(replacement, dict) or not isinstance(source_slot, dict):
                return 0
            if safe_int(source_slot.get("ItemUniqueId")) != safe_int(replacement.get("UniqueId")):
                return 0
        for plan in plans:
            slot_index = safe_int(plan.get("slot_index"), -1)
            current = plan.get("current")
            replacement = plan["replacement"]
            source_slot = plan["source_slot"]
            ids[slot_index] = safe_int(replacement.get("UniqueId"))
            source_slot["ItemUniqueId"] = safe_int(current.get("UniqueId")) if isinstance(current, dict) else 0
        return len(plans)

    def open_auto_equip_preview(self) -> None:
        if not self.selected_hero or not self.data:
            messagebox.showinfo(APP_NAME, "Selecione um herói primeiro.")
            return
        errors = [issue for issue in self.validate_save() if issue["severity"] == "ERRO"]
        if errors:
            messagebox.showerror(APP_NAME, "O save possui erros estruturais. Use Validar save e reparar antes do equipamento automático.")
            return
        hero = self.selected_hero
        plans = self.build_auto_equip_plan(hero)
        hname = HERO_NAMES.get(hero.get("heroKey"), f"Herói {hero.get('heroKey')}")
        if not plans:
            messagebox.showinfo(APP_NAME, f"{hname} já está com os melhores itens encontrados no Inventário e no Armazém.")
            return

        win = tk.Toplevel(self.root)
        win.title(f"Equipar melhor — {hname}")
        win.configure(bg=THEME["base"])
        self.configure_dialog(win, 1000, 560, resizable=True)
        tk.Label(win, text=f"TROCAS RECOMENDADAS PARA {hname.upper()}", fg=THEME["text"], bg=THEME["base"], font=(UI_FONT, 11, "bold")).pack(anchor="w", padx=12, pady=(12, 3))
        tk.Label(win, text="A nota combina raridade, nível conhecido, afinidade e tiers dos encantamentos; a prévia mostra a decisão antes de aplicar.", fg=THEME["muted"], bg=THEME["base"], font=(UI_FONT, 9)).pack(anchor="w", padx=12, pady=(0, 8))
        columns = ("slot", "current", "current_score", "replacement", "new_score", "origin")
        tree = ttk.Treeview(win, columns=columns, show="tree headings", height=13)
        tree.heading("#0", text="")
        tree.column("#0", width=44, minwidth=44, stretch=False)
        for key, label, width in [
            ("slot", "Slot", 110),
            ("current", "Atual", 150),
            ("current_score", "Nota atual", 170),
            ("replacement", "Recomendado", 150),
            ("new_score", "Nota nova", 170),
            ("origin", "Origem", 165),
        ]:
            tree.heading(key, text=label)
            tree.column(key, width=width, anchor="w")
        preview_rows: list[tuple[str, dict]] = []
        preview_plans: dict[str, dict] = {}
        for plan in plans:
            replacement = plan["replacement"]
            iid = tree.insert(
                "",
                END,
                image=self.get_icon(replacement) or "",
                values=(
                    SLOT_NAMES.get(plan["slot_index"], "SLOT"),
                    self.item_name(plan["current"]),
                    self.auto_equip_score_label(plan["current"], hero),
                    self.item_name(replacement),
                    self.auto_equip_score_label(replacement, hero),
                    self.storage_label(plan["source"], plan["source_slot"]),
                ),
            )
            preview_rows.append((iid, replacement))
            preview_plans[iid] = plan
        table = self.attach_scrollbars(win, tree)
        table.pack(fill=BOTH, expand=True, padx=12, pady=8)

        def apply_rows(selected_plans: list[dict]) -> None:
            if not selected_plans:
                return
            applied = self.apply_auto_equip_plan(hero, selected_plans)
            if applied != len(selected_plans):
                messagebox.showerror(APP_NAME, "A origem de algum item mudou. Feche a prévia e tente novamente.")
                return
            self.selected_item = selected_plans[-1]["replacement"]
            self.mark_dirty(f"{applied} item(ns) melhor(es) equipado(s) em {hname}.")
            self.refresh_all()
            win.destroy()
            messagebox.showinfo(APP_NAME, f"Equipamento automático concluído para {hname}.\nTrocas realizadas: {applied}\nUse Salvar alterações para gravar no arquivo.")

        def apply_selected() -> None:
            selected = tree.selection()
            if selected and selected[0] in preview_plans:
                apply_rows([preview_plans[selected[0]]])

        buttons = ttk.Frame(win, style="Panel.TFrame", padding=10)
        buttons.pack(side="bottom", fill=X, before=table)
        ttk.Button(buttons, text="Cancelar", command=win.destroy).pack(side=LEFT)
        selected_button = ttk.Button(buttons, text="Substituir selecionado", command=apply_selected, state="disabled")
        selected_button.pack(side=LEFT, padx=6)
        ttk.Button(
            buttons,
            text=f"Substituir todas ({len(plans)})",
            style="Accent.TButton",
            command=lambda: apply_rows(plans),
        ).pack(side=RIGHT)
        tree.bind(
            "<<TreeviewSelect>>",
            lambda _event: selected_button.configure(state="normal" if tree.selection() else "disabled"),
        )
        tree.bind("<Double-Button-1>", lambda _event: apply_selected())

        def refresh_preview_icons() -> None:
            for iid, replacement in preview_rows:
                if tree.exists(iid):
                    tree.item(iid, image=self.get_icon(replacement) or "")

        self.register_icon_refresher(win, refresh_preview_icons)
        win.bind("<Escape>", lambda _event: win.destroy())
        win.grab_set()

    def auto_equip_all_strategy_note(self) -> str:
        """Explica ao usuário qual critério a otimização global realmente usa.

        A camada intermediária substitui ``build_auto_equip_all_plan`` por uma
        alocação exata, então uma frase fixa aqui descreveria o algoritmo errado
        no produto. Cada camada declara o próprio critério."""
        return (
            "Cada item é usado uma única vez e nenhum herói é rebaixado para beneficiar outro. "
            "Os heróis são avaliados em ordem: um item disputado por dois vai para o que aparece "
            "primeiro na lista — não é um ótimo global calculado entre todos."
        )

    def build_auto_equip_all_plan(self) -> list[dict]:
        """Planeja todos os heróis sequencialmente numa cópia para não reutilizar itens."""
        if not self.data:
            return []
        working_data = copy.deepcopy(self.data)
        working = ProEditor.__new__(ProEditor)
        working.data = working_data
        working.items = list(working_data["player"].get("itemSaveDatas", []))
        working.db = self.db
        working.db_by_key = self.db_by_key
        working.rebuild_item_index()
        result: list[dict] = []
        original_heroes = self.data["player"].get("heroSaveDatas", [])
        working_heroes = working_data["player"].get("heroSaveDatas", [])
        for hero_index, working_hero in enumerate(working_heroes):
            plans = working.build_auto_equip_plan(working_hero)
            if not plans:
                continue
            original_hero = original_heroes[hero_index]
            for plan in plans:
                result.append(
                    {
                        "hero": original_hero,
                        "hero_key": safe_int(original_hero.get("heroKey")),
                        "slot_index": plan["slot_index"],
                        "current_uid": safe_int(plan.get("current", {}).get("UniqueId")) if isinstance(plan.get("current"), dict) else 0,
                        "replacement_uid": safe_int(plan["replacement"].get("UniqueId")),
                        "current_score": plan["current_score"],
                        "replacement_score": plan["replacement_score"],
                    }
                )
            working.apply_auto_equip_plan(working_hero, plans)
        return result

    def apply_auto_equip_all_plan(self, rows: list[dict]) -> int:
        if not self.data:
            return 0
        # Recalcula no estado atual e só aplica se a prévia ainda for idêntica.
        current = self.build_auto_equip_all_plan()
        signature = lambda values: [
            (row["hero_key"], row["slot_index"], row["current_uid"], row["replacement_uid"]) for row in values
        ]
        if signature(current) != signature(rows):
            return 0
        applied = 0
        for row in rows:
            hero = row["hero"]
            ids = hero.setdefault("equippedItemIds", [])
            while len(ids) < 10:
                ids.append(0)
            current_uid = safe_int(ids[row["slot_index"]])
            replacement_uid = row["replacement_uid"]
            replacement_locations = [
                (source, slot)
                for source in ("inventorySaveDatas", "stashSaveDatas")
                for slot in self.data["player"].get(source, [])
                if safe_int(slot.get("ItemUniqueId")) == replacement_uid
            ]
            if len(replacement_locations) != 1:
                return 0
            _source, source_slot = replacement_locations[0]
            ids[row["slot_index"]] = replacement_uid
            source_slot["ItemUniqueId"] = current_uid
            applied += 1
        return applied

    def open_auto_equip_all_preview(self) -> None:
        if not self.data:
            messagebox.showinfo(APP_NAME, "Abra um save primeiro.")
            return
        if any(issue["severity"] == "ERRO" for issue in self.validate_save()):
            messagebox.showerror(APP_NAME, "O save possui erros estruturais. Use Validar save e reparar primeiro.")
            return
        rows = self.build_auto_equip_all_plan()
        if not rows:
            messagebox.showinfo(APP_NAME, "Todos os heróis já usam os melhores equipamentos locais encontrados.")
            return
        win = tk.Toplevel(self.root)
        win.title("Otimizar todos os heróis")
        win.configure(bg=THEME["base"])
        self.configure_dialog(win, 1080, 620, resizable=True)
        tk.Label(
            win,
            text="OTIMIZAÇÃO GLOBAL DOS HERÓIS",
            fg=THEME["text"],
            bg=THEME["base"],
            font=(UI_FONT, 12, "bold"),
        ).pack(anchor="w", padx=14, pady=(14, 3))
        tk.Label(
            win,
            text=self.auto_equip_all_strategy_note(),
            fg=THEME["muted"],
            bg=THEME["base"],
            wraplength=1020,
            justify="left",
        ).pack(anchor="w", padx=14, pady=(0, 8))
        columns = ("hero", "slot", "current", "replacement", "gain")
        tree = ttk.Treeview(win, columns=columns, show="headings", height=18)
        for key, label, width in [
            ("hero", "Herói", 150), ("slot", "Espaço", 180), ("current", "Atual", 250),
            ("replacement", "Recomendado", 250), ("gain", "Melhoria", 190),
        ]:
            tree.heading(key, text=label)
            tree.column(key, width=width, anchor="w")
        for row in rows:
            current_item = self.items_by_uid.get(row["current_uid"])
            replacement = self.items_by_uid.get(row["replacement_uid"])
            hero = row["hero"]
            origin = next(iter(self.uid_location_labels(row["replacement_uid"])), "sem local")
            tree.insert(
                "",
                END,
                values=(
                    HERO_NAMES.get(row["hero_key"], f"Herói {row['hero_key']}"),
                    SLOT_NAMES.get(row["slot_index"], f"Espaço {row['slot_index']}"),
                    self.item_name(current_item),
                    f"{self.item_name(replacement)} ({origin})",
                    self.auto_equip_score_label(replacement, hero),
                ),
            )
        table = self.attach_scrollbars(win, tree)
        table.pack(fill=BOTH, expand=True, padx=14, pady=8)

        def apply() -> None:
            applied = self.apply_auto_equip_all_plan(rows)
            if applied != len(rows):
                messagebox.showerror(APP_NAME, "O inventário mudou após a prévia. Feche a janela e analise novamente.")
                return
            self.mark_dirty(f"Otimização global concluída: {applied} troca(s) preparada(s).")
            self.refresh_all()
            win.destroy()
            messagebox.showinfo(APP_NAME, f"Otimização concluída.\nTrocas realizadas: {applied}\nUse Salvar alterações para gravar.")

        buttons = ttk.Frame(win, style="Panel.TFrame", padding=10)
        buttons.pack(side="bottom", fill=X, before=table)
        ttk.Button(buttons, text="Cancelar", command=win.destroy).pack(side=LEFT)
        ttk.Button(buttons, text=f"Aplicar {len(rows)} troca(s)", style="Accent.TButton", command=apply).pack(side=RIGHT)
        win.bind("<Escape>", lambda _event: win.destroy())
        win.grab_set()

    def item_quality_score(self, item: dict | None) -> tuple[float, ...]:
        if not item:
            return (0.0, 0.0, 0.0, 0.0, 0.0)
        rarity = RARITY_RANK.get(self.item_rarity(item).upper(), 0)
        filled = 0
        tiers = 0
        values = 0.0
        for enchant in item.get("EnchantData", []):
            if isinstance(enchant, dict) and self.enchant_is_filled(enchant):
                filled += 1
                tiers += max(0, safe_int(enchant.get("Tier")))
                values += math.log10(abs(safe_int(enchant.get("Value"))) + 1)
        return (float(rarity), float(bool(item.get("IsChaotic"))), float(tiers), float(filled), round(values, 4))

    def storage_item_rows(self) -> list[dict]:
        if not self.data:
            return []
        rows: list[dict] = []
        for source in ("inventorySaveDatas", "stashSaveDatas"):
            for slot in self.data["player"].get(source, []):
                uid = safe_int(slot.get("ItemUniqueId"))
                item = self.items_by_uid.get(uid)
                if item:
                    rows.append({"item": item, "source": source, "source_slot": slot})
        return rows

    def item_is_soulstone(self, item: dict) -> bool:
        return "soulstone" in normalize_search_text(self.item_name(item))

    def market_candidate_status(self, item: dict) -> tuple[bool, str]:
        uid = safe_int(item.get("UniqueId"))
        db = self.item_db(item)
        rarity = self.item_rarity(item).upper()
        if uid not in getattr(self, "original_item_uids", set()):
            return False, "criado fora do save carregado"
        if self.item_is_session_changed(item):
            return False, "criado ou alterado nesta sessão"
        if not db:
            return False, "item especial sem dados suficientes no catálogo"
        if bool(item.get("IsBlocked")):
            return False, "item bloqueado no save"
        if any(
            safe_int(uid) == uid_value
            for hero in self.data["player"].get("heroSaveDatas", [])
            for uid_value in [safe_int(value) for value in hero.get("equippedItemIds", [])]
        ):
            return False, "item equipado"
        source_type = safe_int(item.get("ItemGetSourceType"), -1)
        if source_type in MARKET_SOURCE_TYPES_EXCLUDED:
            return False, "origem local não verificável pelo editor"
        policy = market_eligibility(str(db.get("Type") or ""), rarity, is_soulstone=self.item_is_soulstone(item))
        if not policy.allowed:
            return False, policy.reason
        reason = policy.reason
        if any(isinstance(row, dict) and self.enchant_is_filled(row) for row in item.get("EnchantData", [])):
            reason += "; encantamentos serão removidos ao listar"
        return True, reason

    def market_candidates(self, stash_page: int, limit: int) -> list[dict]:
        target = f"Armazem {stash_page}"
        rows: list[dict] = []
        for row in self.storage_item_rows():
            item = row["item"]
            if row["source"] == "stashSaveDatas" and self.stash_page_for_index(safe_int(row["source_slot"].get("Index"))) == stash_page:
                continue
            accepted, reason = self.market_candidate_status(item)
            if not accepted:
                continue
            row = dict(row)
            row["reason"] = reason
            row["quality"] = self.item_quality_score(item)
            rows.append(row)
        rows.sort(key=lambda row: (row["quality"], normalize_search_text(self.item_name(row["item"]))), reverse=True)
        self.last_market_pool = len(rows)
        return rows[: max(0, min(limit, self.market_round_capacity(stash_page)))]

    def recycle_candidates(self, stash_page: int, limit: int, max_rarity: str = "LEGENDARY") -> list[dict]:
        max_rank = RARITY_RANK.get(str(max_rarity).upper(), RARITY_RANK["LEGENDARY"])
        eligible: list[dict] = []
        for row in self.storage_item_rows():
            item = row["item"]
            uid = safe_int(item.get("UniqueId"))
            rarity = self.item_rarity(item).upper()
            if row["source"] == "stashSaveDatas" and self.stash_page_for_index(safe_int(row["source_slot"].get("Index"))) == stash_page:
                continue
            if uid not in getattr(self, "original_item_uids", set()) or self.item_is_session_changed(item):
                continue
            if not self.item_db(item) or self.item_db(item).get("Type") != "GEAR":
                continue
            if bool(item.get("IsBlocked")) or bool(item.get("IsChaotic")):
                continue
            if safe_int(item.get("ItemGetSourceType"), -1) in MARKET_SOURCE_TYPES_EXCLUDED:
                continue
            if RARITY_RANK.get(rarity, 0) > max_rank:
                continue
            eligible.append(row)

        groups: dict[int, list[dict]] = {}
        for row in eligible:
            groups.setdefault(safe_int(row["item"].get("ItemKey")), []).append(row)
        candidates: list[dict] = []
        for group in groups.values():
            if len(group) < 2:
                continue
            ordered = sorted(group, key=lambda row: self.item_quality_score(row["item"]), reverse=True)
            for row in ordered[1:]:
                row = dict(row)
                row["quality"] = self.item_quality_score(row["item"])
                row["reason"] = f"duplicado; a melhor cópia de {self.item_name(row['item'])} foi preservada"
                candidates.append(row)
        candidates.sort(key=lambda row: (row["quality"], normalize_search_text(self.item_name(row["item"]))))
        self.last_recycle_pool = len(candidates)
        _unlocked, capacity = self.stash_page_capacity(stash_page)
        return candidates[: max(0, min(limit, capacity))]

    def apply_storage_queue(self, rows: list[dict], stash_page: int) -> int:
        target_slots = [
            slot
            for source, slot in self.slots_for_destination(f"Armazem {stash_page}")
            if source == "stashSaveDatas" and self.slot_is_available(source, slot)
        ]
        if len(target_slots) < len(rows):
            return 0
        for row in rows:
            item = row.get("item")
            source_slot = row.get("source_slot")
            if not isinstance(item, dict) or not isinstance(source_slot, dict):
                return 0
            if safe_int(source_slot.get("ItemUniqueId")) != safe_int(item.get("UniqueId")):
                return 0
        for row, destination in zip(rows, target_slots):
            uid = safe_int(row["item"].get("UniqueId"))
            row["source_slot"]["ItemUniqueId"] = 0
            destination["ItemUniqueId"] = uid
            destination["IsUnLock"] = True
        return len(rows)

    def campaign_access_changes(self, apply: bool = False) -> list[str]:
        if not self.data:
            return []
        player = self.data["player"]
        common = player.setdefault("commonSaveData", {})
        changes: list[str] = []

        tutorial = common.get("TutorialCleared")
        if isinstance(tutorial, list) and any(not bool(value) for value in tutorial):
            changes.append(f"Concluir {sum(not bool(value) for value in tutorial)} tutorial(is) pendente(s)")
            if apply:
                common["TutorialCleared"] = [True] * len(tutorial)
        for key, desired, label in [
            ("isFirstPlay", False, "Remover estado de primeira partida"),
            ("isOpeningDirectionPlayed", True, "Marcar introdução como exibida"),
        ]:
            if key in common and common.get(key) != desired:
                changes.append(label)
                if apply:
                    common[key] = desired

        for hero in player.get("heroSaveDatas", []):
            name = HERO_NAMES.get(safe_int(hero.get("heroKey")), hero.get("heroKey"))
            if not bool(hero.get("IsUnLock")):
                changes.append(f"Desbloquear herói: {name}")
                if apply:
                    hero["IsUnLock"] = True
            current_groups = list(hero.get("unlockedAttributeGroupKeys") or [])
            missing = [key for key in KNOWN_ATTRIBUTE_GROUP_KEYS if key not in current_groups]
            if missing:
                changes.append(f"Liberar {len(missing)} grupo(s) de atributos de {name}")
                if apply:
                    hero["unlockedAttributeGroupKeys"] = sorted(set(current_groups + missing))

        locked_pets = [pet for pet in player.get("PetSaveData", []) if isinstance(pet, dict) and not bool(pet.get("IsUnlock"))]
        if locked_pets:
            changes.append(f"Desbloquear {len(locked_pets)} pet(s)")
            if apply:
                for pet in locked_pets:
                    pet["IsUnlock"] = True
                    pet["IsViewed"] = True

        version = str(common.get("version", ""))
        known_recipes = KNOWN_CUBE_RECIPE_MAX_BY_VERSION.get(version, {})
        for recipe in player.get("cubeRecipeSaveDatas", []):
            if not isinstance(recipe, dict):
                continue
            cube_key = safe_int(recipe.get("CubeKey"))
            known_max = known_recipes.get(cube_key)
            if known_max is not None and safe_int(recipe.get("MaxUnlockRecipeKey")) < known_max:
                changes.append(f"Liberar receitas conhecidas do cubo {cube_key}")
                if apply:
                    recipe["MaxUnlockRecipeKey"] = known_max
        return changes

    def apply_campaign_access_unlocks(self) -> int:
        changes = self.campaign_access_changes(apply=False)
        if not changes:
            return 0
        self.campaign_access_changes(apply=True)
        self.mark_dirty(f"Acessos locais da campanha liberados: {len(changes)} ajuste(s).")
        self.refresh_all()
        return len(changes)

    def open_smart_center(self) -> None:
        if not self.data:
            messagebox.showinfo(APP_NAME, "Abra um save primeiro.")
            return
        win = tk.Toplevel(self.root)
        win.title("Inteligência — equipamentos, desbloqueios e Mercado")
        win.configure(bg=THEME["base"])
        self.configure_dialog(win, 1120, 760, resizable=True)
        win.update_idletasks()
        win.minsize(min(980, win.winfo_width()), min(660, win.winfo_height()))
        tk.Label(win, text="CENTRAL DE INTELIGÊNCIA", fg=THEME["text"], bg=THEME["base"], font=(UI_FONT, 14, "bold")).pack(anchor="w", padx=16, pady=(14, 2))
        tk.Label(
            win,
            text="Escolha o que deseja fazer. O assistente primeiro analisa, depois mostra a prévia e só altera o save com sua confirmação.",
            fg=THEME["muted"],
            bg=THEME["base"],
        ).pack(anchor="w", padx=16, pady=(0, 10))
        tabs = ttk.Notebook(win)
        tabs.pack(fill=BOTH, expand=True, padx=14, pady=(0, 10))
        overview = ttk.Frame(tabs, style="Panel.TFrame", padding=14)
        equipment = ttk.Frame(tabs, style="Panel.TFrame", padding=14)
        campaign = ttk.Frame(tabs, style="Panel.TFrame", padding=14)
        market = ttk.Frame(tabs, style="Panel.TFrame", padding=14)
        recycle = ttk.Frame(tabs, style="Panel.TFrame", padding=14)
        coins_tab = ttk.Frame(tabs, style="Panel.TFrame", padding=14)
        protection = ttk.Frame(tabs, style="Panel.TFrame", padding=14)
        tabs.add(overview, text="Começar")
        tabs.add(equipment, text="Equipamentos")
        tabs.add(campaign, text="Desbloqueios")
        tabs.add(market, text="Mercado")
        tabs.add(recycle, text="Reciclagem")
        tabs.add(coins_tab, text="Moedas")
        tabs.add(protection, text="Segurança")

        common = self.data["player"].get("commonSaveData", {})
        issues = self.validate_save()
        errors = sum(issue["severity"] == "ERRO" for issue in issues)
        warnings = sum(issue["severity"] == "AVISO" for issue in issues)
        overview.columnconfigure(0, weight=1, uniform="assistant")
        overview.columnconfigure(1, weight=1, uniform="assistant")
        status_text = (
            f"SAVE: {'pronto' if not errors else 'requer reparo'} ({errors} erro(s), {warnings} aviso(s))"
            f"     •     JOGO: {'aberto — feche antes de salvar' if taskbar_hero_is_running() else 'fechado'}"
            f"     •     ITENS: {len(self.items)}"
        )
        tk.Label(
            overview,
            text=status_text,
            fg=THEME["text"] if not errors else THEME["danger"],
            bg=THEME["card"],
            padx=12,
            pady=6,
            anchor="w",
        ).grid(row=0, column=0, columnspan=2, sticky="ew", padx=6, pady=(2, 7))
        tk.Label(
            overview,
            text="COMO FUNCIONA     1  Escolha uma tarefa     →     2  Confira a análise     →     3  Confirme     →     4  Salve",
            fg=THEME["success"],
            bg=THEME["panel"],
            font=(UI_FONT, 9, "bold"),
        ).grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=(3, 7))

        def action_card(row: int, column: int, title: str, description: str, limitation: str, button: str, command) -> None:
            card = tk.Frame(overview, bg=THEME["card"], bd=1, relief="solid")
            card.grid(row=row, column=column, padx=6, pady=6, sticky="nsew")
            card.columnconfigure(0, weight=1)
            tk.Label(card, text=title, fg=THEME["text"], bg=THEME["card"], font=(UI_FONT, 10, "bold")).grid(row=0, column=0, sticky="w", padx=(12, 6), pady=(8, 3))
            ttk.Button(card, text=button, command=command).grid(row=0, column=1, sticky="e", padx=(5, 10), pady=(6, 3))
            tk.Label(card, text=description, fg=THEME["muted"], bg=THEME["card"], wraplength=430, justify="left").grid(row=1, column=0, columnspan=2, sticky="w", padx=12)
            tk.Label(card, text=f"Seguro: {limitation}", fg=THEME["success"], bg=THEME["card"], wraplength=430, justify="left", font=(UI_FONT, 8)).grid(row=2, column=0, columnspan=2, sticky="w", padx=12, pady=(4, 8))

        action_card(
            2, 0, "Melhorar os heróis",
            "Compara os equipamentos que você já possui e mostra as melhores trocas para cada herói.",
            "não cria itens; você pode substituir uma indicação ou aplicar todas.",
            "Analisar e substituir", lambda: tabs.select(equipment),
        )
        action_card(
            2, 1, "Preparar itens para o Mercado",
            "Localiza itens existentes com melhor chance local e os organiza em uma aba do armazém.",
            "não envia à Steam, não promete preço e não move nada na análise.",
            "Analisar itens", lambda: tabs.select(market),
        )
        action_card(
            3, 0, "Separar duplicados para reciclagem",
            "Encontra equipamentos repetidos de menor prioridade e preserva a melhor cópia.",
            "não apaga nem converte itens; a reciclagem continua sendo feita no jogo.",
            "Encontrar duplicados", lambda: tabs.select(recycle),
        )
        action_card(
            3, 1, "Liberar recursos locais",
            "Mostra tutoriais, heróis, pets, atributos e receitas conhecidas que ainda estão bloqueados.",
            "não inventa fases e não altera progresso do servidor.",
            "Ver desbloqueios", lambda: tabs.select(campaign),
        )
        coin_total = len(self.commemorative_coin_rows())
        action_card(
            4, 0, "Moedas comemorativas",
            f"Reúne as {coin_total} moeda(s) de aniversário espalhadas pelo save numa página do armazém, ou cria moedas novas direto nele."
            if coin_total else "Organize moedas de aniversário existentes ou crie moedas novas direto no armazém.",
            "juntar só move o que já existe; criar gera itens novos, sempre com sua confirmação.",
            "Ver moedas", lambda: tabs.select(coins_tab),
        )
        ttk.Button(overview, text="Verificar a segurança do save", command=self.open_validation_dialog).grid(row=4, column=1, sticky="e", padx=6, pady=(9, 2))
        tk.Label(
            overview,
            text="Nada é gravado até você clicar em Salvar alterações.",
            fg=THEME["muted"],
            bg=THEME["panel"],
        ).grid(row=5, column=0, columnspan=2, sticky="w", padx=6, pady=(9, 2))

        tk.Label(equipment, text="ANALISAR EQUIPAMENTOS E ENCANTAMENTOS", fg=THEME["text"], bg=THEME["panel"], font=(UI_FONT, 11, "bold")).pack(anchor="w")
        tk.Label(
            equipment,
            text="Compare o item equipado com a melhor opção disponível. A nota combina raridade, nível conhecido, afinidade, tiers e ocupação dos encantamentos.",
            fg=THEME["muted"], bg=THEME["panel"], wraplength=1020, justify="left",
        ).pack(anchor="w", pady=(5, 8))
        equipment_heroes = [hero for hero in self.data["player"].get("heroSaveDatas", []) if isinstance(hero, dict)]
        equipment_hero_labels = [HERO_NAMES.get(safe_int(hero.get("heroKey")), f"Herói {hero.get('heroKey')}") for hero in equipment_heroes]
        initial_hero_label = equipment_hero_labels[0] if equipment_hero_labels else "Nenhum herói"
        if self.selected_hero in equipment_heroes:
            initial_hero_label = HERO_NAMES.get(safe_int(self.selected_hero.get("heroKey")), initial_hero_label)
        equipment_hero_var = StringVar(value=initial_hero_label)
        equipment_summary_var = StringVar(value="")
        equipment_bar = ttk.Frame(equipment, style="Panel.TFrame")
        equipment_bar.pack(fill=X)
        ttk.Label(equipment_bar, text="Herói").pack(side=LEFT)
        equipment_hero_combo = ttk.Combobox(equipment_bar, textvariable=equipment_hero_var, values=equipment_hero_labels, state="readonly", width=20)
        equipment_hero_combo.pack(side=LEFT, padx=(6, 12))
        ttk.Label(equipment_bar, textvariable=equipment_summary_var).pack(side=LEFT, padx=8)
        equipment_tree = ttk.Treeview(
            equipment,
            columns=("slot", "current", "current_enchants", "recommended", "recommended_enchants", "origin"),
            show="headings",
            height=5,
        )
        for key, label, width in [
            ("slot", "Espaço", 105), ("current", "Equipado", 135), ("current_enchants", "Encantamentos atuais", 165),
            ("recommended", "Indicação", 135), ("recommended_enchants", "Encantamentos indicados", 165), ("origin", "Origem", 125),
        ]:
            equipment_tree.heading(key, text=label)
            equipment_tree.column(key, width=width, minwidth=80, anchor="w")
        self.attach_scrollbars(equipment, equipment_tree).pack(fill=BOTH, expand=True, pady=8)
        equipment_plans: dict[str, dict] = {}

        def equipment_selected_hero() -> dict | None:
            try:
                return equipment_heroes[equipment_hero_labels.index(equipment_hero_var.get())]
            except (ValueError, IndexError):
                return None

        def analyze_equipment() -> None:
            equipment_tree.delete(*equipment_tree.get_children())
            equipment_plans.clear()
            if any(issue["severity"] == "ERRO" for issue in self.validate_save()):
                equipment_summary_var.set("O save possui erros. Use Validar e reparar antes de substituir.")
                equipment_selected_button.configure(state="disabled")
                equipment_all_button.configure(state="disabled")
                return
            hero = equipment_selected_hero()
            if hero is None:
                equipment_summary_var.set("Nenhum herói disponível.")
                equipment_selected_button.configure(state="disabled")
                equipment_all_button.configure(state="disabled")
                return
            plans = self.build_auto_equip_plan(hero)
            for plan in plans:
                current = plan.get("current")
                replacement = plan["replacement"]
                iid = equipment_tree.insert(
                    "", END,
                    values=(
                        SLOT_NAMES.get(plan["slot_index"], "ESPAÇO"),
                        self.item_name(current),
                        self.enchant_quality_label(current, hero),
                        self.item_name(replacement),
                        self.enchant_quality_label(replacement, hero),
                        self.storage_label(plan["source"], plan["source_slot"]),
                    ),
                )
                equipment_plans[iid] = plan
            equipment_summary_var.set(
                f"{len(plans)} melhoria(s) encontrada(s)." if plans else "Este herói já usa os melhores itens locais encontrados."
            )
            equipment_selected_button.configure(state="disabled")
            equipment_all_button.configure(state="normal" if plans else "disabled")

        def apply_equipment_rows(plans: list[dict]) -> None:
            hero = equipment_selected_hero()
            if hero is None or not plans:
                return
            hero_name = HERO_NAMES.get(safe_int(hero.get("heroKey")), "Herói")
            if not messagebox.askyesno(
                APP_NAME,
                f"Substituir {len(plans)} equipamento(s) de {hero_name} pelas indicações?\n\nOs itens atuais voltarão para os espaços de origem. A gravação só ocorre ao usar Salvar alterações.",
            ):
                return
            applied = self.apply_auto_equip_plan(hero, plans)
            if applied != len(plans):
                messagebox.showerror(APP_NAME, "A origem de algum item mudou. Analise novamente.")
                analyze_equipment()
                return
            self.selected_item = plans[-1]["replacement"]
            self.mark_dirty(f"{hero_name}: {applied} equipamento(s) substituído(s) pela indicação.")
            self.refresh_all()
            analyze_equipment()
            messagebox.showinfo(APP_NAME, f"Substituições preparadas: {applied}.\nUse Salvar alterações para gravar.")

        def apply_selected_equipment() -> None:
            selected = equipment_tree.selection()
            if selected and selected[0] in equipment_plans:
                apply_equipment_rows([equipment_plans[selected[0]]])

        def optimize_every_hero() -> None:
            win.destroy()
            self.open_auto_equip_all_preview()

        equipment_actions = ttk.Frame(equipment, style="Panel.TFrame")
        equipment_actions.pack(fill=X)
        ttk.Button(equipment_actions, text="Analisar novamente", command=analyze_equipment).pack(side=LEFT)
        equipment_selected_button = ttk.Button(equipment_actions, text="Substituir selecionado", command=apply_selected_equipment, state="disabled")
        equipment_selected_button.pack(side=LEFT, padx=6)
        ttk.Button(equipment_actions, text="Otimizar todos os heróis de uma vez", command=optimize_every_hero).pack(side=LEFT, padx=6)
        equipment_all_button = ttk.Button(equipment_actions, text="Substituir todas as indicações", style="Accent.TButton", command=lambda: apply_equipment_rows(list(equipment_plans.values())), state="disabled")
        equipment_all_button.pack(side=RIGHT)
        equipment_tree.bind("<<TreeviewSelect>>", lambda _event: equipment_selected_button.configure(state="normal" if equipment_tree.selection() else "disabled"))
        equipment_tree.bind("<Double-Button-1>", lambda _event: apply_selected_equipment())
        equipment_hero_combo.bind("<<ComboboxSelected>>", lambda _event: analyze_equipment())
        analyze_equipment()

        tk.Label(campaign, text="LIBERAR RECURSOS LOCAIS", fg=THEME["text"], bg=THEME["panel"], font=(UI_FONT, 11, "bold")).pack(anchor="w")
        tk.Label(
            campaign,
            text=(
                f"Progresso atual: fase {stage_label(common.get('currentStageKey'))}, onda {common.get('currentStageWave', 0)} · "
                f"maior concluída {stage_label(common.get('maxCompletedStage'))}.\n\n"
                "A ação abaixo libera apenas tutoriais, heróis, pets, grupos de atributos e receitas já conhecidas pela versão do save. "
                "Ela não inventa fases acima do conteúdo conhecido e não altera progresso de servidor."
            ),
            fg=THEME["muted"],
            bg=THEME["panel"],
            wraplength=1020,
            justify="left",
        ).pack(anchor="w", pady=(8, 14))
        campaign_changes = self.campaign_access_changes(apply=False)
        campaign_tree = ttk.Treeview(campaign, columns=("change",), show="headings", height=5)
        campaign_tree.heading("change", text="Alterações disponíveis")
        campaign_tree.column("change", width=820, anchor="w")
        for change in campaign_changes:
            campaign_tree.insert("", END, values=(change,))
        if not campaign_changes:
            campaign_tree.insert("", END, values=("Todos os acessos locais conhecidos já estão liberados.",))
        self.attach_scrollbars(campaign, campaign_tree).pack(fill=BOTH, expand=True, pady=8)

        def apply_campaign() -> None:
            changes = self.campaign_access_changes(apply=False)
            if not changes:
                messagebox.showinfo(APP_NAME, "Todos os acessos locais conhecidos já estão liberados.")
                return
            preview = "\n".join(f"• {change}" for change in changes[:12])
            if len(changes) > 12:
                preview += f"\n• ... e mais {len(changes) - 12} ajuste(s)"
            if not messagebox.askyesno(APP_NAME, f"Aplicar estes ajustes?\n\n{preview}\n\nO progresso de fase não será elevado."):
                return
            count = self.apply_campaign_access_unlocks()
            messagebox.showinfo(APP_NAME, f"Acessos liberados: {count} ajuste(s).\nUse Salvar alterações para gravar.")
            campaign_tree.delete(*campaign_tree.get_children())
            campaign_tree.insert("", END, values=("Todos os acessos locais conhecidos já estão liberados.",))
            campaign_apply.configure(state="disabled")

        campaign_apply = ttk.Button(
            campaign,
            text="Confirmar e preparar desbloqueios",
            style="Accent.TButton",
            command=apply_campaign,
            state="normal" if campaign_changes else "disabled",
        )
        campaign_apply.pack(anchor="e", pady=6)

        unlocked_pages = [page for page in range(1, STASH_PAGE_COUNT + 1) if self.stash_page_is_unlocked(page)]
        default_queue_page = f"Armazém {unlocked_pages[-1]}" if unlocked_pages else STASH_DISPLAY_TARGETS[0]
        market_page_var = StringVar(value=default_queue_page)
        market_count_var = StringVar(value=str(self.configured_market_slots()))
        market_summary_var = StringVar(value="Clique em Analisar; nada será movido sem confirmação.")
        market_rows: list[dict] = []
        tk.Label(market, text="PREPARAR ITENS PARA O MERCADO", fg=THEME["text"], bg=THEME["panel"], font=(UI_FONT, 11, "bold")).pack(anchor="w", pady=(0, 4))
        tk.Label(
            market,
            text="1. Escolha a aba.  2. Preencha com candidatos existentes.  3. Confira e organize. Itens desejados criados pelo editor ficam separados para uso local.",
            fg=THEME["success"], bg=THEME["panel"], wraplength=1020, justify="left",
        ).pack(anchor="w", pady=(0, 9))
        market_bar = ttk.Frame(market, style="Panel.TFrame")
        market_bar.pack(fill=X)
        ttk.Label(market_bar, text="Destino").pack(side=LEFT)
        ttk.Combobox(market_bar, textvariable=market_page_var, values=STASH_DISPLAY_TARGETS, state="readonly", width=15).pack(side=LEFT, padx=(6, 14))
        ttk.Label(market_bar, text="Slots nesta rodada").pack(side=LEFT)
        ttk.Spinbox(market_bar, from_=1, to=max(1, self.configured_market_slots()), textvariable=market_count_var, width=6).pack(side=LEFT, padx=6)
        ttk.Button(market_bar, text="Avisos oficiais", command=lambda: webbrowser.open(MARKET_OFFICIAL_NEWS_URL)).pack(side=RIGHT)
        ship = self.trade_ship_status()
        tk.Label(
            market,
            text=f"NAVIO DE TROCAS — {ship.reason}.",
            fg=THEME["success"] if ship.unlocked and ship.known else THEME["warning"],
            bg=THEME["panel"],
            wraplength=1020,
            justify="left",
        ).pack(anchor="w", pady=(6, 2))
        tk.Label(
            market,
            text=policy_summary(compact=True),
            fg=THEME["muted"],
            bg=THEME["panel"],
            wraplength=1020,
            justify="left",
        ).pack(anchor="w", pady=(0, 8))
        market_tree = ttk.Treeview(market, columns=("name", "rarity", "type", "origin", "status"), show="headings", height=4)
        for key, label, width in [
            ("name", "Item", 250), ("rarity", "Raridade", 100), ("type", "Tipo", 100),
            ("origin", "Origem", 185), ("status", "Análise local", 385),
        ]:
            market_tree.heading(key, text=label)
            market_tree.column(key, width=width, anchor="w")
        self.attach_scrollbars(market, market_tree).pack(fill=BOTH, expand=True, pady=6)
        ttk.Label(market, textvariable=market_summary_var).pack(anchor="w", pady=4)
        market_actions = ttk.Frame(market, style="Panel.TFrame")
        market_actions.pack(fill=X)

        def selected_page(var: StringVar) -> int:
            return max(1, min(STASH_PAGE_COUNT, safe_int(normalize_search_text(var.get()).rsplit(" ", 1)[-1], 1)))

        def analyze_market() -> None:
            page = selected_page(market_page_var)
            market_rows.clear()
            market_rows.extend(self.market_candidates(page, max(1, safe_int(market_count_var.get(), 20))))
            market_tree.delete(*market_tree.get_children())
            for row in market_rows:
                item = row["item"]
                market_tree.insert(
                    "", END,
                    values=(self.item_name(item), rarity_label(self.item_rarity(item)), item_type_label(self.item_db(item).get("Type")), self.storage_label(row["source"], row["source_slot"]), row["reason"]),
                )
            market_summary_var.set(self.queue_summary_text(page, len(market_rows), self.last_market_pool, "pré-candidato"))
            market_apply.configure(state="normal" if market_rows else "disabled")

        def fill_market_page() -> None:
            page = selected_page(market_page_var)
            capacity = self.market_round_capacity(page)
            if not capacity:
                messagebox.showinfo(APP_NAME, self.page_block_reason(page))
                return
            market_count_var.set(str(capacity))
            analyze_market()

        def add_desired_market_items() -> None:
            page = selected_page(market_page_var)
            if not self.free_slot_count(f"Armazem {page}"):
                messagebox.showinfo(APP_NAME, self.page_block_reason(page))
                return
            self.open_create_item_dialog(f"Armazem {page}", local_market_notice=True)

        def apply_market() -> None:
            page = selected_page(market_page_var)
            if not market_rows:
                return
            if not messagebox.askyesno(
                APP_NAME,
                f"Mover {len(market_rows)} item(ns) para o Armazém {page}?\n\nIsso apenas organiza o save local. A Steam decidirá a elegibilidade no Navio de Trocas.",
            ):
                return
            applied = self.apply_storage_queue(market_rows, page)
            if applied != len(market_rows):
                messagebox.showerror(APP_NAME, "O armazém mudou após a análise. Analise novamente.")
                return
            self.mark_dirty(f"Armazém {page}: {applied} pré-candidato(s) de Mercado organizados.")
            self.refresh_all()
            messagebox.showinfo(APP_NAME, f"Organização concluída: {applied} item(ns).\nA confirmação final deve ser feita dentro do jogo.")
            analyze_market()

        ttk.Button(market_actions, text="Analisar limite", command=analyze_market).pack(side=LEFT)
        ttk.Button(market_actions, text="Preencher com existentes", command=fill_market_page).pack(side=LEFT, padx=5)
        ttk.Button(market_actions, text="Criar desejados (modo desprotegido)", command=add_desired_market_items).pack(side=LEFT)
        market_apply = ttk.Button(market_actions, text="2. Confirmar e organizar", style="Accent.TButton", command=apply_market, state="disabled")
        market_apply.pack(side=RIGHT)

        # A fila de reciclagem usa a penúltima página liberada para não disputar
        # o mesmo destino da fila de Mercado quando as duas são preparadas.
        recycle_default_page = f"Armazém {unlocked_pages[-2]}" if len(unlocked_pages) > 1 else default_queue_page
        recycle_page_var = StringVar(value=recycle_default_page)
        # Moedas usa a antepenúltima página pelo mesmo motivo: evitar que a página
        # sugerida por padrão dispute espaço com Mercado ou Reciclagem quando as
        # três abas são preparadas na mesma sessão.
        coin_default_page = f"Armazém {unlocked_pages[-3]}" if len(unlocked_pages) > 2 else recycle_default_page
        recycle_limit_var = StringVar(value="50")
        recycle_rarity_var = StringVar(value=RARITY_LABELS["LEGENDARY"])
        recycle_summary_var = StringVar(value="A fila nunca apaga nem converte itens automaticamente.")
        recycle_rows: list[dict] = []
        tk.Label(recycle, text="SEPARAR DUPLICADOS PARA RECICLAGEM", fg=THEME["text"], bg=THEME["panel"], font=(UI_FONT, 11, "bold")).pack(anchor="w", pady=(0, 4))
        tk.Label(
            recycle,
            text="1. Escolha os limites e analise.  2. Confira os duplicados.  3. Organize a fila. A conversão continua sendo feita no Cubo do jogo.",
            fg=THEME["success"], bg=THEME["panel"], wraplength=1020, justify="left",
        ).pack(anchor="w", pady=(0, 9))
        recycle_bar = ttk.Frame(recycle, style="Panel.TFrame")
        recycle_bar.pack(fill=X)
        ttk.Label(recycle_bar, text="Destino da fila").pack(side=LEFT)
        ttk.Combobox(recycle_bar, textvariable=recycle_page_var, values=STASH_DISPLAY_TARGETS, state="readonly", width=15).pack(side=LEFT, padx=(6, 14))
        ttk.Label(recycle_bar, text="Raridade máxima").pack(side=LEFT)
        recycle_rarity_values = [RARITY_LABELS[key] for key in ("COMMON", "UNCOMMON", "RARE", "LEGENDARY", "IMMORTAL")]
        ttk.Combobox(recycle_bar, textvariable=recycle_rarity_var, values=recycle_rarity_values, state="readonly", width=15).pack(side=LEFT, padx=(6, 14))
        ttk.Label(recycle_bar, text="Limite").pack(side=LEFT)
        ttk.Spinbox(recycle_bar, from_=1, to=66, textvariable=recycle_limit_var, width=6).pack(side=LEFT, padx=6)
        tk.Label(
            recycle,
            text=(
                "A análise seleciona somente equipamentos duplicados, preserva a melhor cópia, ignora itens bloqueados/caóticos e exclui tudo que foi criado ou alterado na sessão. "
                "A síntese real deve ser feita manualmente no Cubo do jogo; o editor não promete transformar itens em valor de Mercado."
            ),
            fg=THEME["muted"],
            bg=THEME["panel"],
            wraplength=1020,
            justify="left",
        ).pack(anchor="w", pady=10)
        recycle_tree = ttk.Treeview(recycle, columns=("name", "rarity", "origin", "reason"), show="headings", height=4)
        for key, label, width in [("name", "Item duplicado", 260), ("rarity", "Raridade", 100), ("origin", "Origem", 215), ("reason", "Motivo", 380)]:
            recycle_tree.heading(key, text=label)
            recycle_tree.column(key, width=width, anchor="w")
        self.attach_scrollbars(recycle, recycle_tree).pack(fill=BOTH, expand=True, pady=6)
        ttk.Label(recycle, textvariable=recycle_summary_var).pack(anchor="w", pady=4)
        recycle_actions = ttk.Frame(recycle, style="Panel.TFrame")
        recycle_actions.pack(fill=X)

        def analyze_recycle() -> None:
            max_rarity = RARITY_FROM_LABEL.get(recycle_rarity_var.get(), "LEGENDARY")
            recycle_rows.clear()
            recycle_rows.extend(self.recycle_candidates(selected_page(recycle_page_var), max(1, safe_int(recycle_limit_var.get(), 50)), max_rarity))
            recycle_tree.delete(*recycle_tree.get_children())
            for row in recycle_rows:
                item = row["item"]
                recycle_tree.insert("", END, values=(self.item_name(item), rarity_label(self.item_rarity(item)), self.storage_label(row["source"], row["source_slot"]), row["reason"]))
            recycle_summary_var.set(self.queue_summary_text(
                selected_page(recycle_page_var), len(recycle_rows), self.last_recycle_pool, "duplicado"))
            recycle_apply.configure(state="normal" if recycle_rows else "disabled")

        def apply_recycle() -> None:
            page = selected_page(recycle_page_var)
            if not recycle_rows:
                return
            if not messagebox.askyesno(APP_NAME, f"Mover {len(recycle_rows)} item(ns) para a fila no Armazém {page}?\n\nNenhum item será excluído ou convertido."):
                return
            applied = self.apply_storage_queue(recycle_rows, page)
            if applied != len(recycle_rows):
                messagebox.showerror(APP_NAME, "O armazém mudou após a análise. Analise novamente.")
                return
            self.mark_dirty(f"Fila de reciclagem preparada: {applied} item(ns) no Armazém {page}.")
            self.refresh_all()
            messagebox.showinfo(APP_NAME, f"Fila preparada: {applied} item(ns).\nRecicle manualmente no Cubo do jogo.")
            analyze_recycle()

        ttk.Button(recycle_actions, text="1. Analisar sem mover", command=analyze_recycle).pack(side=LEFT)
        recycle_apply = ttk.Button(recycle_actions, text="2. Confirmar e organizar", style="Accent.TButton", command=apply_recycle, state="disabled")
        recycle_apply.pack(side=RIGHT)

        # ------------------------------------------------------------------
        # Moedas comemorativas (Anniversary Coins 160001-160010)
        # ------------------------------------------------------------------
        coins_body = self.scrollable_area(coins_tab)
        coin_page_var = StringVar(value=coin_default_page)
        coin_summary_var = StringVar(value="Clique em Localizar; nada é movido sem confirmação.")
        coin_plan_holder: dict[str, object] = {"plan": None}
        tk.Label(coins_body, text="JUNTAR MOEDAS COMEMORATIVAS", fg=THEME["text"], bg=THEME["panel"], font=(UI_FONT, 11, "bold")).pack(anchor="w", pady=(0, 4))
        tk.Label(
            coins_body,
            text="1. Escolha a página de destino.  2. Localize as moedas.  3. Confirme para juntá-las. O editor só move o que já existe.",
            fg=THEME["success"], bg=THEME["panel"], wraplength=1020, justify="left",
        ).pack(anchor="w", pady=(0, 9))
        coin_bar = ttk.Frame(coins_body, style="Panel.TFrame")
        coin_bar.pack(fill=X)
        ttk.Label(coin_bar, text="Reunir em").pack(side=LEFT)
        ttk.Combobox(coin_bar, textvariable=coin_page_var, values=STASH_DISPLAY_TARGETS, state="readonly", width=15).pack(side=LEFT, padx=(6, 14))
        tk.Label(
            coins_body,
            text=f"{coins.USAGE_NOTICE} {coins.MARKET_NOTICE}",
            fg=THEME["muted"], bg=THEME["panel"], wraplength=1020, justify="left",
        ).pack(anchor="w", pady=(8, 4))
        coin_tree = ttk.Treeview(coins_body, columns=("coin", "rarity", "quantity", "where"), show="headings", height=4)
        for key, label, width in [
            ("coin", "Moeda", 425), ("rarity", "Raridade", 105),
            ("quantity", "Quantidade", 95), ("where", "Onde está", 320),
        ]:
            coin_tree.heading(key, text=label)
            coin_tree.column(key, width=width, anchor="w")
        self.attach_scrollbars(coins_body, coin_tree).pack(fill=X, pady=(6, 2))
        ttk.Label(coins_body, textvariable=coin_summary_var).pack(anchor="w", pady=(2, 4))
        coin_actions = ttk.Frame(coins_body, style="Panel.TFrame")
        coin_actions.pack(fill=X)

        def analyze_coins() -> None:
            page = selected_page(coin_page_var)
            coin_tree.delete(*coin_tree.get_children())
            for group in self.commemorative_coin_groups():
                coin_tree.insert(
                    "", END,
                    values=(
                        f"{group.definition.display_name} — {group.definition.name}",
                        rarity_label(group.definition.rarity),
                        group.count,
                        ", ".join(group.locations) or "sem local",
                    ),
                )
            plan = self.build_commemorative_coin_plan(page)
            coin_plan_holder["plan"] = plan
            coin_summary_var.set(plan.summary())
            coin_apply.configure(state="normal" if plan.rows_to_apply else "disabled")

        def apply_coins() -> None:
            plan = coin_plan_holder.get("plan")
            if plan is None or not plan.rows_to_apply:
                return
            page = plan.stash_page
            if not messagebox.askyesno(
                APP_NAME,
                f"Mover {plan.moving} moeda(s) comemorativa(s) para o Armazém {page}?\n\n"
                "Nenhuma moeda é criada, consumida ou convertida: elas apenas mudam de espaço no save.",
            ):
                return
            applied = self.apply_storage_queue(list(plan.rows_to_apply), page)
            if applied != plan.moving:
                messagebox.showerror(APP_NAME, "O armazém mudou após a análise. Localize novamente.")
                analyze_coins()
                return
            self.mark_dirty(f"Armazém {page}: {applied} moeda(s) comemorativa(s) reunidas.")
            self.refresh_all()
            analyze_coins()
            messagebox.showinfo(
                APP_NAME,
                f"{applied} moeda(s) reunidas no Armazém {page}.\nUse Salvar alterações para gravar.",
            )

        ttk.Button(coin_actions, text="1. Localizar moedas", command=analyze_coins).pack(side=LEFT)
        coin_apply = ttk.Button(coin_actions, text="2. Confirmar e juntar", style="Accent.TButton", command=apply_coins, state="disabled")
        coin_apply.pack(side=RIGHT)
        analyze_coins()

        # ------------------------------------------------------------------
        # Adicionar moedas comemorativas ao armazém (cria itens novos)
        # ------------------------------------------------------------------
        ttk.Separator(coins_body, orient="horizontal").pack(fill=X, pady=(10, 8))
        coin_choice_labels = [
            f"{definition.display_name} ({rarity_label(definition.rarity)})"
            for definition in coins.COIN_DEFINITIONS
        ]
        coin_choice_by_label = dict(zip(coin_choice_labels, coins.COIN_DEFINITIONS))
        coin_add_choice_var = StringVar(value=coin_choice_labels[0])
        coin_add_quantity_var = StringVar(value="1")
        coin_add_page_var = StringVar(value=coin_default_page)
        tk.Label(coins_body, text="ADICIONAR MOEDA AO ARMAZÉM", fg=THEME["text"], bg=THEME["panel"], font=(UI_FONT, 11, "bold")).pack(anchor="w", pady=(0, 2))
        tk.Label(
            coins_body,
            text="Cria cópias novas da moeda escolhida direto no armazém. Diferente de juntar, esta ação cria itens — sempre com sua confirmação.",
            fg=THEME["warning"], bg=THEME["panel"], wraplength=1020, justify="left",
        ).pack(anchor="w", pady=(0, 6))
        coin_add_bar = ttk.Frame(coins_body, style="Panel.TFrame")
        coin_add_bar.pack(fill=X)
        ttk.Label(coin_add_bar, text="Moeda").pack(side=LEFT)
        ttk.Combobox(coin_add_bar, textvariable=coin_add_choice_var, values=coin_choice_labels, state="readonly", width=34).pack(side=LEFT, padx=(6, 14))
        ttk.Label(coin_add_bar, text="Quantidade").pack(side=LEFT)
        ttk.Spinbox(coin_add_bar, from_=1, to=999, textvariable=coin_add_quantity_var, width=6).pack(side=LEFT, padx=(6, 14))
        ttk.Label(coin_add_bar, text="Armazém").pack(side=LEFT)
        ttk.Combobox(coin_add_bar, textvariable=coin_add_page_var, values=STASH_DISPLAY_TARGETS, state="readonly", width=15).pack(side=LEFT, padx=(6, 14))

        def add_coin() -> None:
            definition = coin_choice_by_label.get(coin_add_choice_var.get())
            if definition is None:
                return
            if not self.db_by_key.get(str(definition.item_key)):
                messagebox.showinfo(APP_NAME, "Atualize o catálogo de itens primeiro.")
                return
            quantity = max(1, safe_int(coin_add_quantity_var.get(), 1))
            page = selected_page(coin_add_page_var)
            if not messagebox.askyesno(
                APP_NAME,
                f"Criar {quantity} moeda(s) \"{definition.display_name}\" no Armazém {page}?\n\n"
                "Itens criados pelo editor ficam isolados das filas de Mercado nesta sessão.",
            ):
                return
            if self.create_item(definition.item_key, quantity, f"Armazem {page}", enchanted=False):
                analyze_coins()

        coin_add_actions = ttk.Frame(coins_body, style="Panel.TFrame")
        coin_add_actions.pack(fill=X, pady=(6, 0))
        ttk.Button(coin_add_actions, text="Adicionar ao armazém", style="Accent.TButton", command=add_coin).pack(side=RIGHT)

        protection_rows = [
            ("Modo Protegido", "Ativo" if self.protected_mode_enabled() else "Desativado", "bloqueia jogo aberto, criação, duplicação e operações de maior risco"),
            ("Identidade Steam", "Protegida", "ownerSteamId e playerId não são editáveis"),
            ("Gravação", "Atômica + backup", "validação acontece antes da substituição"),
            ("Mercado", "Somente pré-análise", "não automatiza Steam, não altera elegibilidade e não oculta mudanças"),
            ("Navio de Trocas", "Liberado" if ship.unlocked and ship.known else ("Desconhecido" if not ship.known else "Bloqueado"), ship.short_reason),
            ("Itens da sessão", "Isolados", "criados ou alterados não entram nas filas inteligentes"),
            ("Anti-banimento", "Não existe garantia", "o modo reduz erros; não burla detecção nem regras"),
        ]
        protection_tree = ttk.Treeview(protection, columns=("control", "status", "detail"), show="headings", height=6)
        for key, label, width in [("control", "Controle", 195), ("status", "Estado", 150), ("detail", "O que faz", 605)]:
            protection_tree.heading(key, text=label)
            protection_tree.column(key, width=width, anchor="w")
        for row in protection_rows:
            protection_tree.insert("", END, values=row)
        self.attach_scrollbars(protection, protection_tree).pack(fill=BOTH, expand=True)
        tk.Label(
            protection,
            text="Importante: editar saves de um jogo conectado pode contrariar regras do jogo e resultar em sanções. O caminho mais seguro para Mercado e progressão é usar somente as funções oficiais dentro do jogo.",
            fg=THEME["warning"],
            bg=THEME["panel"],
            wraplength=1020,
            justify="left",
        ).pack(anchor="w", pady=14)
        ttk.Button(protection, text="Abrir avisos oficiais do TBH", command=lambda: webbrowser.open(MARKET_OFFICIAL_NEWS_URL)).pack(anchor="e")

        buttons = ttk.Frame(win, style="Top.TFrame", padding=(12, 6))
        buttons.pack(side="bottom", fill=X, before=tabs)
        ttk.Button(buttons, text="Fechar", command=win.destroy).pack(side=RIGHT)
        win.bind("<Escape>", lambda _event: win.destroy())
        win.grab_set()

    def uid_location_labels(self, uid: int) -> list[str]:
        if not self.data or not uid:
            return []
        player = self.data["player"]
        labels: list[str] = []
        for hero in player.get("heroSaveDatas", []):
            hname = HERO_NAMES.get(safe_int(hero.get("heroKey")), f"Herói {hero.get('heroKey')}")
            for index, equipped_uid in enumerate(hero.get("equippedItemIds", [])):
                if safe_int(equipped_uid) == uid:
                    labels.append(f"{hname} {SLOT_NAMES.get(index, 'SLOT')}")
        for source, label in [
            ("inventorySaveDatas", "Inventário"),
            ("stashSaveDatas", "Armazém"),
            ("remakeTradingStashSaveDatas", "Trocas"),
        ]:
            for slot in player.get(source, []):
                if safe_int(slot.get("ItemUniqueId")) == uid:
                    index = safe_int(slot.get("Index"))
                    if source == "stashSaveDatas":
                        page = self.stash_page_for_index(index)
                        labels.append(f"Armazém {page} - espaço {self.stash_local_slot(index)}")
                    else:
                        labels.append(f"{label} - espaço {index + 1}")
        return labels

    def remove_uid_from_locations(self, uid: int, include_heroes: bool = True) -> int:
        if not self.data:
            return 0
        player = self.data["player"]
        changed = 0
        if include_heroes:
            for hero in player.get("heroSaveDatas", []):
                ids = hero.get("equippedItemIds", [])
                for index, equipped_uid in enumerate(ids):
                    if safe_int(equipped_uid) == uid:
                        ids[index] = 0
                        changed += 1
        for source in ("inventorySaveDatas", "stashSaveDatas", "remakeTradingStashSaveDatas"):
            for slot in player.get(source, []):
                if safe_int(slot.get("ItemUniqueId")) == uid:
                    slot["ItemUniqueId"] = 0
                    changed += 1
        return changed

    def open_equip_dialog(self, hero: dict | None, slot_index: int) -> None:
        if not hero or not self.data:
            return
        win = tk.Toplevel(self.root)
        hname = HERO_NAMES.get(safe_int(hero.get("heroKey")), f"Herói {hero.get('heroKey')}")
        win.title(f"Equipar {hname} - {SLOT_NAMES.get(slot_index, 'SLOT')}")
        win.configure(bg=THEME["base"])
        self.configure_dialog(win, 900, 560, resizable=True)
        query_var = StringVar(value="")
        rarity_var = StringVar(value=RARITY_FILTER_ALL)
        result_var = StringVar(value="")
        bar = ttk.Frame(win, style="Panel.TFrame", padding=8)
        bar.pack(fill=X)
        ttk.Label(bar, text="Buscar").pack(side=LEFT)
        search = ttk.Entry(bar, textvariable=query_var)
        search.pack(side=LEFT, fill=X, expand=True, padx=8)
        rarity_combo = ttk.Combobox(bar, textvariable=rarity_var, values=RARITY_FILTER_VALUES, state="readonly", width=18)
        rarity_combo.pack(side=LEFT, padx=(0, 8))
        ttk.Label(bar, textvariable=result_var).pack(side=RIGHT)
        columns = ("key", "name", "rarity", "location", "uid")
        tree = ttk.Treeview(win, columns=columns, show="tree headings", height=18)
        tree.heading("#0", text="")
        tree.column("#0", width=44, minwidth=44, stretch=False, anchor="center")
        for col, label, width in [
            ("key", "Código", 90), ("name", "Nome oficial", 270), ("rarity", "Raridade", 100),
            ("location", "Origem", 300), ("uid", "ID único", 120),
        ]:
            tree.heading(col, text=label)
            tree.column(col, width=width, anchor="w")

        def refresh() -> None:
            tree.delete(*tree.get_children())
            query = query_var.get().strip()
            rows = []
            for item in self.items:
                if not self.item_compatible_with_slot(item, hero, slot_index):
                    continue
                db_item = dict(self.item_db(item))
                db_item["SearchExtras"] = " ".join(self.uid_location_labels(safe_int(item.get("UniqueId"))))
                if not item_matches_filters(db_item, query, rarity_var.get(), ITEM_TYPE_LABELS["GEAR"]):
                    continue
                values = (
                    item.get("ItemKey", ""), self.item_name(item), rarity_label(self.item_rarity(item)),
                    ", ".join(self.uid_location_labels(safe_int(item.get("UniqueId")))) or "Sem local",
                    item.get("UniqueId", ""),
                )
                rows.append((self.item_rarity(item), self.item_name(item), values))
            for db_item in self.db:
                candidate = {"ItemKey": safe_int(db_item.get("ItemKey"))}
                if not self.item_compatible_with_slot(candidate, hero, slot_index):
                    continue
                if not item_matches_filters(db_item, query, rarity_var.get(), ITEM_TYPE_LABELS["GEAR"]):
                    continue
                has_enchant_slots = RARITY_ENCHANT_SLOT_COUNT.get(str(db_item.get("Rarity", "")).upper(), 0) > 0
                values = (
                    db_item.get("ItemKey", ""), db_item.get("Name", ""), rarity_label(db_item.get("Rarity", "")),
                    "Criar novo com T30" if has_enchant_slots else "Criar novo sem encantamento", "",
                )
                rows.append((str(db_item.get("Rarity", "")), str(db_item.get("Name", "")), values))
            rarity_order = {name: index for index, name in enumerate(["COMMON", "UNCOMMON", "RARE", "LEGENDARY", "IMMORTAL", "ARCANA", "BEYOND", "CELESTIAL", "DIVINE", "COSMIC"])}
            rows.sort(key=lambda row: (-rarity_order.get(row[0], -1), row[1]))
            result_var.set(f"{len(rows)} opção(ões)" + (" · mostrando 400" if len(rows) > 400 else ""))
            for _rarity, _name, values in rows[:400]:
                tree.insert("", END, values=values, image=self.get_icon_by_key(str(values[0])) or "")

        def equip() -> None:
            selected = tree.selection()
            if not selected:
                messagebox.showinfo(APP_NAME, "Selecione um item.")
                return
            uid = safe_int(tree.item(selected[0], "values")[4])
            item = self.items_by_uid.get(uid)
            created_new = False
            if item is None:
                key = safe_int(tree.item(selected[0], "values")[0])
                db_item = self.db_by_key.get(str(key), {})
                enchanted = RARITY_ENCHANT_SLOT_COUNT.get(str(db_item.get("Rarity", "")).upper(), 0) > 0
                item = self.new_item(key, enchanted=enchanted)
                self.data["player"].setdefault("itemSaveDatas", []).append(item)
                self.items.append(item)
                self.items_by_uid[safe_int(item.get("UniqueId"))] = item
                self.flag_item_created(item)
                created_new = True
            if item and self.equip_item(hero, slot_index, item):
                win.destroy()
            elif created_new:
                self.session_created_uids.discard(safe_int(item.get("UniqueId")))
                self.data["player"]["itemSaveDatas"].remove(item)
                self.items.remove(item)
                self.rebuild_item_index()

        buttons = ttk.Frame(win, style="Panel.TFrame", padding=8)
        buttons.pack(side="bottom", fill=X)
        ttk.Button(buttons, text="Cancelar", command=win.destroy).pack(side=LEFT)
        ttk.Button(buttons, text="Desequipar", command=lambda: self.unequip_slot(hero, slot_index) and win.destroy()).pack(side=LEFT, padx=6)
        ttk.Button(buttons, text="Equipar", style="Accent.TButton", command=equip).pack(side=RIGHT)
        self.attach_scrollbars(win, tree).pack(fill=BOTH, expand=True, padx=10, pady=10)
        search.bind("<KeyRelease>", lambda _e: refresh())
        rarity_combo.bind("<<ComboboxSelected>>", lambda _e: refresh())
        tree.bind("<Double-Button-1>", lambda _e: equip())
        refresh()
        win.bind("<Escape>", lambda _event: win.destroy())
        win.grab_set()
        search.focus_set()

    def equip_item(self, hero: dict, slot_index: int, item: dict) -> bool:
        if not self.item_compatible_with_slot(item, hero, slot_index):
            messagebox.showerror(APP_NAME, "Esse item não é compatível com o espaço selecionado.")
            return False
        ids = hero.setdefault("equippedItemIds", [])
        while len(ids) < 10:
            ids.append(0)
        new_uid = safe_int(item.get("UniqueId"))
        old_uid = safe_int(ids[slot_index])
        if old_uid == new_uid:
            return True
        selected_in_inventory = any(
            safe_int(slot.get("ItemUniqueId")) == new_uid
            for slot in self.data["player"].get("inventorySaveDatas", [])
        )
        if old_uid and self.free_slot_count("Automatico") + int(selected_in_inventory) < 1:
            messagebox.showerror(APP_NAME, "Não há espaço no Inventário nem no Armazém para guardar o item substituído.")
            return False
        self.remove_uid_from_locations(new_uid, include_heroes=True)
        ids = hero.setdefault("equippedItemIds", [0] * 10)
        while len(ids) < 10:
            ids.append(0)
        ids[slot_index] = new_uid
        if old_uid and old_uid in self.items_by_uid and not self.uid_location_labels(old_uid):
            self.place_item(old_uid, "Automatico")
        self.selected_hero = hero
        self.selected_item = item
        self.mark_dirty(f"{self.item_name(item)} equipado em {SLOT_NAMES.get(slot_index, 'SLOT')}.")
        self.refresh_all()
        return True

    def unequip_slot(self, hero: dict, slot_index: int) -> bool:
        ids = hero.setdefault("equippedItemIds", [])
        while len(ids) < 10:
            ids.append(0)
        uid = safe_int(ids[slot_index])
        if not uid:
            return True
        if self.free_slot_count("Automatico") < 1:
            messagebox.showerror(APP_NAME, "Não há espaço no Inventário nem no Armazém.")
            return False
        ids[slot_index] = 0
        self.place_item(uid, "Automatico")
        self.mark_dirty(f"Item de {SLOT_NAMES.get(slot_index, 'SLOT')} desequipado.")
        self.refresh_all()
        return True

    def open_slot_picker_for_item(self, item: dict) -> None:
        if not self.data:
            return
        win = tk.Toplevel(self.root)
        win.title(f"Equipar {self.item_name(item)}")
        win.configure(bg=THEME["base"])
        self.configure_dialog(win, 680, 520, resizable=True)
        header = tk.Frame(win, bg=THEME["base"], height=44)
        header.pack(fill=X, padx=10, pady=(8, 0))
        header.pack_propagate(False)
        header_icon = tk.Label(header, image=self.get_icon(item) or "", bg=THEME["base"], width=38)
        header_icon.pack(side=LEFT, padx=(0, 7))
        tk.Label(header, text=self.item_name(item), fg=THEME["text"], bg=THEME["base"], font=(UI_FONT, 10, "bold"), anchor="w").pack(side=LEFT, fill=X, expand=True)
        tree = ttk.Treeview(win, columns=("hero", "slot", "current"), show="tree headings", height=16)
        tree.heading("#0", text="")
        tree.column("#0", width=44, minwidth=44, stretch=False, anchor="center")
        for col, label, width in [("hero", "Herói", 160), ("slot", "Espaço", 210), ("current", "Item atual", 260)]:
            tree.heading(col, text=label)
            tree.column(col, width=width, anchor="w")
        targets: dict[str, tuple[dict, int]] = {}

        def refresh() -> None:
            header_icon.configure(image=self.get_icon(item) or "")
            tree.delete(*tree.get_children())
            targets.clear()
            for target_hero in self.data["player"].get("heroSaveDatas", []):
                for index in range(10):
                    if not self.item_compatible_with_slot(item, target_hero, index):
                        continue
                    ids = target_hero.get("equippedItemIds", [])
                    current = self.items_by_uid.get(safe_int(ids[index])) if index < len(ids) else None
                    iid = tree.insert(
                        "",
                        END,
                        values=(HERO_NAMES.get(target_hero.get("heroKey"), target_hero.get("heroKey")), SLOT_NAMES[index], self.item_name(current)),
                        image=(self.get_icon(current) or "") if current else "",
                    )
                    targets[iid] = (target_hero, index)
        self.attach_scrollbars(win, tree).pack(fill=BOTH, expand=True, padx=10, pady=10)

        def apply() -> None:
            selected = tree.selection()
            if selected and self.equip_item(*targets[selected[0]], item):
                win.destroy()

        ttk.Button(win, text="Cancelar", command=win.destroy).pack(side=LEFT, padx=10, pady=10)
        ttk.Button(win, text="Equipar", style="Accent.TButton", command=apply).pack(side=RIGHT, padx=10, pady=10)
        tree.bind("<Double-Button-1>", lambda _e: apply())
        self.register_icon_refresher(win, refresh)
        refresh()
        win.bind("<Escape>", lambda _event: win.destroy())
        win.grab_set()

    def equip_selected_item(self) -> None:
        if not self.selected_item:
            messagebox.showinfo(APP_NAME, "Selecione um item primeiro.")
            return
        self.open_slot_picker_for_item(self.selected_item)

    def move_item(self, item: dict, target: str) -> bool:
        uid = safe_int(item.get("UniqueId"))
        current_slots = [
            (source, slot)
            for source in ("inventorySaveDatas", "stashSaveDatas", "remakeTradingStashSaveDatas")
            for slot in self.data["player"].get(source, [])
            if safe_int(slot.get("ItemUniqueId")) == uid
        ]
        target_slots = self.slots_for_destination(target)
        if any(any(source == target_source and slot is target_slot for target_source, target_slot in target_slots) for source, slot in current_slots):
            self.status_var.set(f"{self.item_name(item)} já está em {destination_label(target)}.")
            return True
        if self.free_slot_count(target) < 1:
            messagebox.showerror(APP_NAME, f"Não há espaço livre em {destination_label(target)}.")
            return False
        self.remove_uid_from_locations(uid, include_heroes=True)
        slot = self.place_item(uid, target)
        if slot < 0:
            return False
        self.mark_dirty(f"{self.item_name(item)} movido para {destination_label(target)} · espaço {slot}.")
        self.refresh_all()
        return True

    def open_move_dialog(self, item: dict) -> None:
        win = tk.Toplevel(self.root)
        win.title("Mover item")
        win.configure(bg=THEME["base"])
        win.resizable(False, False)
        icon_label = tk.Label(win, bg=THEME["base"], width=38, height=38)
        icon_label.pack(padx=20, pady=(16, 3))

        def refresh_icon() -> None:
            icon_label.configure(image=self.get_icon(item) or "")

        refresh_icon()
        self.register_icon_refresher(win, refresh_icon)
        tk.Label(win, text=self.item_name(item), fg=THEME["text"], bg=THEME["base"], font=(UI_FONT, 10, "bold")).pack(padx=20, pady=(3, 10))
        target_var = StringVar(value=DESTINATION_LABELS["Inventario"])
        # tk.Label com bg explícito: o fundo do Toplevel é "base", e um ttk.Label
        # (fundo "panel") recortaria um retângulo mais claro no meio do diálogo.
        tk.Label(win, text="Destino", fg=THEME["muted"], bg=THEME["base"]).pack(anchor="w", padx=20)
        ttk.Combobox(
            win,
            textvariable=target_var,
            values=[DESTINATION_LABELS["Inventario"], *STASH_DISPLAY_TARGETS],
            state="readonly",
            width=24,
        ).pack(fill=X, padx=20, pady=(3, 8))
        ttk.Button(
            win,
            text="Mover",
            style="Accent.TButton",
            command=lambda: (self.move_item(item, destination_value(target_var.get())) and win.destroy()),
        ).pack(fill=X, padx=20, pady=5)
        ttk.Button(win, text="Cancelar", command=win.destroy).pack(padx=20, pady=(8, 18))
        self.configure_dialog(win, 360, 320)
        win.bind("<Escape>", lambda _event: win.destroy())
        win.grab_set()

    def move_selected_item(self) -> None:
        if not self.selected_item:
            messagebox.showinfo(APP_NAME, "Selecione um item primeiro.")
            return
        self.open_move_dialog(self.selected_item)

    def delete_item(self, item: dict) -> bool:
        uid = safe_int(item.get("UniqueId"))
        locations = self.uid_location_labels(uid)
        detail = f"\nLocais: {', '.join(locations)}" if locations else ""
        if not messagebox.askyesno(APP_NAME, f"Excluir definitivamente {self.item_name(item)}?{detail}"):
            return False
        self.remove_uid_from_locations(uid, include_heroes=True)
        records = self.data["player"].get("itemSaveDatas", [])
        self.data["player"]["itemSaveDatas"] = [record for record in records if record is not item]
        self.items = [record for record in self.items if record is not item]
        self.rebuild_item_index()
        if self.selected_item is item:
            self.selected_item = None
        self.mark_dirty(f"Item {uid} excluído.")
        self.refresh_all()
        return True
 
    def material_choices(self) -> list[str]:
        return self.material_choice_cache

    def auto_place_unlocated_items(self) -> None:
        if not self.data:
            messagebox.showinfo(APP_NAME, "Abra um save primeiro.")
            return
        located: set[int] = set()
        player = self.data["player"]
        for hero in player.get("heroSaveDatas", []):
            located.update(safe_int(uid) for uid in hero.get("equippedItemIds", []) if safe_int(uid))
        for source in ("inventorySaveDatas", "stashSaveDatas", "remakeTradingStashSaveDatas"):
            located.update(safe_int(slot.get("ItemUniqueId")) for slot in player.get(source, []) if safe_int(slot.get("ItemUniqueId")))
        unlocated = [item for item in self.items if safe_int(item.get("UniqueId")) not in located]
        if not unlocated:
            messagebox.showinfo(APP_NAME, "Todos os itens já possuem um local.")
            return
        available = self.free_slot_count("Automatico")
        if available < len(unlocated):
            if not messagebox.askyesno(
                APP_NAME,
                f"Há {len(unlocated)} item(ns) sem local, mas apenas {available} espaço(s) livre(s) no Inventário e nas 7 páginas do armazém.\n\nAlocar o que couber?",
            ):
                return
        placed = 0
        distribution: dict[str, int] = {}
        for item in unlocated:
            uid = safe_int(item.get("UniqueId"))
            if self.place_item(uid, "Automatico") < 0:
                break
            placed += 1
            location = next(iter(self.uid_location_labels(uid)), "Automatico")
            area = location.split(" - espaço", 1)[0]
            distribution[area] = distribution.get(area, 0) + 1
        if placed:
            self.mark_dirty(f"{placed} item(ns) sem local alocado(s) automaticamente.")
            self.refresh_all()
        breakdown = "\n".join(f"{area}: {count}" for area, count in distribution.items())
        messagebox.showinfo(
            APP_NAME,
            f"Alocação automática concluída.\nItens alocados: {placed}\nSem espaço: {len(unlocated) - placed}"
            + (f"\n\nDestinos:\n{breakdown}" if breakdown else "")
            + "\n\nUse Salvar alterações para gravar no arquivo.",
        )

    def item_locations(self) -> list[tuple[str, dict | None]]:
        if not self.data:
            return []
        player = self.data["player"]
        rows: list[tuple[str, dict | None]] = []
        for hero in player.get("heroSaveDatas", []):
            hname = HERO_NAMES.get(safe_int(hero.get("heroKey")), f"Herói {hero.get('heroKey')}")
            for idx, uid in enumerate(hero.get("equippedItemIds", [])):
                rows.append((f"{hname} {SLOT_NAMES.get(idx, 'SLOT')}", self.items_by_uid.get(safe_int(uid), None) if uid else None))
        for source, label in [
            ("inventorySaveDatas", "Inventário"),
            ("stashSaveDatas", "Armazém"),
            ("remakeTradingStashSaveDatas", "Trocas"),
        ]:
            for slot in player.get(source, []):
                uid = safe_int(slot.get("ItemUniqueId"))
                index = safe_int(slot.get("Index"))
                if source == "stashSaveDatas":
                    page = self.stash_page_for_index(index)
                    where = f"Armazém {page} - espaço {self.stash_local_slot(index)}"
                else:
                    where = f"{label} - espaço {index + 1}"
                rows.append((where, self.items_by_uid.get(uid) if uid else None))
        return rows
 
    def schedule_table_refresh(self) -> None:
        if self.table_refresh_job is not None:
            try:
                self.root.after_cancel(self.table_refresh_job)
            except tk.TclError:
                pass
        self.table_refresh_job = self.root.after(160, self.refresh_tables)

    def refresh_tables(self) -> None:
        self.table_refresh_job = None
        if not self.data:
            return
        query = self.filter_var.get().strip()
        rarity_filter = self.rarity_filter_var.get()
        type_filter = self.type_filter_var.get()
        for name in ["inventory", "stash", "trading", "all"]:
            tree: ttk.Treeview = getattr(self, f"{name}_tree")
            tree.delete(*tree.get_children())

        row_index = {"inventory": 0, "stash": 0, "trading": 0, "all": 0}

        def add(tree_name: str, where: str, item: dict | None) -> None:
            if self.only_non_empty.get() and not item:
                return
            db = self.item_db(item)
            values = (
                where,
                item.get("ItemKey", "") if item else "",
                self.item_name(item),
                rarity_label(db.get("Rarity", "")) if item else "",
                item.get("UniqueId", "") if item else "",
            )
            searchable = dict(db)
            searchable["SearchExtras"] = f"{where} {item.get('UniqueId', '') if item else ''}"
            if not item_matches_filters(searchable, query, rarity_filter, type_filter):
                return
            tree = getattr(self, f"{tree_name}_tree")
            index = row_index[tree_name]
            tree.insert(
                "",
                END,
                values=values,
                image=(self.get_icon(item) or "") if item else "",
                tags=(("even" if index % 2 == 0 else "odd"),),
            )
            row_index[tree_name] += 1

        player = self.data["player"]
        for slot in player.get("inventorySaveDatas", []):
            uid = safe_int(slot.get("ItemUniqueId"))
            add("inventory", f"Inventário - espaço {safe_int(slot.get('Index')) + 1}", self.items_by_uid.get(uid) if uid else None)
        selected_page = self.stash_page_var.get()
        for slot in player.get("stashSaveDatas", []):
            index = safe_int(slot.get("Index"))
            page = self.stash_page_for_index(index)
            if page > STASH_PAGE_COUNT:
                continue
            if selected_page != "Todas as páginas" and selected_page != f"Armazém {page}":
                continue
            uid = safe_int(slot.get("ItemUniqueId"))
            add("stash", f"Armazém {page} - espaço {self.stash_local_slot(index)}", self.items_by_uid.get(uid) if uid else None)
        for slot in player.get("remakeTradingStashSaveDatas", []):
            uid = safe_int(slot.get("ItemUniqueId"))
            add("trading", f"Trocas - espaço {safe_int(slot.get('Index')) + 1}", self.items_by_uid.get(uid) if uid else None)
        for item in self.items:
            uid = safe_int(item.get("UniqueId"))
            locations = self.uid_location_labels(uid)
            add("all", ", ".join(locations) if locations else "Sem local", item)
        for name, count in row_index.items():
            result_var = getattr(self, f"{name}_result_var", None)
            if result_var is not None:
                result_var.set(f"{count} item" if count == 1 else f"{count} itens")
 
    def select_from_tree(self, tree: ttk.Treeview) -> None:
        selected = tree.selection()
        if not selected:
            return
        current_tab = self.notebook.select()
        uid = tree.item(selected[0], "values")[4]
        if uid:
            self.select_item(self.items_by_uid.get(safe_int(uid)))
        if current_tab:
            self.notebook.select(current_tab)
 
    def move_table_selection(self, tree: ttk.Treeview, delta: int) -> None:
        rows = list(tree.get_children())
        if not rows:
            return
        current_tab = self.notebook.select()
        selected = tree.selection()
        if selected and selected[0] in rows:
            index = rows.index(selected[0])
            next_index = max(0, min(len(rows) - 1, index + delta))
        else:
            next_index = 0 if delta >= 0 else len(rows) - 1
        target = rows[next_index]
        tree.selection_set(target)
        tree.focus(target)
        tree.see(target)
        uid = tree.item(target, "values")[4]
        if uid:
            self.select_item(self.items_by_uid.get(safe_int(uid)))
        if current_tab:
            self.notebook.select(current_tab)
 
    def item_from_tree(self, tree: ttk.Treeview) -> dict | None:
        selected = tree.selection()
        if not selected:
            messagebox.showinfo(APP_NAME, "Selecione um item na tabela primeiro.")
            return None
        uid = tree.item(selected[0], "values")[4]
        if not uid:
            messagebox.showinfo(APP_NAME, "Esse espaço está vazio.")
            return None
        return self.items_by_uid.get(safe_int(uid))
 
    def open_selected_table_enchants(self, tree: ttk.Treeview) -> None:
        item = self.item_from_tree(tree)
        if not item:
            return
        if not (self.expected_enchant_slot_count(item) or 0):
            db = self.item_db(item)
            messagebox.showinfo(
                APP_NAME,
                "Materiais não recebem encantamentos."
                if str(db.get("Type", "")).upper() != "GEAR"
                else "A raridade deste equipamento não possui espaços de encantamento.",
            )
            return
        self.select_item(item)
        self.notebook.select(self.enchant_tab)
 
    def edit_selected_table_item(self, tree: ttk.Treeview) -> None:
        item = self.item_from_tree(tree)
        if not item:
            return
        self.open_item_editor(item)

    def duplicate_selected_table_item(self, tree: ttk.Treeview) -> None:
        item = self.item_from_tree(tree)
        if not item:
            return
        self.duplicate_item(item, self.ask_quantity("Duplicar item", "Quantas cópias deseja criar?", 1))

    def move_selected_table_item(self, tree: ttk.Treeview) -> None:
        item = self.item_from_tree(tree)
        if item:
            self.open_move_dialog(item)

    def equip_selected_table_item(self, tree: ttk.Treeview) -> None:
        item = self.item_from_tree(tree)
        if item:
            self.open_slot_picker_for_item(item)

    def delete_selected_table_item(self, tree: ttk.Treeview) -> None:
        item = self.item_from_tree(tree)
        if item:
            self.delete_item(item)

    def item_choices(self) -> list[str]:
        return self.item_choice_cache

    def item_choice_for_key(self, item_key: int) -> str:
        db = self.db_by_key.get(str(item_key), {})
        if not db:
            return str(item_key)
        return f"{item_key} | {rarity_label(db.get('Rarity', ''))} | {db.get('Name', '')}"

    def open_create_item_dialog(self, initial_target: str = "Automatico", local_market_notice: bool = False) -> None:
        if self.data is None:
            messagebox.showinfo(APP_NAME, "Abra um save primeiro.")
            return
        if not self.db:
            messagebox.showinfo(APP_NAME, "Atualize o catálogo de itens primeiro.")
            return

        win = tk.Toplevel(self.root)
        win.title("Adicionar item desejado — uso local" if local_market_notice else "Criar item")
        win.configure(bg=THEME["base"])
        self.configure_dialog(win, 900, 580, resizable=True)
        win.minsize(820, 520)

        query_var = StringVar(value="")
        rarity_var = StringVar(value=RARITY_FILTER_ALL)
        type_var = StringVar(value=ITEM_TYPE_LABELS["GEAR"])
        if initial_target not in DESTINATION_LABELS:
            initial_target = "Automatico"
        target_var = StringVar(value=DESTINATION_LABELS[initial_target])
        quantity_var = StringVar(value="1")
        enchant_var = BooleanVar(value=False)
        result_var = StringVar(value="")
        refresh_job: list[str | None] = [None]

        bar = ttk.Frame(win, style="Panel.TFrame", padding=12)
        bar.pack(fill=X)
        ttk.Label(bar, text="Buscar por nome ou código").grid(row=0, column=0, sticky="w")
        search = ttk.Entry(bar, textvariable=query_var)
        search.grid(row=0, column=1, columnspan=5, sticky="ew", padx=(8, 12))
        ttk.Label(bar, textvariable=result_var).grid(row=0, column=6, columnspan=2, sticky="e")

        ttk.Label(bar, text="Raridade").grid(row=1, column=0, sticky="w", pady=(10, 0))
        rarity_combo = ttk.Combobox(bar, textvariable=rarity_var, values=RARITY_FILTER_VALUES, state="readonly", width=18)
        rarity_combo.grid(row=1, column=1, sticky="ew", padx=(8, 12), pady=(10, 0))
        ttk.Label(bar, text="Tipo").grid(row=1, column=2, sticky="w", pady=(10, 0))
        type_combo = ttk.Combobox(bar, textvariable=type_var, values=TYPE_FILTER_VALUES, state="readonly", width=16)
        type_combo.grid(row=1, column=3, sticky="ew", padx=(8, 12), pady=(10, 0))
        ttk.Label(bar, text="Destino").grid(row=1, column=4, sticky="w", pady=(10, 0))
        target_values = [DESTINATION_LABELS[initial_target]] if local_market_notice else DESTINATION_VALUES
        ttk.Combobox(bar, textvariable=target_var, values=target_values, state="readonly", width=16).grid(
            row=1, column=5, sticky="ew", padx=(8, 12), pady=(10, 0)
        )
        ttk.Label(bar, text="Quantidade").grid(row=1, column=6, sticky="w", pady=(10, 0))
        ttk.Spinbox(bar, from_=1, to=999, textvariable=quantity_var, width=7).grid(row=1, column=7, sticky="w", padx=(8, 0), pady=(10, 0))

        enchant_check = ttk.Checkbutton(bar, text="Criar com encantamentos T30 compatíveis", variable=enchant_var, state="disabled")
        enchant_check.grid(row=2, column=0, columnspan=4, sticky="w", pady=(10, 0))
        ttk.Label(bar, text="Disponível apenas para equipamentos com espaços de encantamento.").grid(
            row=2, column=4, columnspan=4, sticky="e", pady=(10, 0)
        )
        if local_market_notice:
            tk.Label(
                bar,
                text="USO LOCAL: itens criados pelo editor não são candidatos confiáveis ao Mercado e podem ser recusados pelo jogo/Steam.",
                fg=THEME["warning"], bg=THEME["panel"], justify="left", wraplength=1020,
            ).grid(row=3, column=0, columnspan=8, sticky="w", pady=(10, 0))
        bar.columnconfigure(1, weight=1)
        bar.columnconfigure(3, weight=1)
        bar.columnconfigure(5, weight=1)

        columns = ("key", "name", "rarity", "type", "stats")
        tree = ttk.Treeview(win, columns=columns, show="tree headings", height=12)
        tree.heading("#0", text="")
        tree.column("#0", width=44, minwidth=44, stretch=False, anchor="center")
        for col, text, width in [
            ("key", "Código", 75),
            ("name", "Nome oficial", 235),
            ("rarity", "Raridade", 95),
            ("type", "Tipo", 105),
            ("stats", "Atributos possíveis", 280),
        ]:
            tree.heading(col, text=text)
            tree.column(col, width=width, anchor="w")

        def filtered_rows() -> list[dict]:
            rows = [item for item in self.db if item_matches_filters(item, query_var.get(), rarity_var.get(), type_var.get())]
            rows.sort(key=lambda row: (-RARITY_RANK.get(str(row.get("Rarity", "")).upper(), 0), normalize_search_text(row.get("Name"))))
            return rows

        def localized_stats(item: dict) -> str:
            labels = []
            for raw_stat in item.get("StatTypes") or []:
                stat_id = STAT_NAME_TO_TYPE.get(str(raw_stat))
                labels.append(STAT_TYPES.get(stat_id, str(raw_stat)))
            return ", ".join(labels) if labels else "—"

        def refresh() -> None:
            refresh_job[0] = None
            tree.delete(*tree.get_children())
            rows = filtered_rows()
            visible_rows = rows[:300]
            for item in visible_rows:
                values = (
                    item.get("ItemKey", ""),
                    item.get("Name", ""),
                    rarity_label(item.get("Rarity", "")),
                    item_type_label(item.get("Type", "")),
                    localized_stats(item),
                )
                tree.insert("", END, values=values, image=self.get_icon_by_key(str(item.get("ItemKey"))) or "")
            suffix = f" · mostrando {len(visible_rows)}" if len(rows) > len(visible_rows) else ""
            result_var.set(f"{len(rows)} encontrado(s){suffix}")
            enchant_var.set(False)
            enchant_check.configure(state="disabled")

        def schedule_refresh(_event=None) -> None:
            if refresh_job[0] is not None:
                try:
                    win.after_cancel(refresh_job[0])
                except tk.TclError:
                    pass
            refresh_job[0] = win.after(150, refresh)

        def update_selected_actions(_event=None) -> None:
            selected = tree.selection()
            if not selected:
                enchant_var.set(False)
                enchant_check.configure(state="disabled")
                return
            key = safe_int(tree.item(selected[0], "values")[0])
            db_item = self.db_by_key.get(str(key), {})
            applicable = str(db_item.get("Type", "")).upper() == "GEAR" and RARITY_ENCHANT_SLOT_COUNT.get(
                str(db_item.get("Rarity", "")).upper(), 0
            ) > 0
            enchant_var.set(False)
            enchant_check.configure(state="normal" if applicable else "disabled")

        def create_selected() -> None:
            selected = tree.selection()
            if not selected:
                messagebox.showinfo(APP_NAME, "Selecione um item na lista.")
                return
            key = safe_int(tree.item(selected[0], "values")[0])
            quantity = max(1, safe_int(quantity_var.get(), 1))
            if local_market_notice and not messagebox.askyesno(
                APP_NAME,
                "Adicionar estes itens ao armazém para uso local?\n\nEles serão marcados como criados nesta sessão e ficarão fora da análise de candidatos ao Mercado.",
            ):
                return
            created = self.create_item(key, quantity, destination_value(target_var.get()), enchant_var.get())
            if created:
                win.destroy()

        buttons = ttk.Frame(win, style="Panel.TFrame", padding=8)
        buttons.pack(side="bottom", fill=X)
        ttk.Button(buttons, text="Cancelar", command=win.destroy).pack(side=LEFT)
        ttk.Button(buttons, text="Adicionar para uso local" if local_market_notice else "Criar", style="Accent.TButton", command=create_selected).pack(side=RIGHT)
        self.attach_scrollbars(win, tree).pack(fill=BOTH, expand=True, padx=10, pady=10)

        search.bind("<KeyRelease>", schedule_refresh)
        rarity_combo.bind("<<ComboboxSelected>>", schedule_refresh)
        type_combo.bind("<<ComboboxSelected>>", schedule_refresh)
        tree.bind("<<TreeviewSelect>>", update_selected_actions)
        tree.bind("<Double-Button-1>", lambda _e: create_selected())
        win.bind("<Escape>", lambda _event: win.destroy())
        win.grab_set()
        refresh()
        search.focus_set()

    def create_item(self, item_key: int, quantity: int = 1, target: str = "Inventario", enchanted: bool = True) -> list[dict]:
        if self.data is None:
            messagebox.showinfo(APP_NAME, "Abra um save primeiro.")
            return []
        if str(item_key) not in self.db_by_key:
            messagebox.showerror(APP_NAME, f"Código de item não encontrado: {item_key}")
            return []
        quantity = max(1, quantity)
        if self.protected_mode_enabled() and quantity > PROTECTED_BATCH_LIMIT:
            messagebox.showerror(
                APP_NAME,
                f"O Modo Protegido limita a criação a {PROTECTED_BATCH_LIMIT} itens por operação.\n"
                "Desative-o conscientemente para usar um lote maior.",
            )
            return []
        available = self.free_slot_count(target)
        if available < quantity:
            messagebox.showerror(APP_NAME, f"{destination_label(target)} tem apenas {available} espaço(s) livre(s).")
            return []
        created: list[dict] = []
        last_slot = 0
        for _ in range(max(1, quantity)):
            item = self.new_item(item_key, enchanted)
            self.data["player"].setdefault("itemSaveDatas", []).append(item)
            self.items.append(item)
            self.items_by_uid[safe_int(item.get("UniqueId"))] = item
            self.flag_item_created(item)
            last_slot = self.place_item(safe_int(item.get("UniqueId")), target)
            created.append(item)
        self.selected_item = created[-1]
        self.mark_dirty(f"{len(created)} item(ns) criado(s) em {destination_label(target)}. Último espaço: #{last_slot}")
        self.refresh_all()
        messagebox.showinfo(APP_NAME, f"{len(created)} item(ns) criado(s) em {destination_label(target)}.")
        return created

    def new_item(self, item_key: int, enchanted: bool = True) -> dict:
        template = {
            "ItemKey": 0,
            "UniqueId": 0,
            "PrevUniqueId": 0,
            "IsChaotic": False,
            "IsBlocked": False,
            "EnchantCount": [0, 0, 0],
            "EnchantData": [],
            "ItemGetSourceType": 0,
            "DecorationAppliedTotalCount": 0,
            "EngravingAppliedTotalCount": 0,
            "InscriptionAppliedTotalCount": 0,
        }
        template["ItemKey"] = int(item_key)
        template["UniqueId"] = self.next_unique_id()
        template["IsChaotic"] = False
        template["IsBlocked"] = False
        is_gear = str(self.db_by_key.get(str(item_key), {}).get("Type")) == "GEAR"
        slot_count = self.expected_enchant_slot_count(template) or 0
        if enchanted and is_gear and slot_count:
            template["EnchantData"] = self.default_enchants_for_item_key(item_key)
            counts = [min(2, max(0, slot_count - group * 2)) for group in range(3)]
            template["EnchantCount"] = counts
            template["DecorationAppliedTotalCount"] = counts[0]
            template["EngravingAppliedTotalCount"] = counts[1]
            template["InscriptionAppliedTotalCount"] = counts[2]
        else:
            template["EnchantData"] = [self.empty_enchant() for _ in range(slot_count)]
            template["EnchantCount"] = [0, 0, 0]
            template["DecorationAppliedTotalCount"] = 0
            template["EngravingAppliedTotalCount"] = 0
            template["InscriptionAppliedTotalCount"] = 0
        return template

    def default_enchants_for_item_key(self, item_key: int) -> list[dict]:
        db = self.db_by_key.get(str(item_key), {})
        slot_count = RARITY_ENCHANT_SLOT_COUNT.get(str(db.get("Rarity", "")).upper(), 0)
        if slot_count == 0:
            return []
        stats = list(self.db_by_key.get(str(item_key), {}).get("StatTypes") or [])
        if not stats:
            stats = ["AttackDamage", "AttackSpeed", "CriticalDamage", "CooldownReduction", "MaxHp", "Armor"]
        expanded: list[str] = []
        while len(expanded) < slot_count:
            expanded.extend(stats)
        values = {
            "AttackDamage": 9999,
            "AttackSpeed": 999,
            "MaxHp": 999999,
            "HpRegenPerSec": 9999,
            "Armor": 9999,
            "MovementSpeed": 999,
            "CastSpeed": 999,
            "CriticalDamage": 9999,
            "CooldownReduction": 999,
            "CriticalChance": 999,
            "BlockChance": 999,
            "DodgeChance": 999,
            "DamageReduction": 999,
            "DamageAbsorption": 999,
            "HpLeech": 999,
            "AddHpPerHit": 9999,
            "AddHpPerKill": 9999,
            "AreaOfEffect": 999,
        }
        materials = [119001, 190003, 144002, 124004, 143002, 143001]
        recipe_types = ENCHANT_RECIPE_TYPES[slot_count]
        rows = []
        for index, stat in enumerate(expanded[:slot_count]):
            stat_type = STAT_NAME_TO_TYPE.get(stat, 0)
            rows.append(
                {
                    "StatModKey": STAT_TYPE_TO_MOD.get(stat_type, 0),
                    "Tier": 30,
                    "Value": values.get(stat, 999),
                    "RecipeType": recipe_types[index],
                    "ModType": 0,
                    "MaterialKey": materials[index],
                    "StatType": stat_type,
                    "EnchantVersion": None,
                }
            )
        return rows
 
    def open_item_editor(self, item: dict) -> None:
        win = tk.Toplevel(self.root)
        win.title(f"Editar item {item.get('UniqueId')}")
        win.configure(bg=THEME["base"])
        self.configure_dialog(win, 1040, 520, resizable=True)
        win.minsize(900, 480)
 
        preview = tk.Frame(win, bg=THEME["card"], bd=1, relief="solid")
        preview.grid(row=0, column=0, columnspan=2, sticky="ew", padx=14, pady=(14, 10))
        preview.columnconfigure(1, weight=1)
        icon_label = tk.Label(preview, bg=THEME["card"], width=72, height=72)
        icon_label.grid(row=0, column=0, rowspan=4, padx=12, pady=10)
        name_label = tk.Label(preview, text="", fg=THEME["text"], bg=THEME["card"], font=(UI_FONT, 12, "bold"))
        name_label.grid(row=0, column=1, sticky="w", padx=8, pady=(10, 0))
        meta_label = tk.Label(preview, text="", fg=THEME["muted"], bg=THEME["card"], font=(UI_FONT, 9))
        meta_label.grid(row=1, column=1, sticky="w", padx=8)
        stats_label = tk.Label(preview, text="", fg=THEME["text"], bg=THEME["card"], font=(UI_FONT, 9), wraplength=650, justify="left")
        stats_label.grid(row=2, column=1, sticky="w", padx=8, pady=(4, 10))

        edit_query_var = StringVar(value="")
        edit_rarity_var = StringVar(value=RARITY_FILTER_ALL)
        edit_type_var = StringVar(value=TYPE_FILTER_ALL)
        edit_result_var = StringVar(value="")
        selector = ttk.Frame(win, style="Panel.TFrame", padding=10)
        selector.grid(row=1, column=0, columnspan=2, sticky="ew", padx=14, pady=(0, 8))
        ttk.Label(selector, text="Filtrar catálogo").grid(row=0, column=0, sticky="w")
        edit_search = ttk.Entry(selector, textvariable=edit_query_var)
        edit_search.grid(row=0, column=1, sticky="ew", padx=(8, 10))
        edit_rarity_combo = ttk.Combobox(selector, textvariable=edit_rarity_var, values=RARITY_FILTER_VALUES, state="readonly", width=18)
        edit_rarity_combo.grid(row=0, column=2, padx=(0, 8))
        edit_type_combo = ttk.Combobox(selector, textvariable=edit_type_var, values=TYPE_FILTER_VALUES, state="readonly", width=16)
        edit_type_combo.grid(row=0, column=3, padx=(0, 8))
        ttk.Label(selector, textvariable=edit_result_var).grid(row=0, column=4, sticky="e")
        selector.columnconfigure(1, weight=1)
 
        fields: list[tuple[str, object, list[str] | None]] = [
            ("ItemKey", item.get("ItemKey", 0), [self.item_choice_for_key(safe_int(item.get("ItemKey")))]),
            ("UniqueId", item.get("UniqueId", 0), None),
            ("IsChaotic", item.get("IsChaotic", False), ["Não", "Sim"]),
            ("IsBlocked", item.get("IsBlocked", False), ["Não", "Sim"]),
        ]
        vars_by_key: dict[str, StringVar] = {}
        item_key_combo: list[ttk.Combobox | None] = [None]
 
        def update_preview(*_args) -> None:
            key = normalize_choice(vars_by_key.get("ItemKey", StringVar(value=str(item.get("ItemKey")))).get())
            db = self.db_by_key.get(str(key), {})
            name = db.get("Name", f"Item {key}")
            rarity = db.get("Rarity", "")
            item_type = db.get("Type", "")
            stat_types = ", ".join(
                STAT_TYPES.get(STAT_NAME_TO_TYPE.get(str(raw)), str(raw)) for raw in db.get("StatTypes", [])
            ) if db.get("StatTypes") else "sem atributos no catálogo"
            name_label.configure(text=str(name))
            meta_label.configure(text=f"Código {key}  ·  {rarity_label(rarity)}  ·  {item_type_label(item_type)}")
            stats_label.configure(text=f"Atributos possíveis: {stat_types}")
            icon = self.get_icon_by_key(str(key))
            if icon:
                icon_label.configure(image=icon, text="")
                icon_label.image = icon
            else:
                icon_label.configure(image="", text="sem ícone", fg=THEME["muted2"], font=(UI_FONT, 9), width=10, height=4)
                icon_label.image = None

        field_labels = {
            "ItemKey": "Item do catálogo",
            "UniqueId": "ID único",
            "IsChaotic": "Item caótico",
            "IsBlocked": "Item bloqueado",
        }
        for row, (key, value, choices) in enumerate(fields, start=2):
            tk.Label(win, text=field_labels.get(key, key), fg=THEME["muted"], bg=THEME["base"]).grid(row=row, column=0, sticky="w", padx=14, pady=6)
            display = str(value)
            if key == "ItemKey":
                display = self.item_choice_for_key(safe_int(value))
            elif key in {"IsChaotic", "IsBlocked"}:
                display = "Sim" if bool(value) else "Não"
            var = StringVar(value=display)
            vars_by_key[key] = var
            if choices:
                state = "readonly" if key.startswith("Is") or key == "ItemKey" else "normal"
                combo = ttk.Combobox(win, textvariable=var, values=choices, state=state)
                combo.grid(row=row, column=1, sticky="ew", padx=10, pady=6)
                if key == "ItemKey":
                    item_key_combo[0] = combo
                    combo.bind("<<ComboboxSelected>>", update_preview)
                    combo.bind("<KeyRelease>", update_preview)
            else:
                entry = ttk.Entry(win, textvariable=var)
                entry.grid(row=row, column=1, sticky="ew", padx=10, pady=6)
                if key == "UniqueId":
                    entry.configure(state="readonly")
        win.columnconfigure(1, weight=1)

        def refresh_editor_choices(_event=None) -> None:
            rows = [
                db_item
                for db_item in self.db
                if item_matches_filters(db_item, edit_query_var.get(), edit_rarity_var.get(), edit_type_var.get())
            ]
            rows.sort(key=lambda row: (-RARITY_RANK.get(str(row.get("Rarity", "")).upper(), 0), normalize_search_text(row.get("Name"))))
            choices = [
                f"{db_item.get('ItemKey')} | {rarity_label(db_item.get('Rarity'))} | {db_item.get('Name', '')}"
                for db_item in rows[:500]
            ]
            current = vars_by_key["ItemKey"].get()
            if current and current not in choices:
                choices.insert(0, current)
            if item_key_combo[0] is not None:
                item_key_combo[0].configure(values=choices)
            suffix = f" · mostrando 500" if len(rows) > 500 else ""
            edit_result_var.set(f"{len(rows)} encontrado(s){suffix}")

        edit_search.bind("<KeyRelease>", refresh_editor_choices)
        edit_rarity_combo.bind("<<ComboboxSelected>>", refresh_editor_choices)
        edit_type_combo.bind("<<ComboboxSelected>>", refresh_editor_choices)
        refresh_editor_choices()
 
        def apply() -> None:
            try:
                old_uid = int(item.get("UniqueId", 0))
                old_key = safe_int(item.get("ItemKey"))
                new_key = int(normalize_choice(vars_by_key["ItemKey"].get()) or "0")
                if str(new_key) not in self.db_by_key and not messagebox.askyesno(APP_NAME, "Código não encontrado no catálogo. Aplicar mesmo assim?"):
                    return
                item["ItemKey"] = new_key
                for key in ["IsChaotic", "IsBlocked"]:
                    item[key] = vars_by_key[key].get().strip().lower() == "sim"
                item.pop("IsServerPendingItem", None)
                if new_key != old_key:
                    if self.db_by_key.get(str(new_key), {}).get("Type") != "GEAR":
                        item["EnchantData"] = []
                    else:
                        target_count = self.expected_enchant_slot_count(item)
                        enchants = item.get("EnchantData", [])
                        if target_count is not None and len(enchants) > target_count:
                            filled_extras = sum(
                                isinstance(enchant, dict) and self.enchant_is_filled(enchant)
                                for enchant in enchants[target_count:]
                            )
                            if filled_extras and not messagebox.askyesno(
                                APP_NAME,
                                f"A nova raridade possui apenas {target_count} espaço(s). Remover {filled_extras} encantamento(s) excedente(s)?",
                            ):
                                item["ItemKey"] = old_key
                                return
                            del enchants[target_count:]
                        incompatible = [
                            index
                            for index, enchant in enumerate(item.get("EnchantData", []))
                            if safe_int(enchant.get("StatType")) and not self.stat_allowed_for_item(item, safe_int(enchant.get("StatType")))
                        ]
                        if incompatible:
                            for index in incompatible:
                                item["EnchantData"][index] = self.empty_enchant()
                            messagebox.showinfo(
                                APP_NAME,
                                f"{len(incompatible)} encantamento(s) incompatível(is) foram removidos automaticamente.",
                            )
                self.sync_enchant_metadata(item)
                self.flag_item_modified(item)
                self.items_by_uid[old_uid] = item
                self.selected_item = item
                win.destroy()
                self.mark_dirty("Item alterado.")
                self.refresh_all()
            except Exception as exc:
                messagebox.showerror(APP_NAME, f"Valor inválido:\n{exc}")

        button_row = len(fields) + 2
        ttk.Button(win, text="Cancelar", command=win.destroy).grid(row=button_row, column=0, sticky="w", padx=14, pady=12)
        ttk.Button(win, text="Aplicar alterações", style="Accent.TButton", command=apply).grid(row=button_row, column=1, sticky="e", padx=10, pady=12)
        vars_by_key["ItemKey"].trace_add("write", update_preview)
        update_preview()
        win.bind("<Escape>", lambda _event: win.destroy())
        win.grab_set()
 
    def save_dump(self) -> None:
        if not self.path or self.data is None:
            messagebox.showinfo(APP_NAME, "Abra um save primeiro.")
            return
        if self.protected_mode_enabled() and self.path.suffix.lower() == ".es3" and taskbar_hero_is_running():
            messagebox.showerror(
                APP_NAME,
                "O Taskbar Hero está aberto.\n\nFeche o jogo normalmente e tente salvar novamente. "
                "Isso evita conflito com o salvamento local e com a nuvem.",
            )
            return
        current_signature = self.file_signature(self.path)
        if self.protected_mode_enabled() and self.loaded_file_signature and current_signature != self.loaded_file_signature:
            messagebox.showerror(
                APP_NAME,
                "O arquivo mudou no disco depois de ser carregado.\n\nPara não apagar progresso mais recente, reabra o save e refaça as alterações.",
            )
            return
        if not self.validate_before_save():
            return
        try:
            if self.loaded_kind == "es3":
                if self.save_file is None:
                    messagebox.showerror(APP_NAME, "O save .es3 não está carregado corretamente.")
                    return
                self.save_file.account = self.data["account"]
                self.save_file.player = self.data["player"]
                self.save_file.save(str(self.path), backup=True)
                self.loaded_file_signature = self.file_signature(self.path)
                backup = Path(self.save_file.last_backup_path) if self.save_file.last_backup_path else None
                self.mark_clean()
                self.status_var.set(f"Save .es3 salvo. Backup: {backup.name if backup else 'não necessário'}")
                messagebox.showinfo(APP_NAME, f"Save salvo com sucesso.\nBackup: {backup.name if backup else 'não necessário'}")
                return

            backup = versioned_backup_path(self.path)
            shutil.copy2(self.path, backup)
            atomic_write_json(self.path, self.data)
            self.loaded_file_signature = self.file_signature(self.path)
            self.mark_clean()
            self.status_var.set(f"JSON salvo. Backup: {backup.name}")
            messagebox.showinfo(APP_NAME, f"JSON salvo com sucesso.\nBackup: {backup.name}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Falha ao salvar. O arquivo original foi preservado.\n{exc}")

    def export_json(self) -> None:
        if self.data is None:
            messagebox.showinfo(APP_NAME, "Abra um save primeiro.")
            return
        initial = "player_dump.json"
        if self.path:
            initial = f"{self.path.stem}_dump.json"
        path = filedialog.asksaveasfilename(
            defaultextension=".json",
            initialfile=initial,
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            atomic_write_json(Path(path), self.data)
            self.status_var.set(f"JSON exportado: {Path(path).name}")
            messagebox.showinfo(APP_NAME, f"JSON exportado com sucesso.\nArquivo: {Path(path).name}")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Falha ao exportar JSON:\n{exc}")
 
 
# Este módulo é o núcleo da interface, não uma aplicação. Até a 3.4.0 ele expunha
# um ``main()`` próprio e executá-lo abria um editor sem a persistência
# transacional, sem a detecção fail-safe do jogo aberto e sem os bloqueios de
# criação/duplicação do Modo Protegido — todos aplicados só na camada final.
# hollyedittbh_next já recusava execução direta pelo mesmo motivo; o README
# afirmava que este arquivo também recusava, mas ele continuava abrindo.
if __name__ == "__main__":
    raise SystemExit(
        "legacy_editor é uma camada interna. Execute: py -3.12 hollyedittbh_final.py"
    )
