"""AI Predictions Module.

DEPRECATED: Use 'modules.inteligencia' instead for router imports.
Deprecation date: 2026-03-11. Removal target: 2026-05-11.
"""

import warnings

warnings.warn(
    "Importing from 'modules.ai' is deprecated. "
    "Use 'modules.inteligencia' for router access. "
    "This module will be removed after 2026-05-11.",
    DeprecationWarning,
    stacklevel=2,
)

# 06/09/2026: `modules.ai.models`, `.services`, `.repositories`, `.schemas`, `.controllers` e os
# 13 subpacotes de IA sem importador foram APAGADOS (50 tabelas `ai_*` com 0 linhas desde
# 20/01; 0 requisições em 15 dias). O que vive aqui é `conversation` (orquestrador, José Luís,
# Bartolo, Central), `consultores`, `fraud_detection` e `openclaw`. Ver auditoria/MAPA_CONECTA_PRO_20260906.md.
__all__: list[str] = []
