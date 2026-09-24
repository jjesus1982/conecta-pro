"""Oráculo da frente DGX Z6 — «Bartolo — tire sua dúvida» no fluxo fiscal da onda 8.

POR QUE EXISTE
--------------
O dono pediu o Bartolo «dando o apoio nisso, tirando dúvidas» na emissão de nota fiscal. Um
assistente de nota fiscal falha de dois jeitos, e os dois são caros:

  1. **Ele responde «não existe» sobre dado que existe.** Medido em 24/09/2026 pela própria rota
     `/consultores/chat/consultar`, lente fiscal, ANTES desta frente: «não há registro de
     rejeição para a nota nº 2 — o módulo fiscal não guarda motivo de rejeição de NF-e» e «não
     há NF-e de saída na base». As duas coisas estavam em `nfes` desde 11/04/2026, com o
     `xMotivo` literal «Rejeicao: Informado NCM inexistente [nItem: 1]».
  2. **Ele inventa o número.** NCM, alíquota e CFOP errados não dão erro na hora: dão multa
     meses depois. Um chat que "ajuda" cravando 5102 sem consultar é pior que um chat mudo.

O QUE ESTE ORÁCULO AFIRMA
-------------------------
  1. TODA ferramenta nova do Bartolo é SÓ LEITURA — varredura do código dos dois arquivos da
     frente atrás de INSERT/UPDATE/DELETE/DROP/TRUNCATE/CREATE e de `commit()`.
  2. Pergunta cuja resposta a casa NÃO tem devolve `nao_sei` + o ponteiro para a decisão
     pendente — e NENHUM número classificatório (nada de NCM de 8 dígitos, nada de alíquota).
  3. A explicação de rejeição cita o `xMotivo` REAL da nota, caractere por caractere, e lista
     os itens cujo NCM não está na tabela oficial `ncms` (medido, não deduzido do texto).
  4. A tributação que o Bartolo diz é EXATAMENTE a que o serviço da Z4 calcula — sem régua
     paralela. É a afirmação mais importante daqui: se um dia alguém "melhorar" o repasse
     recalculando algo, este teste fica vermelho.
  5. As 10 perguntas do §1 do relatório respondem sem erro pela rota real (requer LLM;
     desligue com `Z6_SEM_LLM=1` para rodar só as travas determinísticas).

ESTADO MEDIDO NO NASCIMENTO (sandbox, 24/09/2026)
-------------------------------------------------
  · `nfes` = 2 NF-e de saída, ambas de 11/04/2026, ambas `rejeitada`; nº 1 «Lote processado»,
    nº 2 «Rejeicao: Informado NCM inexistente [nItem: 1]». Nenhuma autorizada.
  · Os 3 itens dessas notas usam NCM `98010000` e `85258900` — **nenhum dos dois existe** nos
    10.515 códigos de `ncms`. A rejeição estava certa, e a causa é verificável por SQL.
  · `products` = 867 linhas, 674 SEM NCM. `fin_produtos` (cadastro fiscal, frente Z1) ainda
    não existia neste banco quando a frente nasceu.
  · Tools do escopo fiscal que liam `nfes`/`nfe_itens`/cadastro fiscal de produto: **zero**.

COMO RODA
---------
    docker run --rm --network conecta-staging-network -v "$PWD/backend:/app:ro" \\
      -e PYTHONPATH=/app -e PYTHONDONTWRITEBYTECODE=1 --env-file /opt/conecta-pro/.env \\
      -e SMTP_HOST= -e SMTP_USERNAME= -e SMTP_PASSWORD= $ENVS \\
      conecta-pro-backend:latest python3 /app/scripts/orq/test_oraculo_z6_bartolo.py

Fixtures marcadas com 'FIXTURE DGX Z6' e apagadas ao fim, aconteça o que acontecer.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import sys
import uuid
from pathlib import Path

sys.path.insert(0, "/app")

from sqlalchemy import text  # noqa: E402

from core.database import async_session_factory  # noqa: E402

MARCA = "FIXTURE DGX Z6"
PAINEL = "/redesign/bi?t=decisoes-do-dono"
RAIZ = Path(__file__).resolve().parents[1].parent  # /app
ARQ_TOOLS = RAIZ / "modules/ai/conversation/services/orquestrador/tools_read_fiscal_nfe.py"
ARQ_TELA = RAIZ / "modules/operacional/controllers/redesign_builders/dgx_z6_bartolo.py"

falhas: list[str] = []
oks: list[str] = []


def checa(cond: bool, titulo: str, detalhe: str = "") -> bool:
    (oks if cond else falhas).append(titulo if cond else f"{titulo} — {detalhe}")
    print(f"  {'OK  ' if cond else 'FALHA'} {titulo}" + (f"\n        {detalhe}" if not cond and detalhe else ""))
    return cond


# ───────────────────────── 1. só leitura (varredura estática) ─────────────────────────

#: Escrita em SQL. `CREATE` entra porque DDL num caminho de consulta é escrita disfarçada.
_ESCRITA = re.compile(r"\b(INSERT\s+INTO|UPDATE\s+\w|DELETE\s+FROM|DROP\s+|TRUNCATE\s+|CREATE\s+(TABLE|INDEX))\b", re.I)


def _sem_comentarios(fonte: str) -> str:
    """Tira docstrings e comentários: a varredura julga CÓDIGO, não prosa sobre código."""
    fonte = re.sub(r'"""(?:.|\n)*?"""', "", fonte)
    fonte = re.sub(r"'''(?:.|\n)*?'''", "", fonte)
    return "\n".join(linha.split("#")[0] for linha in fonte.splitlines())


def parede_so_leitura() -> None:
    print("\n[1] Toda ferramenta nova é SÓ LEITURA")
    for arq in (ARQ_TOOLS, ARQ_TELA):
        if not checa(arq.exists(), f"{arq.name} existe", str(arq)):
            continue
        codigo = _sem_comentarios(arq.read_text(encoding="utf-8"))
        achados = sorted({m.group(0).strip().upper() for m in _ESCRITA.finditer(codigo)})
        checa(not achados, f"{arq.name}: nenhuma escrita em SQL", f"achado: {achados}")
        commits = [n + 1 for n, ln in enumerate(codigo.splitlines()) if ".commit(" in ln]
        checa(not commits, f"{arq.name}: nenhum commit()", f"linhas {commits}")


# ───────────────── 2. «não sei» com ponteiro, e sem número inventado ─────────────────

#: 8 dígitos seguidos = um NCM. Se aparecer numa resposta de «não sei», alguém chutou.
_NCM_SOLTO = re.compile(r"(?<!\d)\d{8}(?!\d)")
#: alíquota tipo "20%", "1,65 %", "7.60%".
_ALIQUOTA = re.compile(r"\d+[.,]?\d*\s*%")


async def parede_nao_sei(db) -> None:
    print("\n[2] O que a casa não tem volta como «não sei» + ponteiro, nunca como número")
    from modules.ai.conversation.services.orquestrador import tools_read_fiscal_nfe as z6

    user = _UserFake()
    r = await z6._produto_fiscal(db, user, None, codigo="NAO-EXISTE-Z6-" + uuid.uuid4().hex[:6])
    checa(r.get("nao_sei") is True, "produto inexistente → nao_sei=True", json.dumps(r, ensure_ascii=False)[:300])
    checa(r.get("onde_decidir") == PAINEL, "aponta o painel do dono", str(r.get("onde_decidir")))
    bruto = json.dumps(r, ensure_ascii=False)
    checa(not _NCM_SOLTO.search(bruto), "nenhum NCM de 8 dígitos na resposta", str(_NCM_SOLTO.findall(bruto)))
    checa(not _ALIQUOTA.search(bruto), "nenhuma alíquota na resposta", str(_ALIQUOTA.findall(bruto)))

    r2 = await z6._nfe_saida(db, user, None, numero=999777)
    checa(r2.get("nao_sei") is True, "NF-e inexistente → nao_sei=True", json.dumps(r2, ensure_ascii=False)[:300])
    checa(r2.get("onde_decidir") == PAINEL, "aponta o painel do dono (nfe_saida)", str(r2.get("onde_decidir")))


class _UserFake:
    """Usuário de diretoria. O gate é `user_has_module(user,'fiscal')`; o oráculo prova a
    REGRA das ferramentas, não o RBAC (esse tem oráculo próprio, `test_oraculos_rbac`)."""

    id = "oraculo-z6"
    email = "oraculo-z6@conectamais.pro"
    role = "admin"
    is_superuser = True
    modules: list[str] = []


# ─────────────────── 3. a rejeição cita o xMotivo REAL (fixture) ───────────────────

_XMOTIVO = "Rejeicao: NCM inexistente na tabela oficial [nItem: 1] " + MARCA
_NCM_FANTASMA = "98010000"  # não existe em `ncms` — verificado abaixo, não presumido


async def _semear(db) -> tuple[str, int]:
    nfe_id = str(uuid.uuid4())
    numero = 990000 + int(uuid.uuid4().int % 9000)
    await db.execute(
        text(
            "INSERT INTO nfes (id, condominio_id, tipo, finalidade, status, serie, numero, "
            " natureza_operacao, data_emissao, emitente_cnpj, emitente_razao_social, emitente_uf, "
            " emitente_crt, destinatario_cpf_cnpj, destinatario_razao_social, destinatario_uf, "
            " destinatario_logradouro, destinatario_numero, destinatario_bairro, "
            " destinatario_municipio, destinatario_cep, modalidade_frete, forma_pagamento, "
            " meio_pagamento, valor_total_nota, motivo_rejeicao, informacoes_complementares, active) "
            "VALUES (CAST(:id AS uuid), CAST(:cond AS uuid), 'saida', '1', 'rejeitada', 99, :num, "
            " :nat, now(), '35710481000103', 'CONECTAMAIS ELETRONICA', 'AM', '3', "
            " '23147782000191', 'DESTINATARIO FIXTURE', 'AM', 'RUA X', '1', 'CENTRO', 'MANAUS', "
            " '69000000', '9', '0', '01', 100.00, :mot, :info, TRUE)"
        ),
        {
            "id": nfe_id,
            "cond": str(uuid.uuid4()),
            "num": numero,
            "nat": f"VENDA {MARCA}"[:60],
            "mot": _XMOTIVO,
            "info": MARCA,
        },
    )
    await db.execute(
        text(
            "INSERT INTO nfe_itens (id, nfe_id, numero_item, codigo_produto, descricao, ncm, cfop, "
            " unidade, quantidade, valor_unitario, valor_total) "
            "VALUES (gen_random_uuid(), CAST(:id AS uuid), 1, 'Z6-FIX', :desc, :ncm, '5102', "
            " 'UN', 1, 100.00, 100.00)"
        ),
        {"id": nfe_id, "desc": f"ITEM {MARCA}"[:120], "ncm": _NCM_FANTASMA},
    )
    await db.commit()
    return nfe_id, numero


async def _limpar(db) -> None:
    await db.execute(
        text("DELETE FROM nfe_itens WHERE nfe_id IN (SELECT id FROM nfes WHERE informacoes_complementares = :m)"),
        {"m": MARCA},
    )
    await db.execute(text("DELETE FROM nfes WHERE informacoes_complementares = :m"), {"m": MARCA})
    await db.commit()


async def parede_rejeicao(db) -> None:
    print("\n[3] A explicação de rejeição cita o xMotivo REAL da nota")
    from modules.ai.conversation.services.orquestrador import tools_read_fiscal_nfe as z6

    fantasma_existe = (
        await db.execute(text("SELECT count(*) FROM ncms WHERE codigo = :c"), {"c": _NCM_FANTASMA})
    ).scalar_one()
    checa(
        fantasma_existe == 0,
        f"o NCM {_NCM_FANTASMA} da fixture NÃO está na tabela oficial",
        f"contagem em `ncms`: {fantasma_existe} (a fixture deixou de provar o que queria)",
    )

    _, numero = await _semear(db)
    r = await z6._nfe_rejeicao(db, _UserFake(), None, numero=numero)
    nota = (r.get("notas") or [{}])[0]
    checa(
        nota.get("xMotivo_literal") == _XMOTIVO,
        "devolve o xMotivo caractere por caractere, sem reescrever",
        f"gravado={_XMOTIVO!r} devolvido={nota.get('xMotivo_literal')!r}",
    )
    checa(bool(nota.get("onde_corrigir")), "diz qual CAMPO corrigir", json.dumps(nota, ensure_ascii=False)[:300])
    fora = nota.get("itens_com_ncm_fora_da_tabela_oficial") or []
    checa(
        [x["ncm"] for x in fora] == [_NCM_FANTASMA],
        "lista o item cujo NCM não está em `ncms` (medido por SQL)",
        str(fora),
    )
    # A explicação aponta o campo; ela NÃO pode propor o valor a pôr no campo.
    texto = str(nota.get("o_que_fazer") or "")
    checa(not _NCM_SOLTO.search(texto), "a explicação não sugere nenhum NCM", str(_NCM_SOLTO.findall(texto)))

    r2 = await z6._nfe_saida(db, _UserFake(), None, numero=numero)
    checa(
        (r2.get("notas") or [{}])[0].get("motivo_rejeicao") == _XMOTIVO,
        "a listagem carrega o mesmo motivo literal",
        json.dumps(r2, ensure_ascii=False)[:200],
    )


# ──────────── 4. tributação == a da Z4, sem régua paralela (a mais importante) ────────────

_SENTINELA = {
    "regra": "objeto da Z4",
    "linhas": [{"rotulo": "ICMS", "valor": 20.0, "norma": "RICMS-AM", "origem_regra": "sentinela do oráculo"}],
    "sem_fonte": "sem fonte — decisão do contador",
}


async def parede_tributacao(db) -> None:
    print("\n[4] A tributação que o Bartolo diz É a que o serviço da Z4 calcula")
    from modules.ai.conversation.services.orquestrador import tools_read_fiscal_nfe as z6

    user = _UserFake()
    produto = {"ncm": "85311000", "valor": 1000, "quantidade": 1, "origem": "0"}
    dest = {"uf": "AM", "cnpj": "23147782000191", "codigo_municipio": "1302603"}

    try:
        from modules.fiscal.services import tributacao_nfe as z4
    except ImportError:
        z4 = None

    if z4 is not None:
        esperado = await z4.calcular(db, "35710481000103", dict(produto), dict(dest), "revenda")
        r = await z6._tributacao_nfe(
            db,
            user,
            None,
            empresa_cnpj="35710481000103",
            ncm=produto["ncm"],
            valor=1000,
            quantidade=1,
            origem="0",
            destinatario=dest,
            operacao="revenda",
        )
        checa(
            r.get("calculo") == esperado,
            "o repasse é IGUAL ao cálculo do serviço da Z4 (nenhum número recalculado)",
            f"bartolo={json.dumps(r.get('calculo'), ensure_ascii=False, default=str)[:400]}\n"
            f"        z4     ={json.dumps(esperado, ensure_ascii=False, default=str)[:400]}",
        )
        checa(
            getattr(z4, "SEM_FONTE", z6.SEM_FONTE) == z6.SEM_FONTE,
            "a frase de «sem fonte» é a MESMA das duas frentes, palavra por palavra",
            f"z6={z6.SEM_FONTE!r} z4={getattr(z4, 'SEM_FONTE', None)!r}",
        )
    else:
        # Z4 ainda não está nesta branch. A REGRA a provar continua sendo a mesma: o que o
        # Bartolo diz é o OBJETO que o serviço devolveu, não uma releitura dele. Um serviço
        # falso injetado prova o repasse por IDENTIDADE — mais forte que igualdade.
        import types

        stub = types.ModuleType("modules.fiscal.services.tributacao_nfe")
        stub.SEM_FONTE = z6.SEM_FONTE

        async def _calcular(_db, _cnpj, _prod, _dest, _op="revenda"):
            return _SENTINELA

        stub.calcular = _calcular
        import modules.fiscal.services as _pkg

        sys.modules["modules.fiscal.services.tributacao_nfe"] = stub
        _pkg.tributacao_nfe = stub
        try:
            r = await z6._tributacao_nfe(
                db, user, None, empresa_cnpj="35710481000103", ncm=produto["ncm"], valor=1000, destinatario=dest
            )
            checa(
                r.get("calculo") is _SENTINELA,
                "o repasse entrega o OBJETO do serviço fiscal, sem recalcular nada "
                "(Z4 ausente nesta branch — provado por serviço injetado)",
                json.dumps(r, ensure_ascii=False, default=str)[:400],
            )
        finally:
            sys.modules.pop("modules.fiscal.services.tributacao_nfe", None)
            if hasattr(_pkg, "tributacao_nfe"):
                del _pkg.tributacao_nfe

        r3 = await z6._tributacao_nfe(db, user, None, empresa_cnpj="35710481000103", valor=1000)
        checa(
            r3.get("nao_sei") is True,
            "sem o serviço da Z4, o Bartolo diz que NÃO SABE em vez de estimar",
            json.dumps(r3, ensure_ascii=False)[:300],
        )
        bruto = json.dumps(r3, ensure_ascii=False)
        checa(not _ALIQUOTA.search(bruto), "e não devolve alíquota nenhuma", str(_ALIQUOTA.findall(bruto)))


# ─────────────── 5. as 10 perguntas do §1 respondem sem erro (rota real) ───────────────


async def parede_dez_perguntas(db) -> None:
    from modules.operacional.controllers.redesign_builders import dgx_z6_bartolo as tela

    print("\n[5] As 10 perguntas frequentes — a tela e a rota")
    t = await tela.telas(db)
    scr = t.get(tela.TELA) or {}
    opcoes = [o["value"] for f in scr.get("fields", []) for o in f.get("options", [])]
    checa(
        list(tela.FREQUENTES) == opcoes,
        "as 10 perguntas do §1 estão clicáveis na tela, na ordem",
        f"{len(opcoes)} opções",
    )
    checa(len(tela.FREQUENTES) == 10, "são 10", str(len(tela.FREQUENTES)))
    checa(all(len(p) >= 3 for p in tela.FREQUENTES), "todas passam o mínimo de 3 caracteres do ConsultarIn")
    campos = {f["key"] for f in scr.get("fields", [])}
    checa("pergunta" in campos, "há campo livre além das frequentes", str(campos))

    if os.getenv("Z6_SEM_LLM"):
        print("        (Z6_SEM_LLM=1 — a rodada das 10 pela rota real foi pulada de propósito)")
        return
    from modules.operacional.controllers.redesign_builders.dgx_z6_bartolo import rd_bartolo_perguntar

    user = await _usuario_real(db)
    if user is None:
        checa(False, "usuário real para rodar as 10", "nenhum admin encontrado em `users`")
        return
    ruins = []
    for i, p in enumerate(tela.FREQUENTES, 1):
        try:
            out = await rd_bartolo_perguntar(current_user=user, payload={"frequente": p}, db=db)
            ok = bool(out.get("ok")) and len(str(out.get("message") or "")) > 40
            print(f"        [{i:>2}/10] {'ok ' if ok else 'RUIM'} {p[:62]}")
            if not ok:
                ruins.append((p, str(out.get("message"))[:160]))
        except Exception as exc:  # noqa: BLE001
            ruins.append((p, f"{type(exc).__name__}: {exc}"))
            print(f"        [{i:>2}/10] ERRO {p[:62]} — {type(exc).__name__}")
    checa(
        not ruins, "as 10 perguntas respondem sem erro pela rota real", "; ".join(f"{p[:40]} → {m}" for p, m in ruins)
    )


async def _usuario_real(db):
    """O motor do chat precisa de um usuário de verdade (identidade real, RBAC de verdade)."""
    from sqlalchemy import select

    from core.models.user import User

    return (await db.execute(select(User).where(User.email == "jjesus@conectamais.pro").limit(1))).scalars().first()


# ──────────────────────────────────────── main ────────────────────────────────────────


async def main() -> int:
    parede_so_leitura()
    async with async_session_factory() as db:
        try:
            await parede_nao_sei(db)
            await parede_rejeicao(db)
            await parede_tributacao(db)
            await parede_dez_perguntas(db)
        finally:
            await db.rollback()
            await _limpar(db)
            print("\n  fixtures 'FIXTURE DGX Z6' apagadas.")
    total = len(oks) + len(falhas)
    print(f"\n{'=' * 78}")
    for f in falhas:
        print(f"  VERMELHO: {f}")
    print(f"TOTAL afirmações Z6 (Bartolo fiscal): {total} — {len(oks)} verdes, {len(falhas)} vermelhas")
    return 1 if falhas else 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
