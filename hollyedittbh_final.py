#!/usr/bin/env python3
from __future__ import annotations

import hashlib
import copy
import json
import ntpath
import os
import subprocess
import sys
from pathlib import Path
from tkinter import Tk, messagebox

import tbh_save_editor as legacy
import platform_support
import persistence_audit
from hollyedittbh_next import EnhancedProEditor
from safe_persistence import SaveConflictError, normalize_path, write_save_transactionally
from save_layer import ES3_PASSWORD, SaveFile as BaseSaveFile, es3_decrypt


class VerifiedSaveFile(BaseSaveFile):
    """SaveFile com identidade da origem e persistência transacional."""

    @classmethod
    def load(cls, path, password=ES3_PASSWORD):
        source = Path(path)
        raw = source.read_bytes()
        es3_obj = json.loads(es3_decrypt(raw, password).decode("utf-8"))
        loaded = cls(es3_obj, password)
        loaded._source_path = normalize_path(source)
        loaded._source_sha256 = hashlib.sha256(raw).hexdigest()
        return loaded

    def save(self, path, backup=True):
        previous_integrity = self.integrity_valid
        previous_es3 = copy.deepcopy(self._es3)
        self.last_backup_path = None
        try:
            blob = self.to_es3_bytes()
            target_identity = normalize_path(path)
            expected_sha256 = None
            if getattr(self, "_source_path", None) == target_identity:
                expected_sha256 = getattr(self, "_source_sha256", None)

            saved_path, backup_path, blob_sha256 = write_save_transactionally(
                path,
                blob,
                backup=bool(backup),
                expected_sha256=expected_sha256,
            )
            self.last_backup_path = str(backup_path) if backup_path is not None else None
            installed = type(self).load(saved_path, self.password)
            if (installed._source_sha256 != blob_sha256 or not installed.integrity_valid
                    or installed.account != self.account or installed.player != self.player
                    or installed._es3 != self._es3):
                raise SaveConflictError(
                    "O arquivo relido não corresponde à edição. Reabra o save antes de continuar. "
                    f"Backup: {self.last_backup_path or 'não disponível'}."
                )
            self._source_path = target_identity
            self._source_sha256 = blob_sha256
            return saved_path
        except Exception:
            self.integrity_valid = previous_integrity
            self._es3 = previous_es3
            raise


# O carregamento legado consulta estas referências de módulo em tempo de execução.
legacy.SaveFile = VerifiedSaveFile


def taskbar_hero_is_running_fail_safe() -> bool:
    """Falha de detecção é tratada como estado inseguro para salvar."""
    if os.name != "nt":
        return platform_support.posix_game_is_running_fail_safe()
    system_root = os.environ.get("SystemRoot")
    if not system_root:
        return True
    # ntpath explícito: o caminho é sempre Windows, e os.path.join seguiria a
    # convenção do host, produzindo barras trocadas quando o comportamento é
    # exercitado fora do Windows.
    tasklist = ntpath.join(system_root, "System32", "tasklist.exe")
    try:
        completed = subprocess.run(
            [tasklist, "/FI", "IMAGENAME eq TaskBarHero.exe", "/FO", "CSV", "/NH"],
            capture_output=True,
            text=True,
            errors="replace",
            timeout=3,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return True
    if completed.returncode != 0:
        return True
    return "taskbarhero.exe" in completed.stdout.casefold()


legacy.taskbar_hero_is_running = taskbar_hero_is_running_fail_safe


class FinalProEditor(EnhancedProEditor):
    """Camada final 3.3.2: endurece persistência sem alterar o formato do save."""

    def file_signature(self, path: Path | None = None):
        """Retorna assinatura estável por timestamp, tamanho e SHA-256 do conteúdo."""
        target = path or getattr(self, "path", None)
        if target is None:
            return None
        for _attempt in range(2):
            try:
                before = target.stat()
                digest = hashlib.sha256()
                with target.open("rb") as handle:
                    for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                        digest.update(chunk)
                after = target.stat()
            except OSError:
                return None
            if before.st_mtime_ns == after.st_mtime_ns and before.st_size == after.st_size:
                return (after.st_mtime_ns, after.st_size, digest.hexdigest())
        return None

    def save_dump(self) -> None:
        path = getattr(self, "path", None)
        if (
            path is not None
            and path.suffix.lower() == ".es3"
            and getattr(self, "loaded_file_signature", None) is None
        ):
            messagebox.showerror(
                legacy.APP_NAME,
                "Não foi possível verificar a assinatura do save carregado.\n\n"
                "Para evitar sobrescrever um estado externo desconhecido, reabra o arquivo antes de salvar.",
            )
            return
        super().save_dump()

    def _receipt_directory(self) -> Path:
        # Fora da pasta do jogo e também fora do diretório temporário do bundle.
        return platform_support.user_data_dir(legacy.APP_NAME, legacy.APP_DIR, frozen=True) / "persistence"

    def record_saved_persistence(self) -> str:
        try:
            record = persistence_audit.make_receipt(self.path, self.save_file, self.save_file._source_sha256)
            persistence_audit.write_receipt(self._receipt_directory(), self.path, record)
        except Exception as exc:
            # A falha de um relatório auxiliar não desfaz um save já confirmado.
            return f"A gravação foi confirmada, mas o registro de conferência não pôde ser salvo: {exc}"
        return "Após entrar no jogo, sair e fechar normalmente, use Mais opções → Conferir persistência após jogar."

    def check_saved_persistence(self) -> None:
        path = getattr(self, "path", None)
        if path is None or path.suffix.lower() != ".es3":
            messagebox.showinfo(legacy.APP_NAME, "Abra o SaveFile_Live.es3 para conferir os itens. Um JSON não é carregado pelo jogo.")
            return
        if legacy.taskbar_hero_is_running():
            messagebox.showerror(legacy.APP_NAME, "Feche o jogo normalmente antes de conferir. Não foi possível confirmar que está fechado.")
            return
        try:
            previous = persistence_audit.read_receipt(self._receipt_directory(), path)
            if previous is None:
                messagebox.showinfo(legacy.APP_NAME, "Ainda não há registro de uma gravação feita por esta versão do editor para este arquivo.")
                return
            current_save = VerifiedSaveFile.load(path)
            if not current_save.integrity_valid:
                raise ValueError("a assinatura do arquivo relido não confere")
            current = persistence_audit.make_receipt(path, current_save, current_save._source_sha256)
            report = persistence_audit.compare_receipts(previous, current)
            text = persistence_audit.describe_comparison(report)
            if getattr(self, "dirty", False):
                text += "\n\nHá alterações pendentes no editor. A conferência leu o disco e preservou essas alterações em memória."
            if report["missing"] or report["unlocated"]:
                messagebox.showwarning(legacy.APP_NAME, text)
            else:
                messagebox.showinfo(legacy.APP_NAME, text)
        except Exception as exc:
            messagebox.showerror(legacy.APP_NAME, f"Não foi possível conferir a persistência:\n{exc}")

    def on_protected_mode_changed(self) -> None:
        enabled = bool(self.protected_mode_var.get())
        if not enabled:
            accepted = messagebox.askyesno(
                legacy.APP_NAME,
                "Desativar o Modo Protegido libera operações que podem criar ou duplicar itens inexistentes no save original.\n\n"
                "O desenvolvedor do jogo informa que itens criados ou obtidos por métodos anormais podem resultar em restrição do jogo ou do Mercado. "
                "O editor não oferece proteção contra essa verificação.\n\n"
                "Desativar mesmo assim?",
            )
            if not accepted:
                self.protected_mode_var.set(True)
                enabled = True
        self.protected_mode = enabled
        self.status_var.set(
            "Modo Protegido ativado: criação e duplicação de itens bloqueadas."
            if enabled
            else "Modo Protegido desativado conscientemente nesta sessão."
        )

    def open_create_item_dialog(self, initial_target: str = "Automatico", local_market_notice: bool = False) -> None:
        if self.protected_mode_enabled():
            messagebox.showwarning(
                legacy.APP_NAME,
                "Criação de itens bloqueada pelo Modo Protegido.\n\n"
                "Para preservar o save original e reduzir risco de sanções do jogo/Mercado, o modo protegido trabalha apenas com itens já existentes. "
                "A criação local só fica disponível após desativação consciente do Modo Protegido.",
            )
            return
        super().open_create_item_dialog(initial_target, local_market_notice)

    def warn_game_reorganizes_once(self) -> None:
        """Distingue edição local de confirmação depois de jogar."""
        if getattr(self, "_reorg_warning_shown", False):
            return
        self._reorg_warning_shown = True
        messagebox.showwarning(
            legacy.APP_NAME,
            "Sobre itens criados ou duplicados:\n\n"
            "A gravação local será relida e conferida. A aceitação pelo jogo precisa "
            "ser verificada depois de entrar, sair e fechar normalmente.\n\n"
            "Use Mais opções → Conferir persistência após jogar para comparar "
            "os IDs dos itens e distinguir mudança de posição de ausência.\n\n"
            "Itens obtidos por métodos anormais podem gerar restrição do jogo ou do Mercado.",
        )

    def create_item(
        self,
        item_key: int,
        quantity: int = 1,
        target: str = "Inventario",
        enchanted: bool = False,
    ) -> list[dict]:
        if self.protected_mode_enabled():
            messagebox.showwarning(
                legacy.APP_NAME,
                "O Modo Protegido não cria itens que não existiam no save carregado.",
            )
            return []
        self.warn_game_reorganizes_once()
        return super().create_item(item_key, quantity, target, enchanted)

    def duplicate_item(self, item: dict, quantity: int = 1) -> list[dict]:
        if self.protected_mode_enabled():
            messagebox.showwarning(
                legacy.APP_NAME,
                "O Modo Protegido não duplica itens. Use apenas os itens já existentes no save.",
            )
            return []
        self.warn_game_reorganizes_once()
        return super().duplicate_item(item, quantity)

    def equip_item(self, hero: dict, slot_index: int, item: dict) -> bool:
        uid = legacy.safe_int(item.get("UniqueId")) if isinstance(item, dict) else 0
        if self.protected_mode_enabled() and uid in getattr(self, "session_created_uids", set()):
            messagebox.showwarning(
                legacy.APP_NAME,
                "O Modo Protegido não equipa um item criado nesta sessão.\n\n"
                "Selecione um item que já existia no save ou cancele a operação.",
            )
            return False
        return super().equip_item(hero, slot_index, item)

    def show_about(self) -> None:
        messagebox.showinfo(
            legacy.APP_NAME,
            f"{legacy.APP_NAME}\nVersão {legacy.APP_VERSION}\n\n"
            "Editor independente de saves do Taskbar Hero.\n"
            "Backup automático, gravação transacional, validação estrutural, inteligência de equipamentos e Modo Protegido.\n\n"
            "O Modo Protegido não cria nem duplica itens. Não existe garantia anti-banimento e a elegibilidade do Mercado é decidida pelo jogo/Steam.",
        )


def main() -> None:
    root = Tk()
    app = FinalProEditor(root)
    requested = Path(sys.argv[1]) if len(sys.argv) > 1 and not str(sys.argv[1]).startswith("-") else None
    default_dump = legacy.APP_DIR / "player_dump.json"
    if requested is not None:
        if requested.is_file():
            app.load_dump(requested)
        else:
            messagebox.showerror(legacy.APP_NAME, f"O arquivo solicitado não foi encontrado:\n{requested}")
    elif legacy.DEFAULT_SAVE_FILE.is_file():
        # Descobrir o caminho do save não bastava: até aqui a descoberta só
        # escolhia a pasta inicial do seletor, e o usuário precisava confirmar o
        # mesmo arquivo a cada abertura. Carregar é leitura — nada é gravado até
        # Salvar alterações, e o Modo Protegido continua governando a gravação.
        app.load_dump(legacy.DEFAULT_SAVE_FILE)
    elif default_dump.is_file():
        app.load_dump(default_dump)
    root.mainloop()


if __name__ == "__main__":
    main()
