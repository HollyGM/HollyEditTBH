"""Registro local para comparar uma gravação com o save reaberto após jogar.

O registro não pertence ao formato ES3 e nunca é enviado ao jogo ou à Steam.
Comparações usam IDs e conteúdo dos itens, independentemente da ordem do JSON.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

from safe_persistence import normalize_path


def _digest(value: object) -> str:
    encoded = json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def receipt_path(directory: Path, save_path: Path) -> Path:
    return directory / f"{_digest(normalize_path(save_path))}.json"


def make_receipt(save_path: Path, save, save_sha256: str) -> dict:
    items = {}
    for item in save.player.get("itemSaveDatas", []):
        uid = str(item["UniqueId"])
        if uid in items:
            raise ValueError(f"ID de item repetido: {uid}")
        items[uid] = {"key": item["ItemKey"], "sha256": _digest(item)}
    locations: dict[str, list[str]] = {}

    def add(uid, label):
        if uid:
            locations.setdefault(str(uid), []).append(label)

    for source in ("inventorySaveDatas", "stashSaveDatas", "remakeTradingStashSaveDatas"):
        for slot in save.player.get(source, []):
            add(slot.get("ItemUniqueId"), f"{source}:{slot.get('Index')}")
    for hero in save.player.get("heroSaveDatas", []):
        for index, uid in enumerate(hero.get("equippedItemIds", [])):
            add(uid, f"hero:{hero.get('heroKey')}:{index}")
    return {
        "schema": 1,
        "file_identity": _digest(normalize_path(save_path)),
        "owner": _digest(str(save.account.get("ownerSteamId", ""))),
        "save_sha256": save_sha256,
        "saved_at": datetime.now(timezone.utc).isoformat(),
        "items": items,
        "locations": {uid: sorted(labels) for uid, labels in locations.items()},
    }


def write_receipt(directory: Path, save_path: Path, receipt: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    target = receipt_path(directory, save_path)
    fd, raw_temp = tempfile.mkstemp(prefix=".receipt-", suffix=".tmp", dir=directory)
    temp = Path(raw_temp)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(receipt, handle, ensure_ascii=False, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp, target)
    finally:
        if temp.exists():
            temp.unlink()


def read_receipt(directory: Path, save_path: Path) -> dict | None:
    target = receipt_path(directory, save_path)
    if not target.exists():
        return None
    record = json.loads(target.read_text(encoding="utf-8"))
    if not isinstance(record, dict) or record.get("schema") != 1:
        raise ValueError("registro de conferência com formato desconhecido")
    if not isinstance(record.get("items"), dict) or not isinstance(record.get("locations"), dict):
        raise ValueError("registro de conferência incompleto")
    if any(not isinstance(item, dict) or "key" not in item or "sha256" not in item
           for item in record["items"].values()):
        raise ValueError("registro de itens incompleto")
    return record


def compare_receipts(previous: dict, current: dict) -> dict:
    """Não atribui a causa de uma diferença: consumo normal também remove itens."""
    if previous.get("file_identity") != current["file_identity"]:
        raise ValueError("o registro pertence a outro arquivo")
    if previous.get("owner") != current["owner"]:
        raise ValueError("o save agora pertence a outra conta Steam")
    old, new = previous["items"], current["items"]
    common = old.keys() & new.keys()
    return {
        "file_changed": previous.get("save_sha256") != current["save_sha256"],
        "missing": sorted(old.keys() - new.keys(), key=int),
        "added": sorted(new.keys() - old.keys(), key=int),
        "changed": sorted((uid for uid in common if old[uid] != new[uid]), key=int),
        "moved": sorted((uid for uid in common if previous["locations"].get(uid, []) != current["locations"].get(uid, [])), key=int),
        "unlocated": sorted((uid for uid in new if not current["locations"].get(uid)), key=int),
        "present": len(common),
        "expected": len(old),
    }


def describe_comparison(report: dict) -> str:
    if not report["file_changed"]:
        intro = "O arquivo continua igual à última gravação do editor. Ainda não há evidência de um novo salvamento pelo jogo."
    else:
        intro = "O arquivo mudou desde a gravação do editor. A comparação não identifica qual programa fez a alteração."
    lines = [intro, "", f"Itens anteriores presentes: {report['present']}/{report['expected']}."]
    for field, label in (("missing", "Ausentes"), ("changed", "Com dados alterados"),
                         ("moved", "Com localização diferente"), ("added", "Novos"), ("unlocated", "Sem localização")):
        uids = report[field]
        lines.append(f"{label}: {len(uids)}" + (f" (IDs: {', '.join(uids[:12])}{'…' if len(uids) > 12 else ''})" if uids else "") + ".")
    if report["missing"]:
        lines.extend(["", "Itens consumidos, vendidos, reciclados ou removidos pelo jogo também aparecem como ausentes. A comparação não os recria automaticamente."])
    return "\n".join(lines)
