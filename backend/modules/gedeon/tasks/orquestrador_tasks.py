"""GEDEON — Task agendada que monta o kit documental mensal de todos os condomínios.

Roda o kit_orchestrator (Onvio + Inter + NFS-e), idempotente, e cria uma notificação
in_app pro Jordan com o resumo (o que entrou, o que ficou pendente). NÃO envia nada
ao cliente — o GEDEON monta, a equipe revisa.

Competência = mês ANTERIOR à data de execução (salário em arrears: a folha de maio
vira o kit "Junho", montado em junho). Pode passar `competencia` explícita p/ rodar manual.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


def _competencia_anterior() -> str:
    """Mês anterior ao atual no formato 'MM.YYYY' (usa o relógio do worker)."""
    from datetime import date

    hoje = date.today()
    m, a = hoje.month - 1, hoje.year
    if m < 1:
        m, a = 12, a - 1
    return f"{m:02d}.{a}"


@shared_task(name="gedeon.montar_kits_mensais", bind=True, max_retries=2, soft_time_limit=900, time_limit=1200)
def montar_kits_mensais_task(
    self, competencia: str | None = None, condominios: list | None = None, blocos: list | None = None
):
    """Monta o kit de todos os condomínios da competência e notifica o Jordan.

    `blocos`: montagem incremental — None = tudo; subconjunto de
    folha/guias/pagamentos/vavt/cnds/nfse/ponto. "ponto" só dispara o robô do host."""
    import asyncio

    try:
        from modules.gedeon.services.kit_orchestrator import montar_kits_mensais

        comp = competencia or _competencia_anterior()
        pedido = set(blocos) if blocos else None
        # blocos do orquestrador (tudo menos "ponto", que é host-only via ponte Redis)
        blocos_orq = [b for b in (blocos or []) if b != "ponto"] or None

        rel = {"competencia": comp, "etapas": {}, "resumo": {"etapas_ok": 0, "etapas_falha": 0}}
        # só roda o orquestrador se houver algum bloco que não seja apenas "ponto"
        if pedido is None or blocos_orq:
            tid = getattr(getattr(self, "request", None), "id", None)  # p/ progresso ao vivo (Redis)
            rel = asyncio.run(
                montar_kits_mensais(comp, condominios=condominios, dry_run=False, blocos=blocos_orq, task_id=tid)
            )

        resumo = rel.get("resumo", {})
        logger.info(
            "GEDEON kit mensal %s (blocos=%s): %d etapas OK, %d falhas",
            comp,
            blocos_orq or "todos",
            resumo.get("etapas_ok", 0),
            resumo.get("etapas_falha", 0),
        )
        # ponte do ponto (host): em montagem completa OU quando "ponto" foi pedido
        if pedido is None or "ponto" in pedido:
            _solicitar_ponto(comp)
        # MONTAGEM LOCAL: indexa os arquivos locais (ponto/solides/onvio) nos kits do PORTAL
        # com file_path real, e dispara o aviso "kit disponível". Não-fatal (não quebra a montagem).
        try:
            from modules.client_portal.services.portal_kit_materializar_service import materializar

            mes_n, ano_n = int(comp.split(".")[0]), int(comp.split(".")[1])  # comp = MM.YYYY
            ky, kmth = (ano_n, mes_n + 1) if mes_n < 12 else (ano_n + 1, 1)  # mês do KIT = competência+1
            stats_mat = materializar(f"{ky}-{kmth:02d}")
            logger.info("GEDEON materializou no portal: %s", stats_mat)
        except Exception as exc:
            logger.warning("materialização no portal falhou (não-fatal): %s", exc)
        # notifica o Jordan só na montagem COMPLETA (não pinga a cada bloco incremental)
        if pedido is None:
            _notificar_jordan(comp, rel)
        return rel
    except Exception as exc:
        logger.error("montar_kits_mensais_task falhou: %s", exc)
        raise self.retry(exc=exc, countdown=600)


def _solicitar_ponto(competencia: str) -> None:
    """Sinaliza (Redis db1) o vigia do host p/ rodar o robô de ponto assinado (Sólides/Playwright).
    O ponto roda DEPOIS da montagem (precisa da folha já no kit). Não-fatal."""
    try:
        import json
        import os

        import redis

        r = redis.from_url(os.getenv("REDIS_URL", "redis://localhost:6379/1"))
        r.set("gedeon:ponto:request", competencia, ex=3600)
        r.set("gedeon:ponto:status", json.dumps({"competencia": competencia, "state": "pending"}), ex=3600)
        logger.info("GEDEON: pedido de ponto sinalizado p/ %s", competencia)
    except Exception as exc:
        logger.warning("GEDEON: não consegui sinalizar o ponto: %s", exc)


def _notificar_jordan(competencia: str, rel: dict) -> None:
    """Cria uma notificação in_app pro Jordan com o resumo do kit montado.
    Idempotente: não duplica se já houver uma notificação do mesmo kit nas últimas 12h."""
    try:
        from sqlalchemy import text

        from core.database.session import get_sync_db

        resumo = rel.get("resumo", {})
        etapas = rel.get("etapas", {})
        falhas = [k for k, v in etapas.items() if not v.get("ok")]
        ref = f"gedeon_kit_{competencia}"
        corpo = (
            f"GEDEON montou o kit da competência {competencia}: "
            f"{resumo.get('etapas_ok', 0)} etapas OK, {resumo.get('etapas_falha', 0)} falhas. "
        )
        if falhas:
            corpo += "Pendências: " + ", ".join(falhas[:8]) + ". "
        corpo += "Falta (host): ponto assinado (robô Sólides) e atribuição de VA/VT. Revise no Drive."

        with get_sync_db() as db:
            user = db.execute(text("SELECT id FROM users WHERE email = 'jjesus@conectamais.pro' LIMIT 1")).fetchone()
            tenant = db.execute(text("SELECT id FROM tenants LIMIT 1")).fetchone()
            if not user or not tenant:
                logger.warning("_notificar_jordan: user/tenant não encontrado")
                return
            ja = db.execute(
                text(
                    "SELECT 1 FROM communication_notifications "
                    "WHERE reference_id = :ref AND reference_type = 'gedeon_kit_mensal' "
                    "AND created_at > NOW() - INTERVAL '12 hours' LIMIT 1"
                ),
                {"ref": ref},
            ).fetchone()
            if ja:
                return
            db.execute(
                text("""
                INSERT INTO communication_notifications
                  (tenant_id, user_id, title, body, type,
                   reference_type, reference_id, action_url, channels, extra_data)
                VALUES (:tenant_id, :user_id, :title, :body, 'gedeon_kit_mensal',
                   'gedeon_kit_mensal', :ref, '/ged/kits',
                   '["in_app"]'::jsonb, '{}'::jsonb)
            """),
                {
                    "tenant_id": str(tenant[0]),
                    "user_id": str(user[0]),
                    "title": f"GEDEON — Kit {competencia} montado",
                    "body": corpo,
                    "ref": ref,
                },
            )
            db.commit()
    except Exception as exc:
        logger.warning("_notificar_jordan falhou (não crítico): %s", exc)
