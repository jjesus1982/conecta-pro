"""Kit marcado como ENVIADO tem de ter arquivo e destinatário. Sempre.

🔴 O DEFEITO, medido em 14/08/2026. O ÚNICO kit marcado como enviado em oito meses:

    2026-03 · CONDOMINIO DO EDIFICIO MICHELANGELO · sent_at 05/05/2026
    zip_file_path    = vazio
    google_drive_link = vazio

Um "enviado" sem nada anexado. E a rota que o marcou (`auto_assemble_controller`, o endpoint
cujo docstring diz "Envia kit ao cliente") **não enviava nada** — trocava o status e gravava
`sent_at`, checando só assinaturas. Nenhuma verificação de arquivo ou de destinatário.

O painel conta esse kit como entregue. O cliente nunca recebeu documento nenhum. **Marcar
entrega sem prova de entrega é a mesma família de fabricação que o projeto proíbe no dado** —
e aqui ela mente sobre uma obrigação com o cliente, não sobre um número de tela.

⚠️ E O DESTINATÁRIO NÃO ESTÁ CADASTRADO: os 21 clientes têm e-mail genérico e ZERO têm
`financial_contact_email` ou `technical_contact_email`. Kit trabalhista vai para o síndico ou
para a administradora — não para o e-mail genérico do cadastro por omissão. Este oráculo
trava a checagem; **o dado é do Jordan**, e inventar e-mail de cliente não é opção.

AFIRMA A REGRA, NÃO A FOTOGRAFIA: não fixa "1 kit" nem competência. Varre todos os enviados
a cada rodada e continua valendo quando os 34 kits que hoje estão prontos forem entregues.
"""
from __future__ import annotations

import asyncio
import os
import sys

sys.path.insert(0, os.environ.get("APP_ROOT", "/app"))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import text  # noqa: E402

from core.database.session import async_session_factory  # noqa: E402

SQL_ENVIADOS = text(
    "SELECT k.id::text AS id, to_char(k.reference_month,'YYYY-MM') AS comp, "
    "       coalesce(gc.name,'—') AS cliente, k.sent_at, "
    "       coalesce(k.zip_file_path,'') AS zip, "
    "       coalesce(k.google_drive_link,'') AS drive, "
    "       coalesce(k.sent_to,'') AS destino "
    "FROM ged_document_kits k "
    "LEFT JOIN ged_clients gc ON gc.id = k.client_id "
    "WHERE k.sent_at IS NOT NULL OR lower(coalesce(k.status,'')) = 'enviado' "
    "ORDER BY k.sent_at DESC NULLS LAST"
)


async def main() -> None:
    async with async_session_factory() as db:
        enviados = (await db.execute(SQL_ENVIADOS)).mappings().all()

        sem_arquivo = [r for r in enviados if not (r["zip"] or r["drive"])]
        sem_destino = [r for r in enviados if not r["destino"]]

        problemas = []
        if sem_arquivo:
            problemas.append(
                f"{len(sem_arquivo)} sem arquivo: "
                + "; ".join(f'{r["comp"]} {r["cliente"][:24]}' for r in sem_arquivo[:4])
            )
        if sem_destino:
            problemas.append(
                f"{len(sem_destino)} sem destinatário: "
                + "; ".join(f'{r["comp"]} {r["cliente"][:24]}' for r in sem_destino[:4])
            )
        if problemas:
            raise AssertionError(
                "kit(s) marcados como ENVIADOS sem prova de entrega — " + " | ".join(problemas)
            )

        print(f"OK entrega provada em {len(enviados)} kit(s) enviado(s): "
              f"todos com arquivo e destinatário")

        # suspenders: o caminho de entrega precisa existir ANTES de alguém aprovar em massa.
        # Se há kit em 100% e nenhum enviado, não é erro — é fila esperando decisão humana,
        # e o número precisa aparecer para ninguém achar que o módulo entrega sozinho.
        prontos = (await db.execute(text(
            "SELECT count(*) FROM ged_document_kits "
            "WHERE completion_percentage >= 100 AND sent_at IS NULL"
        ))).scalar()
        print(f"OK {prontos} kit(s) em 100% aguardando decisão de envio "
              f"({len(enviados)} já entregue(s))")

    print("TEST oraculo_entrega_kit PASS")


if __name__ == "__main__":
    asyncio.run(main())
