from __future__ import annotations

import ctypes
import hashlib
import os
import secrets
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


def _unique_path(path: Path, label: str, *, visible_backup: bool) -> Path:
    stamp = time.strftime("%Y%m%d_%H%M%S")
    for _attempt in range(16):
        token = secrets.token_hex(4)
        if visible_backup:
            candidate = path.with_name(f"{path.stem}_backup_{stamp}_{os.getpid()}_{token}{path.suffix}")
        else:
            candidate = path.with_name(f".{path.name}.{label}-{os.getpid()}-{token}.tmp")
        if not candidate.exists():
            return candidate
    raise OSError("não foi possível reservar um nome seguro para recuperação do save")


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


def _recover_failed_windows_replace(target: Path, backup_path: Path) -> bool:
    """Restaura o nome principal sem sobrescrever um arquivo que tenha reaparecido.

    A documentação de ReplaceFileW prevê uma falha em que o arquivo substituído
    já foi movido para ``lpBackupFileName``. Nesse estado, o caminho principal
    pode ficar ausente. No Windows, ``os.rename`` não substitui um destino
    existente, então uma recriação concorrente do target não é apagada.
    """
    if target.exists():
        return True
    if not backup_path.exists():
        return False
    try:
        os.rename(backup_path, target)
        return True
    except OSError:
        return target.exists()


def _windows_replace_with_backup(target: Path, replacement: Path, backup_path: Path) -> None:
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    replace_file = kernel32.ReplaceFileW
    replace_file.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_uint32,
        ctypes.c_void_p,
        ctypes.c_void_p,
    ]
    replace_file.restype = ctypes.c_int
    ctypes.set_last_error(0)
    success = replace_file(str(target), str(replacement), str(backup_path), 0, None, None)
    if success:
        return

    error = ctypes.get_last_error()
    safe_path_state = _recover_failed_windows_replace(target, backup_path)
    message = ctypes.FormatError(error).strip() or "ReplaceFileW falhou"
    if not safe_path_state:
        if backup_path.exists():
            message += f"; o original permanece preservado em {backup_path.name}"
        else:
            message += "; o caminho principal não pôde ser restaurado automaticamente"
    raise OSError(error, message, str(target))


def _replace_existing_with_backup(target: Path, replacement: Path, backup_path: Path) -> None:
    """Substitui target em uma chamada nativa e captura o conteúdo substituído."""
    if os.name == "nt":
        _windows_replace_with_backup(target, replacement, backup_path)
        return

    # Fallback apenas para desenvolvimento fora do Windows. O produto e o CI de
    # release exercitam ReplaceFileW e seus estados de recuperação no Windows.
    shutil.copy2(target, backup_path)
    save_layer.os.replace(replacement, target)


def _restore_captured_source(
    target: Path,
    captured_source: Path,
    expected_installed_sha256: str,
) -> tuple[bool, Path | None]:
    """Tenta rollback sem apagar uma versão concorrente mais nova.

    Retorna ``(True, None)`` somente quando o arquivo substituído durante o
    rollback é comprovadamente o blob gerado pelo editor. Se outro conteúdo for
    capturado, ele permanece preservado e é devolvido como caminho de recovery.
    """
    try:
        if file_sha256(target) != expected_installed_sha256:
            return False, None
    except OSError:
        return False, None

    rejected_new = _unique_path(target, "rollback", visible_backup=True)
    try:
        _replace_existing_with_backup(target, captured_source, rejected_new)
    except OSError:
        return False, None

    try:
        rejected_hash = file_sha256(rejected_new)
    except OSError:
        return False, rejected_new if rejected_new.exists() else None

    if rejected_hash != expected_installed_sha256:
        # Outro processo gravou entre a checagem e o rollback. O caminho target
        # contém a versão capturada no primeiro commit; a versão mais nova fica
        # preservada em rejected_new para recuperação explícita.
        return False, rejected_new

    try:
        rejected_new.unlink()
    except OSError:
        # É o blob gerado por nós, portanto mantê-lo não ameaça dados do usuário.
        pass
    return True, None


def write_save_transactionally(
    path: str | os.PathLike[str],
    blob: bytes,
    *,
    backup: bool,
    expected_sha256: str | None,
) -> tuple[str, Path | None, str]:
    """Persiste o save validado e falha de forma conservadora em conflito.

    No Windows, um save previamente carregado é trocado com ``ReplaceFileW``.
    A API combina as etapas de substituição em uma única função e pode capturar,
    no mesmo procedimento, os bytes que ocupavam o caminho no momento do
    commit. O hash dessa cópia é comparado com a origem carregada; divergência
    provoca rejeição do novo conteúdo e tentativa segura de restauração.
    """
    target = Path(os.path.abspath(os.fspath(path)))
    target.parent.mkdir(parents=True, exist_ok=True)
    prepared_path, blob_sha256 = _write_verified_temp(target, blob)
    temp_path: Path | None = prepared_path
    captured_source: Path | None = None

    try:
        if expected_sha256 is None:
            backup_path = None
            if backup and target.exists():
                backup_path = _unique_path(target, "backup", visible_backup=True)
                shutil.copy2(target, backup_path)
            # Compatibilidade com a gravação de um novo caminho e com as
            # regressões históricas de falha de os.replace.
            save_layer.os.replace(temp_path, target)
            temp_path = None
            return str(target), backup_path, blob_sha256

        _assert_expected_source(target, expected_sha256)
        captured_source = _unique_path(target, "source", visible_backup=backup)
        _replace_existing_with_backup(target, temp_path, captured_source)
        temp_path = None

        try:
            source_at_commit_sha256 = file_sha256(captured_source)
        except OSError as exc:
            raise OSError(
                f"A substituição ocorreu, mas a cópia de segurança {captured_source.name} não pôde ser validada."
            ) from exc

        try:
            installed_sha256 = file_sha256(target)
        except OSError as exc:
            raise OSError(
                f"A substituição ocorreu, mas o save instalado não pôde ser validado. A origem foi preservada em {captured_source.name}."
            ) from exc

        if installed_sha256 != blob_sha256:
            raise SaveConflictError(
                f"O save instalado foi alterado por outro processo antes da validação final. A origem anterior foi preservada em {captured_source.name}."
            )

        if source_at_commit_sha256 != expected_sha256:
            restored, concurrent_recovery = _restore_captured_source(target, captured_source, blob_sha256)
            if restored:
                captured_source = None
                raise SaveConflictError(
                    "O save mudou durante o commit. A versão externa foi restaurada e as alterações do editor não foram instaladas."
                )
            if concurrent_recovery is not None:
                captured_source = None  # a primeira versão externa agora ocupa target
                raise OSError(
                    "Novo conflito detectado durante o rollback. A primeira versão externa foi restaurada ao caminho principal "
                    f"e a versão concorrente mais nova foi preservada em {concurrent_recovery.name}."
                )
            raise OSError(
                f"Foi detectado conflito durante o commit. A versão substituída permanece preservada em {captured_source.name}; o editor não a apagou."
            )

        if not backup and captured_source is not None:
            try:
                captured_source.unlink()
                captured_source = None
            except OSError:
                # O save novo já foi validado e está instalado; uma falha ao
                # remover a cópia privada não deve converter sucesso em falha.
                pass

        return str(target), captured_source if backup else None, blob_sha256
    finally:
        if temp_path is not None and temp_path.exists():
            try:
                temp_path.unlink()
            except OSError:
                pass
