"""
Tarefas Celery do KRONOS/THEMIS — execução agendada.
KRONOS: verifica vencimentos às 06h e publica alertas no Event Bus.
THEMIS: verifica assinaturas pendentes a cada 4h.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(name="gedeon.kronos.verificacao_diaria", bind=True, max_retries=3)
def kronos_verificacao_diaria(self):
    """
    Verifica vencimentos de certidões, ASOs e EPIs diariamente às 06h.
    Publica eventos FIN_INADIMPLENCIA_DETECTADA e SAUDE_ASO_EMITIDO no barramento.
    """
    import asyncio

    try:
        # `KronosAgent` NUNCA EXISTIU — a classe é `Kronos`, e o método é
        # `executar_verificacao_diaria`, não `..._completa`. O beat morreu 12× por dia de
        # 11/08 a 14/08 com ImportError, e o vigia de certidão e ASO ficou cego três dias.
        from modules.gedeon.agents.kronos import Kronos

        kronos = Kronos()
        result = asyncio.run(kronos.executar_verificacao_diaria())
        logger.info(
            "KRONOS diário: %d certidões, %d ASOs com alerta",
            result.get("certidoes_alerta", 0),
            result.get("asos_alerta", 0),
        )
        return result
    except Exception as exc:
        logger.error("KRONOS falhou: %s", exc)
        raise self.retry(exc=exc, countdown=300)


@shared_task(name="gedeon.themis.verificacao_assinaturas", bind=True, max_retries=3)
def themis_verificacao_assinaturas(self):
    """
    Verifica assinaturas GED pendentes e publica alertas a cada 4h.
    Publica GED_ASSINATURA_PENDENTE para contratos vencendo.
    """
    import asyncio

    try:
        # Dois defeitos aqui, não um: a classe é `Themis` (não `ThemisAgent`) E o método
        # EXIGE uma AsyncSession. Só renomear a classe trocaria ImportError por TypeError.
        from core.database.session import async_session_factory
        from modules.gedeon.agents.themis import Themis

        async def _run():
            async with async_session_factory() as db:
                return await Themis().verificar_e_alertar(db)

        result = asyncio.run(_run())
        logger.info(
            "THEMIS: %d pendentes, %d críticos",
            result.get("total_pendentes", 0),
            result.get("criticos", 0),
        )
        return result
    except Exception as exc:
        logger.error("THEMIS falhou: %s", exc)
        raise self.retry(exc=exc, countdown=60)


@shared_task(name="gedeon.fiscal.verificar_certidoes", bind=True, max_retries=3)
def fiscal_verificar_certidoes(self):
    """
    Verifica vencimento de certidões fiscais e publica FISCAL_CERTIDAO_VENCIDA.
    Executa diariamente às 07h, complementar ao KRONOS.
    """
    import asyncio

    try:
        from modules.fiscal.publishers import verificar_e_publicar_vencimentos

        async def _run():
            # Busca certidões do GED e verifica vencimentos
            from sqlalchemy import text

            from core.database.session import get_sync_db

            # 🔴 A CONSULTA ANTERIOR NUNCA RODOU. Lia `ged_documents` — que tem ZERO
            # linhas — e pedia as colunas `tipo`, `data_vencimento` e `is_active`, que
            # aquela tabela não tem (são `document_type`, `valid_until`, `deleted_at`).
            # Não é regressão: é código que nunca executou, escrito contra um schema
            # imaginado. Mesmo com o import consertado, morria em UndefinedColumn.
            #
            # As certidões vivem em `ged_certidoes` (10 linhas), e o próprio docstring do
            # KRONOS já dizia isso: "ged_certidoes: id, name, document_type, expiry_date".
            # Uso a MESMA fonte que ele — duas fontes para a mesma pergunta viram duas
            # verdades. Não tem `client_id`: certidão aqui é da EMPRESA (cnpj), não do
            # cliente, então `cliente_id` fica None em vez de inventar vínculo.
            with get_sync_db() as db:
                rows = db.execute(
                    text(
                        "SELECT id::text, document_type, expiry_date, cnpj "
                        "FROM ged_certidoes "
                        "WHERE expiry_date IS NOT NULL "
                        "  AND coalesce(alerta_ativo, true) "
                        "  AND expiry_date <= CURRENT_DATE + interval '30 days' "
                        "ORDER BY expiry_date ASC LIMIT 200"
                    )
                ).fetchall()

            certidoes = [
                {
                    "id": r[0],
                    "tipo": r[1],
                    "data_vencimento": str(r[2]),
                    "cliente_id": None,
                    "cnpj": r[3],
                }
                for r in rows
            ]
            publicadas = await verificar_e_publicar_vencimentos(certidoes)
            return {"total_verificadas": len(certidoes), "eventos_publicados": publicadas}

        result = asyncio.run(_run())
        logger.info("Fiscal certidões: %s", result)
        return result
    except Exception as exc:
        logger.error("fiscal_verificar_certidoes falhou: %s", exc)
        raise self.retry(exc=exc, countdown=300)


def _recalcular_todas_as_competencias() -> int:
    """Refaz `total_documents` e a completude de TODOS os kits, todo dia.

    Achado em 18/09/2026: 39 kits de 03 a 07/2026 declaravam mais documentos do que tinham
    — o Prime Arena dizia 49 e tinha 43; o Laranjeiras dizia 82 e tinha 72. Número visível
    na tela de Documentos, e errado havia meses.

    A causa não é uma: são NOVE lugares que fazem `INSERT INTO ged_kit_documents` sem chamar
    recálculo nenhum (`kit_real_controller` sozinho tem sete). A rede diária que existia —
    `ged.kit_incremental_diario` — só remonta o mês corrente e o anterior, então 08 e 09
    ficavam certos e todo o resto envelhecia sem ninguém para consertar.

    Pôr a chamada nos nove lugares seria guardar um contrato que o décimo esquece. A conta
    já tem dono único (`completude_slots.recalcular_competencia`, a mesma fórmula da tela);
    o que faltava era alguém passar por TODA competência, não só pelas duas vivas.

    ⚠️ Recalcula também `completion_percentage`. Medido antes de ligar, em transação
    revertida: dos 137 kits, 39 mudaram o contador e ZERO mudaram o percentual — a régua de
    bloco já era a mesma. Kit entregue não teve nota reescrita por baixo.
    """
    from sqlalchemy import text  # noqa: PLC0415

    from core.database.session import get_sync_db  # noqa: PLC0415
    from modules.gedeon.services.completude_slots import recalcular_competencia  # noqa: PLC0415

    tocados = 0
    try:
        with get_sync_db() as db:
            meses = db.execute(
                text("SELECT DISTINCT reference_month FROM ged_document_kits WHERE reference_month IS NOT NULL")
            ).all()
            for (mes,) in meses:
                tocados += recalcular_competencia(db, str(mes))
            db.commit()
        logger.info("recalculo_kits: %d kit(s) em %d competência(s)", tocados, len(meses))
    except Exception as exc:  # noqa: BLE001 — higiene de número não derruba o aviso de kit pronto
        logger.warning("recalculo_kits falhou: %s", exc)
    return tocados


@shared_task(name="gedeon.verificar_kits_completos", bind=True, max_retries=3)
def verificar_kits_completos(self):
    """Avisa o dono quando um kit do DRIVE (o que o cliente recebe) chega a 100%.

    Antes olhava `ged_document_kits.completion_percentage = 100` — o kit MATERIALIZADO pelo
    sistema, que estava em 100% por documento fabricado (nota/boleto/certidão desenhados) —
    e mandou 195 "Kit Completo" ao sino entre 14/08 e 06/09/2026 enquanto o Drive dizia 20%.
    Agora: completude real (kit_completude_service, mesmo cache da tela Documentos), da
    competência anterior; um aviso por (condomínio, competência)."""
    from datetime import date

    from sqlalchemy import text

    from core.database.session import get_sync_db

    try:
        _recalcular_todas_as_competencias()
        hoje = date.today()
        m, a = (hoje.month - 1, hoje.year) if hoje.month > 1 else (12, hoje.year - 1)
        comp = f"{m:02d}.{a}"
        import json  # noqa: PLC0415

        from modules.gedeon.services.kit_completude_service import completude_kits

        try:
            out = completude_kits(comp)
        except Exception as exc:  # noqa: BLE001 — Drive fora do ar não é kit completo
            logger.warning("verificar_kits_completos: Drive indisponível (%s)", exc)
            return {"kits_alertados": 0, "erro": str(exc)[:120]}
        kits = out.get("kits") or out.get("condominios") or []
        alertados = 0
        with get_sync_db() as db:
            user_id = db.execute(text("SELECT id FROM users WHERE email = 'jjesus@conectamais.pro' LIMIT 1")).scalar()
            tenant_id = db.execute(text("SELECT id FROM tenants LIMIT 1")).scalar()
            if not user_id or not tenant_id:
                return {"kits_alertados": 0, "erro": "usuario_ou_tenant_nao_encontrado"}
            for k in kits:
                pct = int(k.get("completion_percentage") or k.get("pct") or 0)
                cond = k.get("condominio") or k.get("nome") or "?"
                if pct < 100:
                    continue
                # Atlas aprende do fluxo REAL (só o 'Kit real' o alimentava; o Drive, nunca).
                try:
                    from modules.gedeon.agents.atlas import atlas as _atlas

                    _cid = db.execute(
                        text(
                            "SELECT c.id::text FROM clients c WHERE upper(c.name) LIKE '%' || upper(:n) || '%' LIMIT 1"
                        ),
                        {"n": cond.split()[0] if cond else "?"},
                    ).scalar()
                    if _cid:
                        _atlas.registrar_kit_concluido(
                            client_id=_cid,
                            competencia=comp,
                            tipo_kit="drive",
                            score_final=pct,
                            docs_total=int(k.get("total") or 0),
                            docs_auto=0,
                            observacoes="kit do Drive a 100% (verificar_kits_completos)",
                            criado_por="kronos",
                        )
                except Exception as _exc:  # noqa: BLE001 — aprendizado não derruba o aviso
                    logger.warning("atlas.registrar_kit_concluido falhou p/ %s: %s", cond, _exc)
                ref = f"kit_drive:{cond}:{comp}"
                ja = db.execute(
                    text(
                        "SELECT 1 FROM communication_notifications WHERE reference_type = 'ged_kit_completo' AND extra_data->>'ref' = :r LIMIT 1"
                    ),
                    {"r": ref},
                ).first()
                if ja:
                    continue
                db.execute(
                    text("""
                    INSERT INTO communication_notifications
                      (tenant_id, user_id, title, body, type, reference_type, reference_id, action_url, channels, extra_data)
                    VALUES (:tenant_id, :user_id, :title, :body, 'kit_completo', 'ged_kit_completo', NULL,
                            '/modulos/documentos', '["in_app"]'::jsonb, CAST(:extra AS jsonb))
                """),
                    {
                        "tenant_id": tenant_id,
                        "user_id": user_id,
                        "title": f"Kit completo no Drive — {cond} ({comp})",
                        "body": f"O kit de {cond} da competência {comp} está 100% no Drive ({k.get('total', '?')} arquivo(s)). Pode ser entregue.",
                        "extra": json.dumps({"ref": ref}),
                    },
                )
                alertados += 1
            db.commit()
        logger.info("verificar_kits_completos %s: %d kit(s) do Drive a 100%%", comp, alertados)
        return {"competencia": comp, "kits_no_drive": len(kits), "kits_alertados": alertados}
    except Exception as exc:
        logger.error("verificar_kits_completos: %s", exc)
        raise self.retry(exc=exc, countdown=300)


@shared_task(name="gedeon.hermes_vincular_docs_mes", bind=True, max_retries=3)
def hermes_vincular_docs_mes(self, mes_ref: str | None = None):
    """
    Vincula onvio_documents do mês aos slots ged_kit_documents via HERMES.
    Executa dia 1 às 09:00 (após cron Onvio overnight).
    mes_ref=None → mês corrente. Formato: 'MM.YYYY'.
    """
    try:
        from modules.gedeon.agents.hermes import Hermes

        hermes = Hermes()
        if not mes_ref:
            # Dia 1 chega o pacote da competência ANTERIOR — 'mês corrente' vinculava nada.
            from datetime import date as _d

            _h = _d.today()
            _m, _a = (_h.month - 1, _h.year) if _h.month > 1 else (12, _h.year - 1)
            mes_ref = f"{_m:02d}.{_a}"
        result = hermes.processar_mes(mes_ref)
        logger.info(
            "HERMES %s: %d vinculados, %d ignorados, %d erros",
            result.get("mes_ref"),
            result.get("vinculados", 0),
            result.get("ignorados", 0),
            result.get("erros", 0),
        )
        return result
    except Exception as exc:
        logger.error("hermes_vincular_docs_mes falhou: %s", exc)
        raise self.retry(exc=exc, countdown=300)


@shared_task(name="gedeon.assinaturas.avisar_pendentes", bind=True, max_retries=2)
def avisar_assinaturas_pendentes(self, dry_run: bool = False):
    """Avisa POR E-MAIL quem tem documento esperando assinatura.

    A notificação in-app já existia e é passiva: `portal_notifications` não tem canal, e o
    funcionário só a vê se entrar no portal por conta própria. Medido em 21/08/2026: 6 de
    165 lidas, com 51 recibos e 67 holerites parados desde 15/07. Porteiro e ASG não entram
    num portal web para descobrir que têm tarefa — alguém precisa avisar.

    Só avisa sobre o que É ASSINÁVEL (tem PDF), e no máximo um e-mail por pessoa a cada
    `_JANELA_DIAS`. Lembrete diário vira spam e some junto com o resto.
    """
    from core.database.session import get_sync_db
    from modules.signatures.services.aviso_assinatura_service import avisar_pendentes

    try:
        with get_sync_db() as db:
            rel = avisar_pendentes(db, dry_run=dry_run)
            if not dry_run:
                db.commit()
        logger.info("aviso de assinaturas: %s", rel)
        return rel
    except Exception as exc:  # noqa: BLE001
        logger.warning("aviso de assinaturas falhou: %s", exc)
        raise self.retry(exc=exc, countdown=600) from exc
