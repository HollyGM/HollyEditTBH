#!/usr/bin/env python3
from __future__ import annotations

import sys
import tkinter as tk
from pathlib import Path
from tkinter import Tk, messagebox

import tbh_save_editor as legacy
from hollyedittbh_next import EnhancedProEditor, MARKET_CACHE_FILE
from market_intelligence import POLICY_CHECKED_AT
from market_snapshot_guard import fetch_market_snapshot_guarded


class FinalProEditor(EnhancedProEditor):
    """Camada final 3.3.1: endurece operações de risco sem remover o editor."""

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

    def create_item(
        self,
        item_key: int,
        quantity: int = 1,
        target: str = "Inventario",
        enchanted: bool = True,
    ) -> list[dict]:
        if self.protected_mode_enabled():
            messagebox.showwarning(
                legacy.APP_NAME,
                "O Modo Protegido não cria itens que não existiam no save carregado.",
            )
            return []
        return super().create_item(item_key, quantity, target, enchanted)

    def duplicate_item(self, item: dict, quantity: int = 1) -> list[dict]:
        if self.protected_mode_enabled():
            messagebox.showwarning(
                legacy.APP_NAME,
                "O Modo Protegido não duplica itens. Use apenas os itens já existentes no save.",
            )
            return []
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

    def market_round_capacity(self, stash_page: int) -> int:
        actual = legacy.ProEditor.free_slot_count(self, f"Armazem {stash_page}")
        return max(0, min(actual, self.configured_market_slots()))

    def free_slot_count(self, target: str) -> int:
        count = super().free_slot_count(target)
        caller = sys._getframe(1).f_code.co_name
        if caller == "fill_market_page" and target.startswith("Armazem "):
            return min(count, self.configured_market_slots())
        pending = getattr(self, "_market_summary_capacity", None)
        if pending and target == pending[0]:
            self._market_summary_capacity = None
            return min(count, pending[1])
        return count

    def market_candidates(self, stash_page: int, limit: int) -> list[dict]:
        rows = super().market_candidates(stash_page, limit)
        target = f"Armazem {stash_page}"
        self._market_summary_capacity = (target, self.market_round_capacity(stash_page))
        return rows

    def _market_refresh_background(self) -> None:
        try:
            snapshot = fetch_market_snapshot_guarded(MARKET_CACHE_FILE)
            self.intel_jobs.put(("market", snapshot))
        except Exception as exc:
            self.intel_jobs.put(("status", f"Mercado Steam: {exc}"))

    def _walk_widgets(self, widget: tk.Misc):
        yield widget
        try:
            children = widget.winfo_children()
        except tk.TclError:
            children = []
        for child in children:
            yield from self._walk_widgets(child)

    def _update_protection_tree(self, widget: tk.Misc) -> None:
        try:
            if widget.winfo_class() != "Treeview":
                return
            for iid in widget.get_children():
                values = list(widget.item(iid, "values"))
                if values and str(values[0]) == "Modo Protegido" and len(values) >= 3:
                    values[2] = "bloqueia jogo aberto, criação, duplicação e operações de maior risco"
                    widget.item(iid, values=values)
        except (tk.TclError, AttributeError):
            return

    def open_smart_center(self) -> None:
        before = set(self.root.winfo_children())
        super().open_smart_center()
        self.root.update_idletasks()
        market_slots = self.configured_market_slots()

        for child in self.root.winfo_children():
            if child in before or not isinstance(child, tk.Toplevel):
                continue
            for widget in self._walk_widgets(child):
                self._update_protection_tree(widget)
                try:
                    text = str(widget.cget("text"))
                except (tk.TclError, AttributeError):
                    text = ""

                if text == "Quantidade máxima":
                    try:
                        widget.configure(text="Slots nesta rodada")
                    except tk.TclError:
                        pass
                elif text == "Adicionar desejados (uso local)":
                    try:
                        widget.configure(text="Criar desejados (modo desprotegido)")
                    except tk.TclError:
                        pass
                elif "O editor não consulta sua Steam" in text:
                    replacement = (
                        f"Política-base oficial confirmada em {POLICY_CHECKED_AT}: equipamentos Cósmico, Divino e Celestial "
                        "continuam fora de novas recomendações enquanto não houver anúncio oficial posterior de liberação, "
                        "com exceção conhecida para Soulstones. O editor não acessa conta ou login Steam: usa apenas snapshot "
                        "público e cacheado do Community Market como referência; aceitação e preço finais pertencem ao jogo/Steam."
                    )
                    try:
                        widget.configure(text=replacement)
                    except tk.TclError:
                        pass

                try:
                    if widget.winfo_class() == "TSpinbox" and str(widget.get()) == "20":
                        widget.configure(from_=1, to=market_slots)
                        widget.set(str(market_slots))
                except (tk.TclError, AttributeError):
                    pass

    def show_about(self) -> None:
        messagebox.showinfo(
            legacy.APP_NAME,
            f"{legacy.APP_NAME}\nVersão {legacy.APP_VERSION}\n\n"
            "Editor independente de saves do Taskbar Hero.\n"
            "Backup automático, gravação atômica, validação estrutural, inteligência de equipamentos e Modo Protegido.\n\n"
            "O Modo Protegido não cria nem duplica itens. Não existe garantia anti-banimento e a elegibilidade do Mercado é decidida pelo jogo/Steam.",
        )


def main() -> None:
    root = Tk()
    app = FinalProEditor(root)
    requested = Path(sys.argv[1]) if len(sys.argv) > 1 and not str(sys.argv[1]).startswith("-") else None
    default_dump = legacy.APP_DIR / "player_dump.json"
    if requested and requested.is_file():
        app.load_dump(requested)
    elif default_dump.exists():
        app.load_dump(default_dump)
    root.mainloop()


if __name__ == "__main__":
    main()
