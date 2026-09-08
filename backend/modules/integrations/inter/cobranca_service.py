"""D6.3 — CobrancaService: gerencia cobranças/boletos Inter no banco de dados."""

from decimal import Decimal
import logging
from datetime import date
from typing import Any

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


class CobrancaService:
    """Gerencia cobranças emitidas via Inter e seu ciclo de vida."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def sincronizar_status(self) -> dict[str, Any]:
        """Atualiza status de cobranças A_RECEBER consultando a API Inter.

        Para cada cobrança em status A_RECEBER com cobranca_id_inter preenchido,
        consulta a API Inter e atualiza o status local.
        Retorna {atualizadas, erros}.
        """
        import os

        from modules.integrations.banking.adapters.base import BankCredentials
        from modules.integrations.banking.adapters.inter import InterAdapter

        rows = (
            (
                await self.db.execute(
                    text("""
                    SELECT id, cobranca_id_inter
                    FROM inter_cobrancas
                    WHERE status = 'A_RECEBER'
                      AND cobranca_id_inter IS NOT NULL
                    ORDER BY created_at
                    LIMIT 50
                """),
                )
            )
            .mappings()
            .all()
        )

        adapter = InterAdapter(
            BankCredentials(
                client_id=os.getenv("INTER_CLIENT_ID", ""),
                client_secret=os.getenv("INTER_CLIENT_SECRET", ""),
                certificate_path=os.getenv("INTER_CERT_PATH"),
                private_key_path=os.getenv("INTER_KEY_PATH"),
                environment=os.getenv("INTER_ENVIRONMENT", "production"),
            )
        )

        atualizadas = 0
        erros: list[str] = []

        try:
            for row in rows:
                try:
                    result = await adapter.get_boleto(row["cobranca_id_inter"])
                    novo_status = result.get("status") or result.get("situacao")
                    if novo_status and novo_status != "A_RECEBER":
                        await self.db.execute(
                            text("""
                                UPDATE inter_cobrancas
                                SET status = :status, updated_at = NOW()
                                WHERE id = :id
                            """),
                            {"status": novo_status, "id": str(row["id"])},
                        )
                        atualizadas += 1
                except Exception as exc:
                    logger.warning("D6.3 sincronizar_status erro %s: %s", row["cobranca_id_inter"], exc)
                    erros.append(str(exc))
        finally:
            await adapter.close()

        if atualizadas:
            await self.db.commit()

        logger.info("D6.3 sincronizar_status: %d atualizadas, %d erros", atualizadas, len(erros))
        return {"atualizadas": atualizadas, "erros": erros}

    async def listar(
        self,
        status: str | None = None,
        vencimento_inicio: date | None = None,
        vencimento_fim: date | None = None,
        limit: int = 100,
    ) -> list[dict]:
        """Lista cobranças com filtros opcionais."""
        where_parts = ["1=1"]
        params: dict = {"limit": limit}

        if status:
            where_parts.append("status = :status")
            params["status"] = status.upper()
        if vencimento_inicio:
            where_parts.append("vencimento >= :vi")
            params["vi"] = vencimento_inicio
        if vencimento_fim:
            where_parts.append("vencimento <= :vf")
            params["vf"] = vencimento_fim

        where = " AND ".join(where_parts)
        rows = (
            (
                await self.db.execute(
                    text(f"""
                    SELECT id, cobranca_id_inter, seu_numero, valor, vencimento,
                           status, pagador, url_boleto, pix_copia_cola,
                           barcode, linha_digitavel, descricao, created_at
                    FROM inter_cobrancas
                    WHERE {where}
                    ORDER BY created_at DESC
                    LIMIT :limit
                """),
                    params,
                )
            )
            .mappings()
            .all()
        )
        return [dict(r) for r in rows]

    async def emitir(
        self,
        cliente_crm_id: str,
        valor: float,
        vencimento: date,
        descricao: str = "",
        pagador: dict | None = None,
    ) -> dict[str, Any]:
        """Emite cobrança: grava em DB → chama Inter API → atualiza com cobranca_id_inter."""
        import uuid

        local_id = str(uuid.uuid4())
        seu_numero = f"CPRO-{local_id[:8].upper()}"

        await self.db.execute(
            text("""
                INSERT INTO inter_cobrancas
                    (id, seu_numero, valor, vencimento, status, descricao, pagador, created_at, updated_at)
                VALUES
                    (:id, :seu_numero, :valor, :vencimento, 'PENDENTE', :descricao,
                     cast(:pagador as jsonb), NOW(), NOW())
            """),
            {
                "id": local_id,
                "seu_numero": seu_numero,
                "valor": valor,
                "vencimento": vencimento,
                "descricao": descricao,
                "pagador": __import__("json").dumps(pagador or {}),
            },
        )
        await self.db.commit()

        import os

        from modules.integrations.banking.adapters.base import BankCredentials
        from modules.integrations.banking.adapters.inter import InterAdapter

        adapter = InterAdapter(
            BankCredentials(
                client_id=os.getenv("INTER_CLIENT_ID", ""),
                client_secret=os.getenv("INTER_CLIENT_SECRET", ""),
                certificate_path=os.getenv("INTER_CERT_PATH"),
                private_key_path=os.getenv("INTER_KEY_PATH"),
                environment=os.getenv("INTER_ENVIRONMENT", "production"),
            )
        )

        cobranca_id_inter: str | None = None
        url_boleto: str | None = None
        pix_copia_cola: str | None = None
        barcode: str | None = None
        linha_digitavel: str | None = None
        novo_status = "PENDENTE"

        try:
            autenticado = await adapter.authenticate()
            if autenticado:
                # assinatura real do adapter (amount/due_date/payer_*): os kwargs antigos davam
                # TypeError engolido e a cobrança ficava PENDENTE para sempre (revisão 08/09/2026)
                _pag = pagador or {}
                result = await adapter.generate_boleto(
                    amount=Decimal(str(valor)),
                    due_date=vencimento,
                    payer_name=str(_pag.get("nome") or _pag.get("name") or "Cliente"),
                    payer_document=str(_pag.get("cpfCnpj") or _pag.get("cpf_cnpj") or _pag.get("documento") or ""),
                    description=descricao,
                    seu_numero=seu_numero,
                )
                cobranca_id_inter = result.get("codigoSolicitacao") or result.get("nosso_numero")
                url_boleto = result.get("linkBoleto") or result.get("url_boleto")
                pix_copia_cola = result.get("pixCopiaECola") or result.get("pix_copia_cola")
                barcode = result.get("codigoBarras") or result.get("barcode")
                linha_digitavel = result.get("linhaDigitavel") or result.get("linha_digitavel")
                novo_status = "A_RECEBER"
        except Exception as exc:
            logger.warning("D6.3 emitir: Inter API falhou (%s) — mantendo PENDENTE", exc)
        finally:
            await adapter.close()

        await self.db.execute(
            text("""
                UPDATE inter_cobrancas
                SET cobranca_id_inter = :cid,
                    url_boleto        = :url,
                    pix_copia_cola    = :pix,
                    barcode           = :barcode,
                    linha_digitavel   = :ld,
                    status            = :status,
                    updated_at        = NOW()
                WHERE id = :id
            """),
            {
                "cid": cobranca_id_inter,
                "url": url_boleto,
                "pix": pix_copia_cola,
                "barcode": barcode,
                "ld": linha_digitavel,
                "status": novo_status,
                "id": local_id,
            },
        )
        await self.db.commit()

        logger.info("D6.3 emitir: id=%s cid=%s status=%s", local_id, cobranca_id_inter, novo_status)
        return {
            "id": local_id,
            "cobranca_id_inter": cobranca_id_inter,
            "seu_numero": seu_numero,
            "valor": valor,
            "vencimento": vencimento.isoformat(),
            "status": novo_status,
            "url_boleto": url_boleto,
            "pix_copia_cola": pix_copia_cola,
            "barcode": barcode,
            "linha_digitavel": linha_digitavel,
        }

    async def estatisticas(self) -> dict[str, Any]:
        """Totais agrupados por status."""
        rows = (
            (
                await self.db.execute(
                    text("""
                    SELECT status, COUNT(*) AS qtd, SUM(valor) AS total
                    FROM inter_cobrancas
                    GROUP BY status
                    ORDER BY status
                """),
                )
            )
            .mappings()
            .all()
        )
        return {"por_status": [{"status": r["status"], "qtd": r["qtd"], "total": float(r["total"] or 0)} for r in rows]}
