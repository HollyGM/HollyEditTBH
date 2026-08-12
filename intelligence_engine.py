from __future__ import annotations

from dataclasses import dataclass
import math
import re
from typing import Mapping, Sequence

RARITY_RANK = {
    "COMMON": 1,
    "UNCOMMON": 2,
    "RARE": 3,
    "LEGENDARY": 4,
    "IMMORTAL": 5,
    "ARCANA": 6,
    "BEYOND": 7,
    "CELESTIAL": 8,
    "DIVINE": 9,
    "COSMIC": 10,
}

SLOT_NAMES = {
    0: "ARMA PRINCIPAL",
    1: "ARMA SECUNDÁRIA",
    2: "CAPACETE",
    3: "ARMADURA",
    4: "LUVAS",
    5: "BOTAS",
    6: "AMULETO",
    7: "BRINCO",
    8: "ANEL",
    9: "ABRAÇADEIRA",
}

MAIN_PREFIX = {101: "30", 201: "31", 301: "32", 401: "33", 501: "34", 601: "35"}
OFFHAND_PREFIX = {101: "40", 201: "41", 301: "42", 401: "43", 501: "44", 601: "45"}
FIXED_PREFIX = {2: "50", 3: "51", 4: "52", 5: "53", 6: "60", 7: "61", 8: "62", 9: "63"}

_LEVEL_RE = re.compile(r"(?:\bLv\.?|\bLevel)\s*[:\-]?\s*(\d{1,3})\b", re.IGNORECASE)


@dataclass(frozen=True)
class ScoreBreakdown:
    total: float
    rarity: float
    level: float
    enchantments: float
    affinity: float
    filled_slots: int
    total_tier: int
    chaotic: float
    value_tiebreak: float
    level_known: bool

    def as_tuple(self) -> tuple[float, ...]:
        """Sortable compatibility shape. Only total is a primary score."""
        return (
            round(self.total, 6),
            round(self.affinity, 6),
            round(self.enchantments, 6),
            round(self.level, 6),
            round(self.rarity, 6),
            float(self.total_tier),
            float(self.filled_slots),
            round(self.value_tiebreak, 6),
        )


def slot_prefixes(hero_key: int, slot_index: int) -> set[str]:
    if slot_index == 0:
        value = MAIN_PREFIX.get(int(hero_key), "")
    elif slot_index == 1:
        value = OFFHAND_PREFIX.get(int(hero_key), "")
    else:
        value = FIXED_PREFIX.get(int(slot_index), "")
    return {value} if value else set()


def extract_item_level(db_item: Mapping | None) -> tuple[int, bool]:
    if not db_item:
        return 0, False
    for key in ("Level", "ItemLevel", "RequiredLevel", "ReqLevel", "RequireLevel"):
        raw = db_item.get(key)
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if 0 < value <= 999:
            return value, True
    match = _LEVEL_RE.search(str(db_item.get("Name", "")))
    if match:
        return int(match.group(1)), True
    return 0, False


def _is_filled_enchant(enchant: Mapping | None) -> bool:
    if not isinstance(enchant, Mapping):
        return False
    try:
        tier = int(enchant.get("Tier") or 0)
        stat = int(enchant.get("StatType") or 0)
        mod = int(enchant.get("StatModKey") or 0)
    except (TypeError, ValueError):
        return False
    return tier > 0 and (stat > 0 or mod > 0)


def score_item(
    item: Mapping | None,
    db_item: Mapping | None,
    hero_weights: Mapping[int | str, float] | None = None,
    *,
    rarity_step: float = 20.0,
    level_weight: float = 0.22,
    tier_weight: float = 14.0,
    filled_slot_bonus: float = 1.25,
    chaotic_bonus: float = 6.0,
    unprofiled_stat_weight: float = 0.85,
) -> ScoreBreakdown:
    """Continuous and explainable equipment score.

    Rarity remains important but no longer suppresses every other signal. Strong,
    hero-aligned enchantments can legitimately beat a blank item one rarity above.
    Raw enchant values are only a bounded tiebreak because different stat families
    use incomparable units.
    """
    if not item:
        return ScoreBreakdown(0.0, 0.0, 0.0, 0.0, 0.0, 0, 0, 0.0, 0.0, False)

    db_item = db_item or {}
    rarity_name = str(db_item.get("Rarity", "")).upper()
    rarity_rank = RARITY_RANK.get(rarity_name, 0)
    rarity_points = rarity_rank * rarity_step

    item_level, level_known = extract_item_level(db_item)
    level_points = min(item_level, 100) * level_weight if level_known else 0.0

    weights: dict[int, float] = {}
    for key, value in (hero_weights or {}).items():
        try:
            stat_key = int(key)
            numeric = float(value)
        except (TypeError, ValueError):
            continue
        weights[stat_key] = max(0.25, min(3.0, numeric))

    enchant_points = 0.0
    affinity_points = 0.0
    value_tiebreak = 0.0
    total_tier = 0
    filled = 0

    for enchant in item.get("EnchantData", []) or []:
        if not _is_filled_enchant(enchant):
            continue
        try:
            tier = max(0, min(30, int(enchant.get("Tier") or 0)))
            stat_type = int(enchant.get("StatType") or 0)
            raw_value = abs(float(enchant.get("Value") or 0))
        except (TypeError, ValueError):
            continue

        filled += 1
        total_tier += tier
        stat_weight = weights.get(stat_type, unprofiled_stat_weight)
        tier_fraction = tier / 30.0
        points = tier_fraction * tier_weight * stat_weight
        enchant_points += points
        affinity_points += max(0.0, stat_weight - unprofiled_stat_weight) * tier_fraction * tier_weight
        value_tiebreak += min(2.0, math.log10(raw_value + 1.0) * 0.20) * stat_weight

    slot_points = filled * filled_slot_bonus
    chaos_points = chaotic_bonus if bool(item.get("IsChaotic")) else 0.0
    total = rarity_points + level_points + enchant_points + slot_points + chaos_points + value_tiebreak

    return ScoreBreakdown(
        total=round(total, 6),
        rarity=round(rarity_points, 6),
        level=round(level_points, 6),
        enchantments=round(enchant_points + slot_points + value_tiebreak, 6),
        affinity=round(affinity_points, 6),
        filled_slots=filled,
        total_tier=total_tier,
        chaotic=round(chaos_points, 6),
        value_tiebreak=round(value_tiebreak, 6),
        level_known=level_known,
    )


@dataclass(frozen=True)
class Assignment:
    total_score: float
    item_by_hero: tuple[int, ...]


def optimal_unique_assignment(
    score_matrix: Sequence[Sequence[float | None]],
    *,
    minimum_scores: Sequence[float] | None = None,
    empty_score: float = 0.0,
) -> Assignment:
    """Exact assignment using candidate-by-candidate bitmask DP.

    Rows are heroes and columns are unique items. None marks incompatibility.
    The algorithm is exact for the game's small hero count and prevents the
    save-order bias caused by sequential greedy assignment.
    """
    hero_count = len(score_matrix)
    if hero_count == 0:
        return Assignment(0.0, ())
    candidate_count = max((len(row) for row in score_matrix), default=0)
    minima = list(minimum_scores or [empty_score] * hero_count)
    if len(minima) != hero_count:
        raise ValueError("minimum_scores must have one entry per hero")

    empty_assignment = tuple([-1] * hero_count)
    dp: dict[int, tuple[float, tuple[int, ...]]] = {0: (0.0, empty_assignment)}

    # Private empty option per hero. It does not consume a shared item.
    for hero_index in range(hero_count):
        if empty_score + 1e-12 < minima[hero_index]:
            continue
        bit = 1 << hero_index
        updates = dict(dp)
        for mask, (score, assignment) in dp.items():
            if mask & bit:
                continue
            new_assignment = list(assignment)
            new_assignment[hero_index] = -2
            candidate = (score + empty_score, tuple(new_assignment))
            old = updates.get(mask | bit)
            if old is None or candidate[0] > old[0] + 1e-12 or (
                abs(candidate[0] - old[0]) <= 1e-12 and candidate[1] < old[1]
            ):
                updates[mask | bit] = candidate
        dp = updates

    for candidate_index in range(candidate_count):
        updates = dict(dp)
        for mask, (score, assignment) in dp.items():
            for hero_index in range(hero_count):
                bit = 1 << hero_index
                if mask & bit:
                    continue
                row = score_matrix[hero_index]
                if candidate_index >= len(row):
                    continue
                value = row[candidate_index]
                if value is None:
                    continue
                numeric = float(value)
                if numeric + 1e-12 < minima[hero_index]:
                    continue
                new_assignment = list(assignment)
                new_assignment[hero_index] = candidate_index
                candidate = (score + numeric, tuple(new_assignment))
                old = updates.get(mask | bit)
                if old is None or candidate[0] > old[0] + 1e-12 or (
                    abs(candidate[0] - old[0]) <= 1e-12 and candidate[1] < old[1]
                ):
                    updates[mask | bit] = candidate
        dp = updates

    full_mask = (1 << hero_count) - 1
    if full_mask not in dp:
        raise ValueError("no feasible assignment satisfies the minimum scores")
    total, assignment = dp[full_mask]
    return Assignment(round(total, 6), assignment)


def greedy_assignment(score_matrix: Sequence[Sequence[float | None]]) -> Assignment:
    """Sequential baseline kept only for regression tests and audit comparisons."""
    used: set[int] = set()
    picked: list[int] = []
    total = 0.0
    for row in score_matrix:
        best_index = -2
        best_score = 0.0
        for index, value in enumerate(row):
            if index in used or value is None:
                continue
            numeric = float(value)
            if numeric > best_score:
                best_score = numeric
                best_index = index
        if best_index >= 0:
            used.add(best_index)
        picked.append(best_index)
        total += best_score
    return Assignment(round(total, 6), tuple(picked))
