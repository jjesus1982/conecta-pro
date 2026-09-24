"""Oráculo — A tela de emitir NF-e e o DANFE (frente DGX Z3, 24/09/2026).

Por que existe
--------------
O dono pediu «preciso urgente emitir notas fiscais». Nota fiscal AUTORIZADA em produção é
irreversível: uma vez na SEFAZ, só sai por cancelamento (prazo de 24 h) ou carta de correção,
e os dois deixam rastro no fisco. O caminho rápido para o desastre é uma tela que emite bonito
e transmite no ambiente errado — ou que deixa passar um item sem NCM e devolve «erro 500» em
vez de dizer o que falta.

Este oráculo trava as cinco coisas que não podem afrouxar sem alguém perceber:

  1. **O padrão do ambiente é HOMOLOGAÇÃO.** O campo `ambiente` da tela `nfe-nova` nasce com
     `value == "homologacao"` e a primeira opção do select é a de homologação. Se alguém
     trocar o padrão para produção — por «conveniência» — este oráculo fica VERMELHO.
     Também afirma que produção NÃO transmite pela tela `nfe-nova`: ela só grava rascunho.
  2. **A recusa ensina.** Item sem NCM, destinatário incompleto e CFOP ausente/incompatível
     viram HTTP 422 com uma mensagem que diz o que fazer, não um 500 nem um silêncio.
  3. **O DANFE de homologação traz «SEM VALOR FISCAL»** atravessando o documento (exigência do
     leiaute: DANFE de homologação não vale como documento fiscal). O de produção autorizada
     não traz a faixa.
  4. **Cancelar exige justificativa de 15+ caracteres** — é a regra da SEFAZ (`xJust`,
     mínimo 15, máximo 255), a mesma que `nfe_provider.cancelar_nfe` já impõe.
  5. **A lista mostra o `xMotivo` INTEIRO da rejeitada.** O motivo da rejeição é o que ensina
     a corrigir; truncar em 30 caracteres é o mesmo que esconder.

O que afirma (recontado por conta própria, não pelo serviço)
------------------------------------------------------------
Os itens 1, 3, 4 e 5 leem a TELA e o PDF montados; o item 2 chama as regras puras e confere o
status HTTP levantado. O item 5 usa uma fixture própria em `nfes` marcada
`motivo_rejeicao LIKE 'FIXTURE DGX Z3%'`, apagada no fim — nada de produção é tocado.

Estado medido no nascimento (staging, 24/09/2026)
--------------------------------------------------
`_dgx_z3_tela_nfe` não existia → ImportError, VERMELHO em tudo. A tabela `nfes` tinha 2 notas
(ambas `rejeitada`, emitidas contra o ambiente de PRODUÇÃO pelo controller antigo, que tem
`homologacao=False` fixo) e nenhuma coluna `ambiente` — por isso a coluna nasce aqui e as duas
notas antigas aparecem como «(não registrado)», nunca adivinhadas.

Como roda
---------
    docker run --rm --network conecta-staging-network -v "$WT/backend:/app:ro" \
      -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \
      -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \
      conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_z3_tela_nfe.py

Sai 0 = verde; 1 = vermelho.
"""

from __future__ import annotations

import asyncio
import sys

FIXTURE = "FIXTURE DGX Z3"
#: xMotivo real de uma rejeição da SEFAZ — longo de propósito: é ele que tem de aparecer inteiro.
XMOTIVO = (
    "Rejeicao: Duplicidade de NF-e, com diferenca na Chave de Acesso [chNFe: "
    "13260435710481000103550010000000011596029510] " + FIXTURE
)


def _cab_ok() -> dict:
    """Cabeçalho COMPLETO de uma NF-e válida (o caso que tem de passar)."""
    return {
        "empresa_slug": "conecta_eletronica",
        "emitente_cnpj": "35710481000103",
        "emitente_uf": "AM",
        "natureza_operacao": "VENDA DE MERCADORIA",
        "finalidade": "1",
        "ambiente": "homologacao",
        "serie": 1,
        "destinatario_cpf_cnpj": "04378626000144",
        "destinatario_razao_social": "CONDOMINIO RESIDENCIAL TESTE LTDA",
        "destinatario_ind_ie": "9",
        "destinatario_ie": "",
        "destinatario_uf": "AM",
        "destinatario_logradouro": "Avenida das Torres",
        "destinatario_numero": "1200",
        "destinatario_bairro": "Cidade Nova",
        "destinatario_municipio": "Manaus",
        "destinatario_cod_municipio": "1302603",
        "destinatario_cep": "69097000",
        "modalidade_frete": "9",
        "valor_frete": 0.0,
    }


def _itens_ok() -> list[dict]:
    return [
        {
            "codigo": "CAM-001",
            "descricao": "CAMERA IP DOME 2MP",
            "ncm": "85258900",
            "cfop": "5102",
            "unidade": "UN",
            "quantidade": 2,
            "valor_unitario": 450.0,
            "valor_desconto": 0.0,
        }
    ]


async def main() -> int:  # noqa: PLR0912, PLR0915 — um oráculo é uma lista de afirmações
    falhas: list[str] = []

    try:
        from modules.operacional.controllers.redesign_builders import _dgx_z3_tela_nfe as z3
    except Exception as e:  # noqa: BLE001 — módulo ausente = vermelho honesto, não crash
        print(f"FALHOU: não consegui importar _dgx_z3_tela_nfe: {e}")
        print("TOTAL falhas Z3: 1")
        return 1

    from fastapi import HTTPException
    from sqlalchemy import text

    from core.database import async_session_factory

    # ── 2) a recusa ENSINA (422 com mensagem acionável) ──────────────────────────────────
    def _status_da_recusa(cab, itens) -> tuple[int | None, str]:
        try:
            z3.exigir(z3.validar_nfe(cab, itens))
        except HTTPException as e:
            return e.status_code, str(e.detail)
        return None, ""

    # 2a) passa quando está completo
    cod, det = _status_da_recusa(_cab_ok(), _itens_ok())
    if cod is not None:
        falhas.append(f"nota COMPLETA foi recusada ({cod}): {det}")

    # 2b) item sem NCM
    sem_ncm = _itens_ok()
    sem_ncm[0]["ncm"] = ""
    cod, det = _status_da_recusa(_cab_ok(), sem_ncm)
    if cod != 422:
        falhas.append(f"item sem NCM devolveu {cod}, esperado 422")
    elif "NCM" not in det:
        falhas.append(f"recusa por NCM não diz 'NCM': {det!r}")

    # 2b') NCM com menos de 8 dígitos também é inválido para a SEFAZ
    ncm_curto = _itens_ok()
    ncm_curto[0]["ncm"] = "8525"
    cod, _ = _status_da_recusa(_cab_ok(), ncm_curto)
    if cod != 422:
        falhas.append(f"NCM de 4 dígitos devolveu {cod}, esperado 422")

    # 2c) destinatário incompleto — sem CNPJ, sem endereço, sem IE sendo contribuinte
    for campo in ("destinatario_cpf_cnpj", "destinatario_razao_social", "destinatario_cep", "destinatario_municipio"):
        cab = _cab_ok()
        cab[campo] = ""
        cod, det = _status_da_recusa(cab, _itens_ok())
        if cod != 422:
            falhas.append(f"destinatário sem {campo} devolveu {cod}, esperado 422")

    cab = _cab_ok()
    cab["destinatario_ind_ie"] = "1"  # contribuinte do ICMS → IE obrigatória
    cab["destinatario_ie"] = ""
    cod, det = _status_da_recusa(cab, _itens_ok())
    if cod != 422:
        falhas.append(f"contribuinte do ICMS sem IE devolveu {cod}, esperado 422")
    elif "Inscrição Estadual" not in det and "IE" not in det:
        falhas.append(f"recusa por IE não explica a IE: {det!r}")

    # 2d) CFOP ausente e CFOP incompatível com a UF
    sem_cfop = _itens_ok()
    sem_cfop[0]["cfop"] = ""
    cod, det = _status_da_recusa(_cab_ok(), sem_cfop)
    if cod != 422:
        falhas.append(f"item sem CFOP devolveu {cod}, esperado 422")
    elif "CFOP" not in det:
        falhas.append(f"recusa por CFOP não diz 'CFOP': {det!r}")

    fora = _itens_ok()
    fora[0]["cfop"] = "6102"  # operação interestadual num destinatário do MESMO estado (AM→AM)
    cod, det = _status_da_recusa(_cab_ok(), fora)
    if cod != 422:
        falhas.append(f"CFOP 6xxx com destinatário no mesmo estado devolveu {cod}, esperado 422")

    dentro = _itens_ok()
    dentro[0]["cfop"] = "5102"
    cab = _cab_ok()
    cab["destinatario_uf"] = "SP"  # outro estado exige CFOP 6xxx
    cod, det = _status_da_recusa(cab, dentro)
    if cod != 422:
        falhas.append(f"CFOP 5xxx com destinatário em outro estado devolveu {cod}, esperado 422")

    # ── 4) cancelar exige justificativa de 15+ caracteres (regra da SEFAZ, xJust) ─────────
    try:
        z3.validar_justificativa("erro de digitacao")  # 17 caracteres → passa
    except HTTPException as e:
        falhas.append(f"justificativa de 17 caracteres foi recusada: {e.detail}")
    for curta in ("", "erro", "cancelar nota"):  # 0, 4 e 13 caracteres
        try:
            z3.validar_justificativa(curta)
            falhas.append(f"justificativa de {len(curta)} caracteres passou — a SEFAZ exige 15")
        except HTTPException as e:
            if e.status_code != 422:
                falhas.append(f"justificativa curta devolveu {e.status_code}, esperado 422")

    # ── 3) DANFE: faixa «SEM VALOR FISCAL» em homologação, ausente em produção autorizada ──
    nota_homolog = dict(_cab_ok(), numero=1, chave_acesso="1" * 44, status="autorizada", valor_total_nota=900.0)
    pdf_h = z3.danfe_pdf(nota_homolog, _itens_ok())
    if not pdf_h.startswith(b"%PDF"):
        falhas.append("DANFE de homologação não é um PDF")
    if b"SEM VALOR FISCAL" not in pdf_h:
        falhas.append("DANFE de HOMOLOGAÇÃO não traz a faixa «SEM VALOR FISCAL»")

    nota_prod = dict(nota_homolog, ambiente="producao")
    pdf_p = z3.danfe_pdf(nota_prod, _itens_ok())
    if b"SEM VALOR FISCAL" in pdf_p:
        falhas.append("DANFE de PRODUÇÃO autorizada traz a faixa «SEM VALOR FISCAL» — não deveria")
    # rascunho em produção AINDA não é documento fiscal → faixa obrigatória
    if b"SEM VALOR FISCAL" not in z3.danfe_pdf(dict(nota_prod, status="rascunho"), _itens_ok()):
        falhas.append("DANFE de RASCUNHO em produção não traz a faixa «SEM VALOR FISCAL»")

    # ── 1 e 5) leem o banco ──────────────────────────────────────────────────────────────
    async with async_session_factory() as db:
        await z3._ensure(db)

        # fixture: uma nota REJEITADA com xMotivo longo
        await db.execute(text("DELETE FROM nfes WHERE coalesce(motivo_rejeicao,'') LIKE :p"), {"p": f"%{FIXTURE}%"})
        await db.execute(
            text(
                "INSERT INTO nfes (id, condominio_id, tipo, finalidade, status, serie, numero, "
                " natureza_operacao, data_emissao, emitente_cnpj, emitente_razao_social, emitente_uf, "
                " emitente_crt, destinatario_cpf_cnpj, destinatario_razao_social, destinatario_uf, "
                " destinatario_logradouro, destinatario_numero, destinatario_bairro, "
                " destinatario_municipio, destinatario_cep, modalidade_frete, forma_pagamento, "
                " meio_pagamento, valor_total_nota, motivo_rejeicao, ambiente, active, created_at) "
                "VALUES (gen_random_uuid(), CAST(:cond AS uuid), 'saida', '1', 'rejeitada', 9, 9901, "
                " :nat, now(), '35710481000103', 'CONECTAMAIS ELETRONICA LTDA', 'AM', '3', "
                " '04378626000144', :dest, 'AM', 'Rua Teste', '1', 'Centro', 'Manaus', '69000000', "
                " '9', '0', '15', 900.00, :mot, 'homologacao', true, now())"
            ),
            {
                "cond": "00000000-0000-0000-0000-000000000001",
                "nat": f"{FIXTURE} VENDA",
                "dest": f"{FIXTURE} DESTINATARIO LTDA",
                "mot": XMOTIVO,
            },
        )
        await db.commit()

        try:
            telas = await z3.telas(db)

            # 1) o padrão do ambiente é HOMOLOGAÇÃO
            nova = telas.get("nfe-nova")
            if not nova:
                falhas.append("telas() não devolve 'nfe-nova'")
            else:
                amb = next((f for f in nova.get("fields") or [] if f.get("key") == "ambiente"), None)
                if not amb:
                    falhas.append("'nfe-nova' não tem o campo 'ambiente'")
                else:
                    if amb.get("value") != "homologacao":
                        falhas.append(
                            f"padrão do ambiente é {amb.get('value')!r} — tem de ser 'homologacao'. "
                            "Emitir em PRODUÇÃO por padrão é irreversível."
                        )
                    ops = amb.get("options") or []
                    if not ops or ops[0].get("value") != "homologacao":
                        falhas.append("a primeira opção do select de ambiente não é homologação")
                    if not any(o.get("value") == "producao" for o in ops):
                        falhas.append("o select de ambiente não oferece produção (o caminho tem de existir)")
                if "HOMOLOGAÇÃO" not in (nova.get("sub") or "").upper():
                    falhas.append("'nfe-nova' não avisa, no subtítulo, que emite em homologação")
                # a tela nova NÃO pode ser o caminho de produção
                if (nova.get("submit") or {}).get("endpoint", "").endswith("nfe-producao"):
                    falhas.append("'nfe-nova' aponta para o endpoint de produção")

            # a tela de produção existe E é gated com confirmação humana
            prod = telas.get("nfe-producao")
            if not prod:
                falhas.append("telas() não devolve 'nfe-producao' (o caminho de produção tem de existir)")
            else:
                sub = prod.get("submit") or {}
                if not sub.get("gated"):
                    falhas.append("'nfe-producao' não é gated — produção sem gate humano")
                if not sub.get("confirm"):
                    falhas.append("'nfe-producao' não pede confirmação humana")

            # preview não transmite nada
            prev = telas.get("nfe-preview")
            if not prev:
                falhas.append("telas() não devolve 'nfe-preview'")
            elif prev.get("type") != "table":
                falhas.append(f"'nfe-preview' é {prev.get('type')!r} — tem de ser leitura (table)")
            else:
                # O dispatcher injeta em TODA tabela um «Ver» read-only (`verDaLinha`), sem
                # endpoint — por isso a régua é ter ENDPOINT, não ter `actions`.
                escritas = [
                    a.get("btnLabel")
                    for r in prev.get("rows") or []
                    for a in (r.get("actions") or [])
                    if (a or {}).get("endpoint")
                ]
                if escritas:
                    falhas.append(f"'nfe-preview' tem ação de escrita {escritas} — nada é transmitido nesta tela")

            # 5) a lista mostra o xMotivo INTEIRO da rejeitada
            lista = telas.get("nfes-emitidas")
            if not lista:
                falhas.append("telas() não devolve 'nfes-emitidas'")
            else:
                achou = False
                for row in lista.get("rows") or []:
                    if XMOTIVO in _texto(row):
                        achou = True
                        break
                if not achou:
                    falhas.append(
                        "'nfes-emitidas' não mostra o xMotivo INTEIRO da rejeitada — é ele que ensina a corrigir"
                    )
                # e a rejeitada tem de oferecer o XML, não o cancelamento
                for row in lista.get("rows") or []:
                    if XMOTIVO not in _texto(row):
                        continue
                    rotulos = {str(a.get("btnLabel", "")).lower() for a in row.get("actions") or []}
                    if any("cancel" in x for x in rotulos):
                        falhas.append("rejeitada oferece «Cancelar» — nota rejeitada não existe na SEFAZ")
        finally:
            await db.execute(text("DELETE FROM nfes WHERE coalesce(motivo_rejeicao,'') LIKE :p"), {"p": f"%{FIXTURE}%"})
            await db.execute(text("DELETE FROM nfes WHERE natureza_operacao LIKE :p"), {"p": f"%{FIXTURE}%"})
            await db.commit()

    for f in falhas:
        print("FALHOU:", f)
    print(f"TOTAL falhas Z3: {len(falhas)}")
    if falhas:
        raise AssertionError(f"{len(falhas)} desvio(s) na tela de NF-e")
    print(
        "OK NF-e: padrão homologação travado, recusa que ensina (NCM/destinatário/CFOP), "
        "DANFE de homologação com SEM VALOR FISCAL, cancelamento com 15+ caracteres, "
        "xMotivo inteiro na lista."
    )
    return 0


def _texto(no) -> str:
    """Todo o texto de uma linha da tabela do redesign (células, docs, ações), recursivo."""
    if isinstance(no, str):
        return no
    if isinstance(no, dict):
        return " ".join(_texto(v) for v in no.values())
    if isinstance(no, (list, tuple)):
        return " ".join(_texto(v) for v in no)
    return ""


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except AssertionError as e:
        print(e)
        sys.exit(1)
