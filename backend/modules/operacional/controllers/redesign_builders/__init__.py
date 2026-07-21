"""
redesign_builders — um arquivo por módulo (fanout 3 terminais, sem conflito).

Cada <modulo>.py expõe: SLUG (str, com hífen), build(db)->dict, EXTRA_MENU (list),
e opcionalmente router (APIRouter com /action/*). O registry
(redesign_data_controller._discover_module_builders) SOBRESCREVE o _build_<mod> do
monólito com build(), SOMA EXTRA_MENU e inclui o router.

REGRA: cada terminal edita SÓ os arquivos dos SEUS módulos (ver auditoria/parity/DIVISAO_3T.md).
Nunca edite o registry, o _shared/helpers, ou o arquivo de outro terminal.
"""
