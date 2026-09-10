"""
Helper único de solicitação de assinatura para os geradores de documento.

Todo gerador de PDF que produz um documento assinável chama UMA função daqui —
`garantir_solicitacao_assinatura` (async) ou `garantir_solicitacao_assinatura_sync`
(para endpoints síncronos, ex. folha) — passando o tipo do documento, o id e o
contexto (funcionário, cliente). O helper:

1. Aplica a POLÍTICA DE ASSINANTE por tipo de documento (definida pelo Jordan):
     contract       → EMPLOYEE + COMPANY
     proposal       → COMPANY + CUSTOMER
     recibo_vt_vr   → EMPLOYEE
     payslip        → EMPLOYEE
     aviso_previo   → EMPLOYEE + COMPANY
     rescisao       → EMPLOYEE + COMPANY
     licitacao      → COMPANY
   (ficha_epi NÃO passa por aqui — continua no fluxo portal_digital_signatures.)

2. É IDEMPOTENTE: se já existe solicitação para (document_type, document_id),
   não cria outra — devolve o status atual. Assim, gerar o PDF N vezes não
   duplica signatários.

3. NUNCA quebra a geração do PDF: qualquer erro aqui é logado e engolido
   (retorna None), pois a assinatura é um efeito colateral do gerador — o
   download do documento não pode falhar por causa dela.

O motor (UniversalSignatureService) é consumido exatamente pelo contrato
publicado; este helper apenas monta os SignerInput conforme a política.
"""

from __future__ import annotations

import hashlib
import logging
import uuid
from typing import Any

from sqlalchemy import text as sa_text
from sqlalchemy.ext.asyncio import AsyncSession

from modules.signatures.services.universal_signature_service import (
    SignatureLevel,
    SignerInput,
    SignerType,
    UniversalSignatureService,
)

logger = logging.getLogger(__name__)

# Empresa (assinante COMPANY) — razão social/CNPJ por empresa (multi-CNPJ).
# A empresa dona do doc é resolvida em `garantir_solicitacao_assinatura` (pelo CPF
# do funcionário, ou explícita) e grava-se `empresa_slug` no request; o assinador
# ICP-Brasil (qualified_signer) escolhe o certificado A1 desse CNPJ.
EMPRESA_REPRESENTANTE = "JORDAN JESUS"
_EMPRESA_ASSINANTE: dict[str, dict[str, str]] = {
    "conecta_eletronica": {"razao": "CONECTAMAIS ELETRONICA LTDA", "cnpj": "35.710.481/0001-03"},
    "conecta_patrimonial": {"razao": "CONECTAMAIS PATRIMONIAL LTDA", "cnpj": "66.014.833/0001-10"},
}
_EMPRESA_SLUG_DEFAULT = "conecta_eletronica"


def _empresa_assinante(empresa_slug: str | None) -> dict[str, str]:
    return _EMPRESA_ASSINANTE.get(empresa_slug or _EMPRESA_SLUG_DEFAULT, _EMPRESA_ASSINANTE[_EMPRESA_SLUG_DEFAULT])


# Política: quais tipos de assinante cada tipo de documento exige, na ordem.
#   contract          → contrato de TRABALHO (funcionário + empresa)
#   service_contract  → contrato de SERVIÇO com cliente (cliente + empresa)
POLITICA_ASSINANTES: dict[str, list[SignerType]] = {
    "contract": [SignerType.EMPLOYEE, SignerType.COMPANY],
    "service_contract": [SignerType.CUSTOMER, SignerType.COMPANY],
    # `contrato`, em português, é o que o CRM grava de verdade
    # (`contract_signature.abrir_assinatura`). Não estava declarado aqui: caía no default,
    # calado. Achado em 09/09/2026 pelo cruzamento entre o vocabulário DECLARADO e o
    # GRAVADO — a política afirmava `service_contract` e o banco tinha `contrato`.
    # Mesmos signatários do `service_contract`, porque é o mesmo documento: contrato de
    # serviço com cliente.
    "contrato": [SignerType.CUSTOMER, SignerType.COMPANY],
    # Mapa de empregados: a empresa emite e assina sozinha. Declarado para sair do default;
    # o NÍVEL fica como está (simples) — promover a assinatura de um documento é decisão do
    # dono, não consequência de eu ter descoberto que ele existe.
    "mapa_empregados": [SignerType.COMPANY],
    "proposal": [SignerType.COMPANY, SignerType.CUSTOMER],
    # ⚠️ MUDANÇA DE DECISÃO — Jordan, 21/08/2026, revoga a de 05/08/2026.
    # Holerite e recibo de VT/VR passam a ser assinados SÓ PELO FUNCIONÁRIO. Antes eram
    # co-assinados ("selos empilhados") e a empresa nunca assinava: em 21/08 havia 67
    # holerites e 51 recibos PENDING no lado COMPANY, travando 118 documentos que o
    # funcionário não conseguia concluir sozinho. Só 3 de 107 recibos foram assinados
    # desde 15/07 — a contraparte nunca vinha.
    #
    # A regra, na palavra dele: "contracheque e recibo de vt e vr assinados apenas pelos
    # funcionários; folha de ponto pelas duas partes, empresa e funcionários; contratos de
    # trabalho e prorrogações assinados pelas duas partes".
    "recibo_vt_vr": [SignerType.EMPLOYEE],
    "payslip": [SignerType.EMPLOYEE],
    # Espelho de ponto mensal (Portaria 671): FUNCIONÁRIO homologa (eletrônica) + EMPRESA
    # co-assina (qualificada ICP-Brasil). Decisão Jordan (2026-08-05): selos empilhados.
    "espelho_ponto": [SignerType.EMPLOYEE, SignerType.COMPANY],
    # Prorrogação de contrato de experiência segue o contrato: duas partes.
    "prorrogacao_contrato": [SignerType.EMPLOYEE, SignerType.COMPANY],
    "aviso_previo": [SignerType.EMPLOYEE, SignerType.COMPANY],
    "rescisao": [SignerType.EMPLOYEE, SignerType.COMPANY],
    "licitacao": [SignerType.COMPANY],
    # Documento do KIT GEDEON (contracheque/ponto/VT-VA-VR/contrato/ficha/férias/
    # aviso/rescisão montados no kit por condomínio) → o FUNCIONÁRIO assina.
    # A empresa NÃO co-assina docs do kit; ficha_epi tem fluxo próprio (fora daqui).
    "kit_documento": [SignerType.EMPLOYEE],
    # 09/09/2026: espelho de ponto e escala do kit trazem o campo do diretor — funcionário E empresa assinam
    "kit_documento_coassinado": [SignerType.EMPLOYEE, SignerType.COMPANY],
    # COMUNICADO INTERNO: a EMPRESA emite+assina (qualificada, cert A1 do CNPJ) e
    # cada FUNCIONÁRIO dá CIÊNCIA (eletrônica simples). A publicação em massa (1
    # empresa + N funcionários) usa `publicar_comunicados_patrimonial.py`; esta
    # política cobre também o caso 1×1 pelo helper padrão.
    "comunicado": [SignerType.COMPANY, SignerType.EMPLOYEE],
}

# Política de NÍVEL legal por (document_type). Decisão do Jordan:
#   Assinatura QUALIFICADA ICP-Brasil (A1) SÓ para CONTRATOS — e somente do lado
#   da EMPRESA (COMPANY), que é a titular do certificado. Funcionário e cliente
#   não têm certificado próprio: assinam sempre em nível SIMPLE (SHA-256).
#   Todos os demais document_types usam SIMPLE para todos os signatários.
# `payslip` e `recibo_vt_vr` saíram: sem signatário COMPANY, estar aqui era letra morta —
# `nivel_assinatura` só devolve QUALIFIED para COMPANY. Manter confundiria quem lesse.
DOCUMENTOS_QUALIFICADOS: frozenset[str] = frozenset(
    {
        "contract",
        "service_contract",
        # ⚠️ "contrato", em português, é o tipo que o CRM grava de verdade
        # (`contract_signature.abrir_assinatura`, linha 69). Os dois vocabulários convivem
        # nesta casa — `contract`/`service_contract` vêm do DP, `contrato` vem do comercial —
        # e a lista só conhecia o inglês. Resultado medido em 09/09/2026: holerite e espelho
        # de ponto assinavam com o A1 ICP-Brasil e **o CONTRATO assinava em nível simples**,
        # justamente o documento com mais consequência jurídica.
        #   nivel_assinatura("contrato", COMPANY)  → simple      (antes)
        #   nivel_assinatura("contract", COMPANY)  → qualified
        # Conferido antes de ligar: os dois certificados A1 abrem —
        # Eletrônica (35.710.481/0001-03) até 13/01/2027, Patrimonial até 06/07/2027 —
        # então isto promove a assinatura, não a quebra.
        "contrato",
        "comunicado",
        "espelho_ponto",
        "prorrogacao_contrato",
        # 09/09/2026: documento do kit com o campo do diretor (espelho, recibo de adiantamento) — a empresa assina
        # com o A1 ICP-Brasil, como já faz no espelho fora do kit ("já funciona assim hoje", Jordan)
        "kit_documento_coassinado",
    }
)


def nivel_assinatura(document_type: str, signer_type: SignerType) -> SignatureLevel:
    """Nível legal exigido para (document_type × signer_type).

    Regra única e testável:
      - COMPANY assinando um CONTRATO (contract | service_contract) → QUALIFIED (A1).
      - Qualquer outro caso (outros tipos de doc, ou EMPLOYEE/CUSTOMER) → SIMPLE.

    Args:
        document_type: Tipo do documento.
        signer_type: Tipo do assinante.

    Returns:
        SignatureLevel.QUALIFIED ou SignatureLevel.SIMPLE.
    """
    if signer_type == SignerType.COMPANY and document_type in DOCUMENTOS_QUALIFICADOS:
        return SignatureLevel.QUALIFIED
    return SignatureLevel.SIMPLE


def document_hash_sha256(pdf_bytes: bytes | None) -> str | None:
    """SHA-256 (hex) do conteúdo do PDF, quando os bytes estiverem disponíveis."""
    if not pdf_bytes:
        return None
    return hashlib.sha256(pdf_bytes).hexdigest()


def _build_signers(
    tipos: list[SignerType],
    *,
    employee_id: uuid.UUID | str | None,
    employee_name: str | None,
    employee_document: str | None,
    customer_name: str | None,
    customer_email: str | None,
    customer_document: str | None,
    company_signer_id: uuid.UUID | str | None,
    empresa_slug: str | None = None,
) -> list[SignerInput]:
    """Monta os SignerInput na ordem da política, a partir do contexto do doc."""
    emp = _empresa_assinante(empresa_slug)
    signers: list[SignerInput] = []
    for idx, tipo in enumerate(tipos, start=1):
        if tipo == SignerType.EMPLOYEE:
            signers.append(
                SignerInput(
                    signer_type=SignerType.EMPLOYEE,
                    signer_name=employee_name or "Funcionário",
                    signer_id=_coerce_uuid(employee_id),
                    signer_document=employee_document,
                    order=idx,
                )
            )
        elif tipo == SignerType.COMPANY:
            signers.append(
                SignerInput(
                    signer_type=SignerType.COMPANY,
                    signer_name=f"{emp['razao']} ({EMPRESA_REPRESENTANTE})",
                    signer_id=_coerce_uuid(company_signer_id),
                    signer_document=emp["cnpj"],
                    order=idx,
                )
            )
        elif tipo == SignerType.CUSTOMER:
            signers.append(
                SignerInput(
                    signer_type=SignerType.CUSTOMER,
                    signer_name=customer_name or "Cliente",
                    signer_email=customer_email,
                    signer_document=customer_document,
                    order=idx,
                )
            )
    return signers


async def _empresa_slug_por_cpf(db: AsyncSession, cpf: str | None) -> str | None:
    """Resolve a empresa dona do vínculo (empresas.slug) pelo CPF do funcionário.
    None se sem CPF ou sem match — o assinador cai na Eletrônica (default seguro)."""
    import re

    from sqlalchemy import text

    digitos = re.sub(r"\D", "", str(cpf or ""))
    if not digitos:
        return None
    try:
        row = await db.execute(
            text(
                "SELECT e.slug FROM employees emp JOIN empresas e ON e.id = emp.empresa_id "
                "WHERE REGEXP_REPLACE(COALESCE(emp.cpf,''),'[^0-9]','','g') = :cpf LIMIT 1"
            ),
            {"cpf": digitos},
        )
        r = row.first()
        return r[0] if r else None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha ao resolver empresa por CPF na assinatura: %s", exc)
        return None


def _coerce_uuid(value: uuid.UUID | str | None) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError):
        return None


async def garantir_solicitacao_assinatura(
    db: AsyncSession,
    *,
    document_type: str,
    document_id: str,
    title: str,
    document_hash: str | None = None,
    document_path: str | None = None,
    employee_id: uuid.UUID | str | None = None,
    employee_name: str | None = None,
    employee_document: str | None = None,
    customer_name: str | None = None,
    customer_email: str | None = None,
    customer_document: str | None = None,
    company_signer_id: uuid.UUID | str | None = None,
    requested_by: uuid.UUID | str | None = None,
    empresa_slug: str | None = None,
) -> dict[str, Any] | None:
    """Garante que exista uma solicitação de assinatura para o documento (idempotente).

    Aplica a POLÍTICA por document_type e chama o motor. Se já houver solicitação,
    devolve o status atual sem criar outra. Erros são engolidos (retorna None) para
    nunca quebrar a geração do PDF.

    `empresa_slug` (empresas.slug) define QUAL CNPJ assina (certificado A1 e razão
    social do signatário COMPANY). Se None, é resolvido pelo CPF do funcionário
    (`employee_document`); sem isso, cai na Eletrônica (default seguro, multi-CNPJ).

    Returns:
        dict com o resultado do motor (chave "created": bool). Para propostas,
        inclui "public_token" do link do cliente. None em caso de erro.
    """
    tipos = POLITICA_ASSINANTES.get(document_type)
    if not tipos:
        # Documento sem política de assinatura (ex.: NFS-e) — nada a fazer.
        return None

    try:
        svc = UniversalSignatureService(db)

        # Idempotência: já existe solicitação para este documento?
        atual = await svc.status(document_type=document_type, document_id=str(document_id))
        if atual.get("total_signers", 0) > 0:
            # 10/09/2026 (kit real do Michelangelo): o pedido guarda o CAMINHO do arquivo, e o arquivo pode ser
            # regerado depois — o espelho de ponto nasceu .html e virou .pdf. O pedido continuava apontando para
            # o .html e a assinatura morria na hora de estampar o selo ("is no PDF"), já com o funcionário na tela.
            # Só os PENDENTES seguem o arquivo novo: em pedido já assinado o caminho é evidência e não se mexe.
            if document_path:
                await db.execute(
                    sa_text(
                        "UPDATE sig_signature_requests SET document_path = :p, updated_at = now() "
                        "WHERE document_type = :t AND CAST(document_id AS TEXT) = :d "
                        "AND status = 'PENDING' AND coalesce(document_path,'') <> :p"
                    ),
                    {"p": document_path, "t": document_type, "d": str(document_id)},
                )
                await db.commit()
            atual["created"] = False
            atual["public_token"] = _extract_public_token(atual)
            return atual

        # Empresa dona do doc (multi-CNPJ): explícita, ou resolvida pelo CPF do
        # funcionário. Sem match → None → Eletrônica (default seguro no assinador).
        if not empresa_slug and employee_document:
            empresa_slug = await _empresa_slug_por_cpf(db, employee_document)

        signers = _build_signers(
            tipos,
            employee_id=employee_id,
            employee_name=employee_name,
            employee_document=employee_document,
            customer_name=customer_name,
            customer_email=customer_email,
            customer_document=customer_document,
            company_signer_id=company_signer_id,
            empresa_slug=empresa_slug,
        )

        result = await svc.criar_solicitacao_assinatura(
            document_type=document_type,
            document_id=str(document_id),
            signers=signers,
            title=title,
            document_hash=document_hash,
            document_path=document_path,
            requested_by=_coerce_uuid(requested_by),
            metadata={"empresa_slug": empresa_slug or _EMPRESA_SLUG_DEFAULT},
        )
        result["created"] = True
        # Expõe o token do cliente (proposta) no topo, para o endpoint devolver o link.
        for r in result.get("requests", []):
            if r.get("public_token"):
                result["public_token"] = r["public_token"]
                break
        return result
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "Falha ao garantir solicitação de assinatura (doc_type=%s doc_id=%s): %s",
            document_type,
            document_id,
            exc,
        )
        return None


def _extract_public_token(status: dict[str, Any]) -> str | None:
    """Token do cliente não é exposto pelo status(); devolvido só na criação."""
    return None


def _engine_sync_nullpool():
    """Engine DEDICADA com NullPool para os helpers `_sync` (asyncio.run cria um loop
    novo a cada chamada; o pool GLOBAL prende conexões asyncpg ao loop de origem → erro
    'got Future attached to a different loop'). NullPool abre/fecha conexão por uso."""
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from core.config import settings

    eng = create_async_engine(settings.database_url, poolclass=NullPool)
    return eng, async_sessionmaker(eng, class_=AsyncSession, expire_on_commit=False)


def _rodar_sync(corotina_factory):
    """Wrapper histórico — a regra mora em `core.async_utils.rodar_corotina`, que nasceu aqui."""
    from core.async_utils import rodar_corotina

    return rodar_corotina(corotina_factory, timeout=120)


def status_documento_sync(document_type: str, document_id: str) -> dict[str, Any] | None:
    """Versão síncrona de status() para endpoints `def` (ex.: folha/recibo VT-VR)."""

    async def _run() -> dict[str, Any] | None:
        eng, factory = _engine_sync_nullpool()
        try:
            async with factory() as session:
                return await UniversalSignatureService(session).status(
                    document_type=document_type, document_id=str(document_id)
                )
        finally:
            await eng.dispose()

    try:
        return _rodar_sync(_run)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha ao consultar status de assinatura (sync): %s", exc)
        return None


def garantir_solicitacao_assinatura_sync(**kwargs: Any) -> dict[str, Any] | None:
    """Versão síncrona para endpoints `def` (ex.: folha/recibo VT-VR).

    Abre uma AsyncSession própria de curta duração e roda o fluxo async.
    Seguro em rotas síncronas do FastAPI (executam num worker thread sem event
    loop). Nunca quebra o chamador: erros retornam None.
    """

    async def _run() -> dict[str, Any] | None:
        eng, factory = _engine_sync_nullpool()
        try:
            async with factory() as session:
                return await garantir_solicitacao_assinatura(session, **kwargs)
        finally:
            await eng.dispose()

    try:
        return _rodar_sync(_run)
    except RuntimeError:
        # Já existe event loop rodando neste contexto — cai fora sem quebrar o PDF.
        logger.warning("garantir_solicitacao_assinatura_sync chamado dentro de event loop ativo; ignorado.")
        return None
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha na solicitação de assinatura (sync): %s", exc)
        return None
