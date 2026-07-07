"""SST Tasks — Celery tasks para automacao SST + eSocial."""

from .afastamento_tasks import verificar_afastamentos_vencidos, verificar_inss_pendente
from .esocial_tasks import (
    esocial_pull_recibos,
    transmit_afastamento_to_esocial,
    transmit_aso_to_esocial,
    transmit_cat_to_esocial,
)

__all__ = [
    "verificar_afastamentos_vencidos",
    "verificar_inss_pendente",
    "transmit_cat_to_esocial",
    "transmit_aso_to_esocial",
    "transmit_afastamento_to_esocial",
    "esocial_pull_recibos",
]
