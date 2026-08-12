#!/usr/bin/env python3
"""Compatibilidade do núcleo legado.

Importado como módulo, este nome resolve para ``legacy_editor`` para preservar a
API histórica usada pela interface e pelos testes. Executado diretamente, inicia
a entrada final suportada do HollyEditTBH.
"""
from __future__ import annotations

if __name__ == "__main__":
    from hollyedittbh_final import main

    main()
else:
    import sys
    import legacy_editor as _legacy

    sys.modules[__name__] = _legacy
