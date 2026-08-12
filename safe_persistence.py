from __future__ import annotations

import hashlib
import os
import shutil
import tempfile
import time
from pathlib import Path

import save_layer


class SaveConflictError(RuntimeError):
    """O arquivo de origem deixou de ser o mesmo que foi carregado."""


def normalize_path(path: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.realpath(os.path.abspath(os.fspath(path))))


def file_sha256(path: str | os.PathLike[str]) -> str:
    digest = hashlib.sha256()
    with open(path, "rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _timestamped_backup_path(path: Path) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    candidate = path.with_name(f"{path.stem}_backup_{stamp}{path.suffix}")
    suffix = 2
    while candidate.exists():
        candidate = path.with_name(f"{path.stem}_backup_{stamp}_{suffix}{path.suffix}")
        suffix += 1
    return candidate


def _private_rollback_path(path: Path) -> Path:
    fd, raw_path = tempfile.mkstemp(prefix=f".{path.name}.original-", suffix=".tmp", dir=path.parent)
    os.close(fd)
    rollback = Path(raw_path)
    rollback.unlink()
    return rollback


def _write_verified_temp(path: Path, blob: bytes) -> tuple[Path, str]:
    expected_blob_hash = hashlib.sha256(blob).hexdigest()
    fd, raw_path = tempfile.mkstemp(prefix=".tbh-save-", suffix=".tmp", dir=path.parent)
    temp_path = Path(raw_path)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(blob)
            handle.flush()
            os.fsync(handle.fileno())
        if file_sha256(temp_path) != expected_blob_hash:
            raise OSError("falha ao validar o arquivo temporário antes da substituição")
        return temp_path, expected_blob_hash
    except Exception:
        try:
            temp_path.unlink()
        except OSError:
            pass
        raise


def _assert_expected_source(path: Path, expected_sha256: str) -> None:
    try:
        observed = file_sha256(path)
    except OSError as exc:
        raise SaveConflictError(
            "O save original não pôde ser verificado antes da gravação. Reabra o arquivo e refaça as alterações."
        ) from exc
    if observed != expected_sha256:
        raise SaveConflictError(
            "O save mudou no disco depois de ser carregado. Reabra o arquivo e refaça as alterações."
        )


def _restore_original_if_safe(original_path: Path, rollback_path: Path) -> bool:
    if not rollback_path.exists() or original_path.exists():
        return False
    try:
        save_layer.os.replace(rollback_path, original_path)
        return True
    except OSError:
        return False


def write_save_transactionally(
    path: str | os.PathLike[str],
    blob: bytes,
    *,
    backup: bool,
    expected_sha256: str | None,
) -> tuple[str, Path | None, str]:
    """Persiste bytes no mesmo diretório sem sobrescrever uma origem inesperada.

    Para um save previamente carregado (``expected_sha256`` informado), o novo
    conteúdo é escrito e validado primeiro. Em seguida, a origem é movida
    atomicamente para um caminho de rollback/backup e seu hash é conferido já
    fora do nome original. Só então o temporário é instalado. No Windows,
    ``os.rename`` falha caso outro processo recrie o destino durante a troca,
    evitando sobrescrever esse novo arquivo.
    """
    target = Path(os.path.abspath(os.fspath(path)))
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path, blob_sha256 = _write_verified_temp(target, blob)
    rollback_path: Path | None = None
    source_moved = False

    try:
        if expected_sha256 is None:
            backup_path = None
            if backup and target.exists():
                backup_path = _timestamped_backup_path(target)
                shutil.copy2(target, backup_path)
            save_layer.os.replace(temp_path, target)
            temp_path = Path()
            return str(target), backup_path, blob_sha256

        _assert_expected_source(target, expected_sha256)
        rollback_path = _timestamped_backup_path(target) if backup else _private_rollback_path(target)

        # Retira atomicamente a origem do nome público. A conferência posterior
        # fecha a janela entre "verificar" e "substituir" existente na 3.3.1.
        save_layer.os.replace(target, rollback_path)
        source_moved = True

        moved_hash = file_sha256(rollback_path)
        if moved_hash != expected_sha256:
            restored = _restore_original_if_safe(target, rollback_path)
            source_moved = not restored
            raise SaveConflictError(
                "O save mudou durante a gravação e a operação foi cancelada sem instalar o novo conteúdo."
            )

        if target.exists():
            raise SaveConflictError(
                "Outro processo recriou o save durante a gravação. O novo conteúdo não foi instalado."
            )

        # No Windows, produto suportado, rename não substitui um destino que
        # reapareça entre a checagem acima e a instalação.
        os.rename(temp_path, target)
        temp_path = Path()
        source_moved = False

        if not backup and rollback_path.exists():
            rollback_path.unlink()
            rollback_path = None

        return str(target), rollback_path if backup else None, blob_sha256
    except Exception as exc:
        if source_moved and rollback_path is not None and rollback_path.exists():
            restored = _restore_original_if_safe(target, rollback_path)
            if not restored and not target.exists():
                raise OSError(
                    f"Falha ao concluir a gravação e ao restaurar o original. Cópia de recuperação preservada em {rollback_path.name}."
                ) from exc
        raise
    finally:
        if temp_path and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
