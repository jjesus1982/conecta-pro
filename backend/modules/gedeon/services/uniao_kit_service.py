"""GEDEON — o kit é UM só: junta o que está no banco com o que está no Drive.

Medido em 19/08/2026, conferindo os kits de julho com a mesma régua dos dois lados:

    Ideal Flores    banco 74%   Drive 50%
      banco tem ponto, NFS-e e boleto que o Drive NÃO tem
      Drive tem 5 CNDs e o banco registrou 2

Não era número errado: eram duas COLEÇÕES diferentes. Os PDFs que o montador gera vivem em
`/app/uploads`, viram slot e nunca sobem ao Drive; os arquivos que os blocos do GEDEON põem
na pasta do condomínio nunca viram slot. O kit real sempre foi a união, e nenhuma das duas
telas mostrava isso — o Jordan conferia em dois lugares e via dois kits.

Mão dupla, e as duas direções são necessárias:
  A. slot com arquivo em disco  →  sobe para a pasta do condomínio (é o que o cliente recebe)
  B. arquivo na pasta           →  vira slot (é o que a completude e o painel enxergam)

Idempotente nas duas pontas: não sobe o que já está lá, não cria slot repetido.
"""

from __future__ import annotations

import logging
import os

from sqlalchemy import text

from modules.gdrive.services.gdrive_service import gdrive_service
from modules.gedeon.services.drive_kit_classifier import classify_filename
from modules.gedeon.services.kit_layout import _arquivo_ja_existe, pasta_kit_arquivo

logger = logging.getLogger(__name__)

_RAIZ_UPLOADS = "/app/uploads"

_SQL_KITS = text(
    """
    SELECT k.id::text AS kit_id, g.name AS cond
      FROM ged_document_kits k
      JOIN ged_clients g ON g.id = k.client_id
     WHERE k.reference_month = CAST(:mes AS date)
     ORDER BY g.name
    """
)

_SQL_SLOTS = text(
    "SELECT id::text AS id, document_type, document_name, file_path FROM ged_kit_documents "
    " WHERE kit_id = CAST(:kid AS uuid) AND coalesce(file_path,'') <> ''"
)

_SQL_TIPOS_DO_KIT = text(
    "SELECT document_type, coalesce(document_name,'') AS nome FROM ged_kit_documents  WHERE kit_id = CAST(:kid AS uuid)"
)

_SQL_INSERE_SLOT = text(
    "INSERT INTO ged_kit_documents (id, kit_id, document_type, document_name, file_path, "
    "  source_module, auto_generated, is_signed, created_at, updated_at) "
    "VALUES (gen_random_uuid(), CAST(:kid AS uuid), :dt, :dn, :fp, 'drive', true, false, NOW(), NOW())"
)


# ── DOCUMENTO DO TRABALHADOR SÓ SOBE ASSINADO ────────────────────────────────
#
# Desenho do GEDEON, na palavra do Jordan (21/08/2026): *"todos os documentos do
# trabalhador — contracheque, recibo de VT e VA — devem ser assinados pelo funcionário; o
# sistema gera, disponibiliza no portal, ele assina, e ISSO sobe para o kit"*.
#
# A primeira versão desta união subia TODO slot que tivesse arquivo em disco, assinado ou
# não. Medido em 21/08: 38 comprovantes de salário, 7 contracheques, 7 folhas de ponto e 7
# recibos nos kits, ZERO assinados — kit anunciado 100% com papel sem valor probatório.
#
# Documento da EMPRESA (guia, certidão, NF, boleto) não tem assinatura de funcionário e
# continua subindo normalmente: a trava é só para o que é do trabalhador.
_DOC_DO_TRABALHADOR: dict[str, str] = {
    "contracheque": "payslip",
    "contracheques_consolidado": "payslip",
    "recibo_folha": "payslip",
    "comp_salario_individual": "payslip",
    "recibo_vt_va": "recibo_vt_vr",
    "vale_vt_vr": "recibo_vt_vr",
    "comp_vt_individual": "recibo_vt_vr",
    "comp_va_solides": "recibo_vt_vr",
    "comp_vt_va_combinado": "recibo_vt_vr",
    "folha_ponto": "espelho_ponto",
    "folhas_ponto": "espelho_ponto",
    "folhas_ponto_consolidado": "espelho_ponto",
    "contrato_trabalho": "contract",
}

#: Existe assinatura VÁLIDA para este arquivo? Válida = status assinado E PDF selado em
#: disco. Só o status não basta: em 21/08, 42 de 51 registros diziam assinado sem arquivo.
_SQL_TEM_ASSINATURA = text(
    "SELECT signed_document_path FROM sig_signature_requests "
    " WHERE document_type = :dt AND status IN ('SIGNED','COMPLETED') "
    "   AND coalesce(signed_document_path,'') <> '' "
    "   AND (CAST(document_id AS text) = :ref OR coalesce(document_name,'') = :nome) "
    " ORDER BY signed_at DESC NULLS LAST LIMIT 1"
)


#: Marcas de que o arquivo é o COMPROVANTE DE PAGAMENTO ao fornecedor (Sólides/Sinetran),
#: documento da EMPRESA — não do trabalhador. O classificador dá o mesmo slug e o mesmo
#: escopo "funcionario" para os dois: "Comprovante de Pagamento Vale Alimentação (Sólides)
#: - R$ 4.928,00" e "Recibo de Vale Transporte e Vale Alimentacao - Nailson Garcia" caem
#: ambos em comp_va_solides/comp_vt_va_combinado. O que separa é o nome trazer FORNECEDOR
#: e VALOR em vez de pessoa. Sem esta distinção, exigir assinatura removeria os 14
#: comprovantes de pagamento legítimos dos kits.
_MARCAS_DE_FORNECEDOR = ("(sólides)", "(solides)", "(sinetran)", "r$")


def _e_documento_de_pessoa(nome_arquivo: str) -> bool:
    """False quando o arquivo é comprovante ao fornecedor, não documento do trabalhador."""
    n = (nome_arquivo or "").lower()
    return not any(m in n for m in _MARCAS_DE_FORNECEDOR)


def _assinatura_valida(db, document_type: str, ref: str, nome: str) -> str | None:
    """Caminho do PDF SELADO, se existir em disco. None = não pode subir para o kit."""
    dt = _DOC_DO_TRABALHADOR.get(document_type)
    if not dt or not _e_documento_de_pessoa(nome):
        return ""  # documento da empresa: sobe o original mesmo
    try:
        p = db.execute(_SQL_TEM_ASSINATURA, {"dt": dt, "ref": ref or "", "nome": nome or ""}).scalar()
    except Exception as exc:  # noqa: BLE001
        logger.warning("consulta de assinatura falhou (%s): %s", document_type, exc)
        return None
    return p if p and os.path.exists(p) else None


def _caminho_local(fp: str) -> str | None:
    """O slot guarda ora caminho absoluto, ora relativo a /app/uploads. Aceita os dois."""
    if not fp or fp.startswith("http"):
        return None
    p = fp if os.path.isabs(fp) else os.path.join(_RAIZ_UPLOADS, fp)
    return p if os.path.exists(p) else None


def _arquivos_do_kit_no_drive(cond: str, competencia: str) -> list[dict]:
    """Todos os arquivos das subpastas do kit daquele condomínio/mês.

    🔴 NÃO procure a pasta do condomínio por conta própria. Existem pastas DUPLICADAS na
    raiz do workspace — medido em 19/08/2026: duas "CONDOMINIO DO EDIFICIO MICHELANGELO" e,
    no Ideal Flores, uma segunda com caixa diferente ("Condominio Ideal Flores da Cidade").
    A primeira versão desta função fazia `files().list(name=...)` e pegava `[0]`; no
    Michelangelo caiu na duplicata VAZIA e a união enxergou ZERO arquivos com 53 na pasta
    certa — o kit ficou em 74% enquanto o Drive dizia 100%.

    `garantir_pasta_kit` resolve isso: quando há duplicata, `_criar_pasta` escolhe a de
    MAIS conteúdo, contando a subárvore. Uma regra, um lugar.
    """
    from modules.gedeon.services.kit_layout import garantir_pasta_kit

    svc = gdrive_service._service
    pasta_mes = garantir_pasta_kit(cond, competencia)
    if not pasta_mes:
        return []
    out: list[dict] = []
    subs = (
        svc.files()
        .list(
            q=f"'{pasta_mes}' in parents and mimeType='application/vnd.google-apps.folder' and trashed=false",
            fields="files(id,name)",
            supportsAllDrives=True,
            includeItemsFromAllDrives=True,
        )
        .execute()
        .get("files", [])
    )
    for sub in subs:
        arqs = (
            svc.files()
            .list(
                q=f"'{sub['id']}' in parents and trashed=false",
                fields="files(id,name,webViewLink,mimeType)",
                pageSize=300,
                supportsAllDrives=True,
                includeItemsFromAllDrives=True,
            )
            .execute()
            .get("files", [])
        )
        out += [a for a in arqs if not a["mimeType"].endswith("folder")]
    return out


def unir_kit_drive_banco(competencia: str, db, dry_run: bool = False) -> dict:
    """Junta as duas metades do kit, nas duas direções. Não faz commit — é do chamador."""
    from modules.gedeon.services.completude_slots import recalcular_competencia

    if not gdrive_service._service:
        gdrive_service.check_status()

    mes_ref = _mes_referencia(competencia)
    rel: dict = {
        "competencia": competencia,
        "mes_ref": mes_ref,
        "subiu_pro_drive": 0,
        "virou_slot": 0,
        "sem_classificacao": [],
        "sem_assinatura": 0,
        "por_kit": {},
        "falhas": 0,
    }
    cache: dict = {}

    for k in db.execute(_SQL_KITS, {"mes": mes_ref}).mappings().all():
        cond, kid = k["cond"], k["kit_id"]
        subiu = virou = 0
        try:
            # ── A. o que o banco tem e o Drive não ────────────────────────────
            for s in db.execute(_SQL_SLOTS, {"kid": kid}).mappings().all():
                local = _caminho_local(s["file_path"])
                if not local:
                    continue
                # Documento do trabalhador: sobe a versão ASSINADA, ou não sobe.
                assinado = _assinatura_valida(db, s["document_type"], str(s.get("id") or ""), s["document_name"] or "")
                if assinado is None:
                    rel["sem_assinatura"] += 1
                    continue
                local = assinado or local
                fn = s["document_name"] or os.path.basename(local)
                if not fn.lower().endswith(".pdf"):
                    fn += ".pdf"
                if dry_run:
                    subiu += 1
                    continue
                pasta = pasta_kit_arquivo(cond, competencia, fn, cache)
                if pasta and not _arquivo_ja_existe(pasta, fn):
                    if gdrive_service.fazer_upload_arquivo(local, pasta, fn):
                        subiu += 1

            # ── B. o que o Drive tem e o banco não ────────────────────────────
            ja_tem = {r["document_type"] for r in db.execute(_SQL_TIPOS_DO_KIT, {"kid": kid}).mappings()}
            nomes_no_kit = {r["nome"] for r in db.execute(_SQL_TIPOS_DO_KIT, {"kid": kid}).mappings()}
            for a in _arquivos_do_kit_no_drive(cond, competencia):
                slug, _escopo, _ = classify_filename(a["name"])
                if not slug:
                    rel["sem_classificacao"].append(a["name"][:60])
                    continue
                # Documento por condomínio: um por tipo basta. Por funcionário: um por nome.
                if slug in ja_tem and a["name"] in nomes_no_kit:
                    continue
                if slug in ja_tem and _escopo != "funcionario":
                    continue
                if dry_run:
                    virou += 1
                    continue
                db.execute(
                    _SQL_INSERE_SLOT,
                    {
                        "kid": kid,
                        "dt": slug,
                        "dn": a["name"],
                        "fp": a.get("webViewLink") or "",
                    },
                )
                ja_tem.add(slug)
                nomes_no_kit.add(a["name"])
                virou += 1
        except Exception as exc:  # noqa: BLE001 — um kit ruim não cala os outros seis
            rel["falhas"] += 1
            logger.warning("uniao do kit %s (%s): %s", cond, kid, exc)

        rel["subiu_pro_drive"] += subiu
        rel["virou_slot"] += virou
        if subiu or virou:
            rel["por_kit"][cond] = {"subiu": subiu, "virou_slot": virou}

    if not dry_run:
        recalcular_competencia(db, mes_ref)
    rel["sem_classificacao"] = sorted(set(rel["sem_classificacao"]))[:12]
    return rel


def _mes_referencia(competencia: str) -> str:
    """'07.2026' -> '2026-08-01'. O kit da competência X tem reference_month em X+1 —
    mesma convenção da pasta do Drive, que se chama pelo mês de ENTREGA."""
    m, a = int(competencia.split(".")[0]), int(competencia.split(".")[1])
    return f"{a + 1}-01-01" if m == 12 else f"{a}-{m + 1:02d}-01"
