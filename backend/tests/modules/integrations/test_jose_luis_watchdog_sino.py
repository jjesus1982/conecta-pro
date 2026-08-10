"""Watchdog do José Luís sai do Telegram e vai pro SINO (Task 5 do plano irmão).

Telegram é canal banido na casa. Além disso, `_telegram_send` degradava mal: sem
`MONITOR_BOT_TOKEN`/`TELEGRAM_CHAT_ID` no worker ela só logava um warning e a
lista **não chegava a ninguém** — silêncio que parece funcionamento. O sino
(`communication_notifications`) é a mesma superfície dos alertas de DP/marketing,
com RBAC resolvido server-side.
"""

import inspect

from modules.integrations.connectors.whatsapp import tasks as wtasks


def test_telegram_foi_removido_do_modulo():
    """Critério de pronto do plano: `_telegram_send` REMOVIDA, não só sem uso."""
    assert not hasattr(wtasks, "_telegram_send"), "_telegram_send ainda existe"
    fonte = inspect.getsource(wtasks)
    for proibido in ("telegram", "MONITOR_BOT_TOKEN", "TELEGRAM_CHAT_ID", "api.telegram.org"):
        assert proibido.lower() not in fonte.lower(), f"ainda há referência a {proibido!r}"


def test_entrega_no_sino_existe_e_e_async():
    assert inspect.iscoroutinefunction(wtasks._entregar_no_sino)


def test_as_duas_tasks_do_watchdog_continuam_registradas():
    """Trocar o canal não pode derrubar o agendamento — o beat carrega por nome."""
    for nome in ("followup_conversas", "auditar_qualidade"):
        assert hasattr(wtasks, nome)


def test_silencio_honesto_quando_nao_ha_nada():
    """`rows` vazio -> ninguém é notificado. Mandar 'nada esfriou' todo dia é ruído
    diário que treina o time a ignorar o sino."""
    fonte = inspect.getsource(wtasks.followup_conversas)
    assert "frias\": 0" in fonte or "'frias': 0" in fonte
    # o retorno vazio não pode passar por entrega nenhuma
    antes_do_return = fonte.split('"frias": 0')[0] if '"frias": 0' in fonte else fonte
    assert "_entregar_no_sino" not in antes_do_return.split("if not rows:")[-1]
