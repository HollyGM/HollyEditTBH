"""Compatibilidade: a coleta guardada agora é a única implementação.

Até a 3.3.2 existiam duas cópias quase idênticas da paginação do Steam Market —
``market_intelligence.fetch_market_snapshot`` e a versão "guarded" deste módulo —
com semânticas divergentes de ``complete`` e User-Agents diferentes. A versão
protegida virou a implementação canônica em ``market_intelligence``; este módulo
permanece apenas como nome estável para quem já o importava.
"""
from __future__ import annotations

from market_intelligence import (
    fetch_market_snapshot as fetch_market_snapshot_guarded,
    prefer_snapshot,
)

__all__ = ["fetch_market_snapshot_guarded", "prefer_snapshot"]
