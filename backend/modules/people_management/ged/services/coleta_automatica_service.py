"""D4 — ColetaAutomaticaService: orquestra sync Onvio + auto-assemble + log."""

import asyncio
import time
from datetime import UTC, date, datetime
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from core.database.session import SyncSessionLocal
from core.logging import logger

from ..models.coleta_automatica import GedColetaConfig, GedColetaLog
from ..models.document_kit import GedDocumentKit


class ColetaAutomaticaService:
    """Orquestra: Sync Onvio → Auto-assemble + matching → Log."""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def executar(
        self,
        run_type: str = "manual",
        triggered_by: str = "system",
        mes_ref: str | None = None,
        force_resync: bool = False,
    ) -> dict:
        """Executa pipeline completo de coleta.

        Args:
            run_type: 'cron' ou 'manual'
            triggered_by: email do usuário ou 'cron'
            mes_ref: mês ISO (YYYY-MM-DD). Se None, processa últimos 3 meses.
            force_resync: força re-sync mesmo que docs já existam

        Returns:
            {status, duration_ms, sync_novos, kits_assembled, onvio_matched, erros}
        """
        start = time.time()
        erros: list[dict[str, Any]] = []
        sync_novos = 0
        kits_assembled = 0
        onvio_matched = 0

        # ── Fase 1: Sync Onvio (síncrono — roda em thread pool) ──────────────
        try:
            sync_result = await asyncio.get_event_loop().run_in_executor(None, self._sync_onvio_sync, mes_ref)
            sync_novos = sync_result.get("novos", 0)
            logger.info("Sync Onvio: %d novos docs", sync_novos)
        except Exception as e:
            logger.error("Fase sync_onvio falhou: %s", e)
            erros.append({"fase": "sync_onvio", "erro": str(e)})

        # ── Fase 2: Auto-assemble (async) ─────────────────────────────────────
        try:
            from modules.people_management.ged.services.kit_builder_service import (
                KitBuilderService,
            )

            builder = KitBuilderService(self.db)

            if mes_ref:
                mes_date = date.fromisoformat(mes_ref).replace(day=1)
                # Validar: mês deve ter kits existentes
                has_kits = await self.db.scalar(
                    select(func.count(GedDocumentKit.id)).where(GedDocumentKit.reference_month == mes_date)
                )
                if not has_kits:
                    erros.append(
                        {
                            "fase": "planejamento",
                            "erro": f"Mês {mes_date.isoformat()} não tem kits. Crie kits primeiro via /auto-assemble.",
                        }
                    )
                    meses_alvo = []
                else:
                    meses_alvo = [mes_date]
            else:
                meses_alvo = await self._meses_com_kits()
                if not meses_alvo:
                    erros.append(
                        {
                            "fase": "planejamento",
                            "erro": "Nenhum mês tem kits cadastrados. Use /auto-assemble explicitamente para criar kits novos.",
                        }
                    )

            for mes in meses_alvo:
                try:
                    r = await builder.auto_build_all_kits(mes)
                    kits_assembled += r.get("kits_created", 0) + r.get("kits_updated", 0)
                    onvio_matched += r.get("onvio_matched", 0)
                    if r.get("errors"):
                        erros.append({"fase": f"auto_assemble_{mes.isoformat()}", "erros": r["errors"]})
                except Exception as e:
                    logger.error("Auto-assemble %s falhou: %s", mes, e)
                    erros.append({"fase": f"auto_assemble_{mes.isoformat()}", "erro": str(e)})
                    await self.db.rollback()  # 08/09: sessão abortada derrubava o registro do log (21/08: 'current transaction is aborted')
        except Exception as e:
            logger.error("Fase auto_assemble falhou: %s", e)
            erros.append({"fase": "auto_assemble", "erro": str(e)})
            await self.db.rollback()  # 08/09: sessão abortada derrubava o registro do log (21/08: 'current transaction is aborted')

        # ── Fase 3: Certidões (D5.4) ─────────────────────────────────────────
        certidoes_atualizadas = 0
        alertas_disparados = 0
        try:
            import os

            from modules.people_management.ged.services.certidoes_updater_service import (
                CertidoesUpdaterService,
            )

            cnpj_empresa = os.getenv("EMPRESA_CNPJ", "35710481000103")
            cert_result = await CertidoesUpdaterService(self.db).executar(
                cnpj_empresa,
                run_type=run_type,
                triggered_by=triggered_by,
                write_log=False,  # D5.5.2: ColetaAutomaticaService grava 1 log unificado
            )
            certidoes_atualizadas = cert_result["certidoes_atualizadas"]
            alertas_disparados = cert_result["alertas_disparados"]
            for e in cert_result["erros"]:
                erros.append({"fase": "certidoes", **e})
            logger.info("Fase certidoes: atualizadas=%d alertas=%d", certidoes_atualizadas, alertas_disparados)
        except Exception as e:
            logger.error("Fase certidoes falhou: %s", e)
            erros.append({"fase": "certidoes", "erro": str(e)})

        # ── Resultado ─────────────────────────────────────────────────────────
        duration_ms = int((time.time() - start) * 1000)
        if erros and (kits_assembled == 0 and sync_novos == 0 and certidoes_atualizadas == 0):
            status = "error"
        elif erros:
            status = "partial"
        else:
            status = "success"

        # Gravar log
        log = GedColetaLog(
            run_type=run_type,
            status=status,
            duration_ms=duration_ms,
            sync_novos=sync_novos,
            kits_assembled=kits_assembled,
            onvio_matched=onvio_matched,
            certidoes_atualizadas=certidoes_atualizadas,
            alertas_disparados=alertas_disparados,
            erros=erros if erros else None,
            triggered_by=triggered_by,
        )
        self.db.add(log)

        # Atualizar config
        await self.db.execute(
            update(GedColetaConfig)
            .where(GedColetaConfig.id == 1)
            .values(last_run=datetime.now(UTC), last_status=status)
        )

        await self.db.commit()

        logger.info(
            "ColetaAutomatica %s concluida: status=%s duration=%dms sync=%d kits=%d matched=%d erros=%d",
            run_type,
            status,
            duration_ms,
            sync_novos,
            kits_assembled,
            onvio_matched,
            len(erros),
        )

        return {
            "status": status,
            "duration_ms": duration_ms,
            "sync_novos": sync_novos,
            "kits_assembled": kits_assembled,
            "onvio_matched": onvio_matched,
            "erros": erros,
        }

    def _sync_onvio_sync(self, mes_ref: str | None) -> dict:
        """Roda OnvioSyncService com sessão síncrona (thread pool)."""
        # ⭐ TODAS as empresas, não só a Eletrônica. `OnvioSyncService(db)` sem client_id cai
        # no padrão histórico e ignorava os 147 documentos da Patrimonial — inclusive as CNDs
        # que a Portte deposita lá. Medido em 19/08/2026.
        from modules.gedeon.onvio.onvio_sync_service import sincronizar_todas_empresas

        db = SyncSessionLocal()
        try:
            result = sincronizar_todas_empresas(db, mes_ref=mes_ref)
            return result or {}
        except Exception as e:
            logger.error("_sync_onvio_sync error: %s", e)
            return {"novos": 0, "erro": str(e)}
        finally:
            db.close()

    async def _meses_com_kits(self) -> list[date]:
        """Retorna meses que JÁ TÊM kits em ged_document_kits, desc.

        Princípio D4.1: auto-assemble PREENCHE kits existentes — NÃO cria
        kits novos sozinho. Mês sem kits → SKIP. Criar kits novos é decisão
        de negócio via endpoint /auto-assemble explícito.
        """
        result = await self.db.execute(
            select(GedDocumentKit.reference_month).distinct().order_by(GedDocumentKit.reference_month.desc())
        )
        return [row[0] for row in result.all()]

    async def get_config(self) -> GedColetaConfig:
        """Retorna a config singleton (id=1)."""
        result = await self.db.execute(select(GedColetaConfig).where(GedColetaConfig.id == 1))
        return result.scalar_one()

    async def update_config(
        self,
        enabled: bool,
        cron_expr: str,
        updated_by: str,
    ) -> None:
        """Atualiza enabled + cron_expr."""
        await self.db.execute(
            update(GedColetaConfig)
            .where(GedColetaConfig.id == 1)
            .values(
                enabled=enabled,
                cron_expr=cron_expr,
                updated_by=updated_by,
                updated_at=datetime.now(UTC),
            )
        )
        await self.db.commit()

    async def get_history(self, limit: int = 20) -> list[GedColetaLog]:
        """Retorna últimas N execuções ordenadas por data desc."""
        result = await self.db.execute(select(GedColetaLog).order_by(GedColetaLog.run_at.desc()).limit(limit))
        return list(result.scalars().all())
