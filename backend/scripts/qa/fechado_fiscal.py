#!/usr/bin/env python3
"""Critério de aceite EXECUTÁVEL do módulo Fiscal/Contabilidade (ordem de fechamento 14/08/2026).

Sai 0 só quando as 10 condições passam. Enquanto sair vermelho, o módulo não fechou.

    python3 backend/scripts/qa/fechado_fiscal.py      (do HOST, em /opt/conecta-pro)

# O CORTE — e por que ele é medido no VENCIMENTO, não na competência

Decisão do Jordan (14/08): o histórico até 31/07 serviu para homologar e está encerrado. O que
importa é de **01/08/2026 em diante**, nos DOIS CNPJs.

Aplicar esse corte à *competência* seria medir a coisa errada, e o número mostra por quê:

    competência 07/2026  →  vence 07/08 (FGTS, eSocial) e 20/08 (DAS, INSS, IRRF)
    competência 08/2026  →  vence em SETEMBRO

**O que está vivo em agosto é a competência 07.** A 08 nem deveria existir hoje:
`calendario_service.garantir_ate_hoje` só cria até a última competência ENCERRADA, de
propósito — "criar obrigação de mês aberto encheria a tela de prazo que ainda não existe".
Forçar a competência 08 agora quebraria esse desenho para satisfazer a régua.

Então o corte aqui é `data_vencimento >= 2026-08-01`: é a data que gera multa, é a que o
Jordan enxerga, e ela captura a competência 07 (vencendo agora) e a 08 (quando nascer, em
setembro). Nada anterior a 01/08 é medido.

# A regra do "regime CERTO" — evidência, nunca legislação

`calendario_service` recusa deduzir da lei quais obrigações a empresa tem, e a recusa está
certa: "deduzir da legislação seria eu decidindo o enquadramento dela". Este gate mantém a
mesma disciplina e só afirma o que a NOSSA base prova:

  * DAS só existe em `simples_nacional`. É definição do tributo, não enquadramento.

⚠️ Havia uma segunda afirmação aqui — "obrigação de folha pertence a quem tem os holerites" —
e ela foi RETIRADA no mesmo dia em que nasceu. A fonte era `hr_payslips.empresa_id`, coluna
com DEFAULT Patrimonial: holerite não atribuído nasce Patrimonial, e a coluna "provou" uma
migração de folha que o governo não registrou. O documento do emissor desmente (GFD FGTS
06.2026 na Eletrônica, 54 trabalhadores). Oito obrigações foram movidas e revertidas. Quem
atribui obrigação a CNPJ é a GUIA, que traz o empregador impresso.

O que este gate NÃO decide, e fica para o Jordan: se a Eletrônica sem folha ainda deve
ESOCIAL sem movimento, e se a Patrimonial (serviço, Simples III) precisa de certidão
ESTADUAL. Ambos estão marcados no relatório, não silenciados aqui.
"""
from __future__ import annotations

import os
import re
import subprocess
import sys
from datetime import date

RAIZ = "/opt/conecta-pro"
BASE = os.path.join(RAIZ, "backend")

#: O corte declarado pelo Jordan em 14/08/2026. Medido no VENCIMENTO — ver docstring.
CORTE = date(2026, 8, 1)

#: ⚠️ NÃO reintroduza uma regra de "obrigação de folha pertence a quem tem os holerites".
#: Foi tentada em 14/08/2026 e a evidência que a sustentava era um DEFAULT de coluna:
#: `hr_payslips.empresa_id` nasce Patrimonial quando ninguém atribui. O documento do
#: emissor desmente — GFD FGTS 06.2026 filiada na Eletrônica com 54 trabalhadores, e o
#: DCTFWeb de 07/2026 todo sob 35710481000103. Oito obrigações foram movidas por essa
#: regra e revertidas. Quem atribui é a GUIA, que traz o CNPJ do empregador.

#: Certidões exigidas dos DOIS CNPJs. Saiu do conjunto REAL da Eletrônica (medido 14/08),
#: menos `registro_cnpj`, que é cadastro e não certidão.
#: ⚠️ `certidao_negativa_estadual` é ICMS — se o Jordan confirmar que a Patrimonial (serviço
#: puro, CNAE 8111-7/00) não precisa dela, tire desta tupla. É a única linha a mudar.
CERTIDOES_EXIGIDAS = (
    "certidao_negativa_federal",
    "certidao_negativa_inss",
    "certidao_negativa_fgts",
    "certidao_negativa_trabalhista",
    "certidao_negativa_municipal",
    "certidao_negativa_estadual",
    "alvara_funcionamento",
)

#: As 5 telas de cálculo da F1 — o motor devolve o número e a tela descarta o corpo.
CALCULADORAS = ("calc-simples", "calc-lucro-real", "calc-comparativo",
                "calc-limite-simples", "calc-retencoes")

#: As 8 tools mínimas do agente fiscal (F4).
TOOLS_FISCAIS = ("calcular_das", "calcular_lucro_real", "comparar_regimes",
                 "calcular_retencoes", "obrigacoes_do_mes", "certidoes_vencendo",
                 "guias_pendentes", "propor_baixa_obrigacao")

MEU = ("modules/fiscal", "modules/fiscal_contabil", "modules/government_integrations",
       "/fiscal", "/government")

#: Prefixo de nome de TASK que pertence a este fechamento. `ged.` entra porque as certidões
#: alimentam a condição 1; `financial.`/`crm.`/`sst.`/`whatsapp.` ficam de fora — aparecem no
#: detalhe, mas não decidem o fechamento do fiscal.
_BEATS_MEUS = ("fiscal.", "government_integrations.", "esocial", "ged.")


def _ok(cond: bool, titulo: str, detalhe: str = "") -> bool:
    print(f"  {'✅' if cond else '❌'} {titulo}" + (f" — {detalhe}" if detalhe else ""))
    return cond


#: O container não respondeu — e isso NÃO é o mesmo que "a checagem reprovou".
#:
#: Aprendido na marra em 14/08/2026: outra sessão iniciou um deploy no meio de uma execução
#: do gate, o backend estava sendo recriado, e TODO `docker exec` falhou. O gate contou os
#: sete oráculos como vermelhos e imprimiu "0/7 verdes" — um retrato assustador e falso, no
#: mesmo minuto em que `fiscal_painel` passava quando rodado à mão.
#:
#: É literalmente a regra que a ordem de fechamento manda seguir: *ausência de resposta não é
#: prova de defeito*. Cinco sessões deployam neste host; o container SOME de tempos em
#: tempos, e um critério de aceite que confunde as duas coisas mente na hora exata em que
#: alguém está olhando.
_INFRA = ("Error response from daemon", "No such container", "is restarting",
          "is not running", "Cannot connect to the Docker daemon", "RWLayer of container")


def _infra_caiu(saida: str) -> bool:
    return any(m in saida for m in _INFRA)


def _imagem_em_uso_criada_em() -> str | None:
    """Quando foi construída a imagem que está SERVINDO agora (ISO UTC).

    Serve para responder a pergunta certa sobre o sino: *esta falha veio do código que está
    no ar?* Uma janela fixa de 48h não sabe disso e acusa defeito já corrigido — foi o que
    aconteceu em 15/08/2026: as 8 tarefas contadas tinham falhado em 13 e 14/08, todas
    ANTES do bake que trouxe os consertos, e nenhuma falhou depois. O gate reprovava por
    defeito que não existe mais, que é a mesma família do "container mudo = vermelho".

    O bake é o instante em que o conserto entra em produção, então ele é a régua natural —
    e se mantém sozinho: cada deploy reinicia o relógio.

    ⚠️ O preço, e ele é declarado no detalhe da condição: logo depois de um bake a janela de
    observação é curta, então "sino limpo" prova pouco. Por isso o gate imprime há quanto
    tempo a imagem está no ar — quem lê decide se o silêncio já significa alguma coisa.
    """
    try:
        img = subprocess.run(["docker", "inspect", "conecta-pro-backend", "--format", "{{.Image}}"],
                             capture_output=True, text=True, timeout=30)
        if img.returncode != 0 or not img.stdout.strip():
            return None
        r = subprocess.run(["docker", "inspect", img.stdout.strip(), "--format", "{{.Created}}"],
                           capture_output=True, text=True, timeout=30)
        return r.stdout.strip()[:19].replace("T", " ") if r.returncode == 0 else None
    except Exception:  # noqa: BLE001 — sem a data, cai para a janela fixa
        return None


def _rodar(script: str, precisa_banco: bool = False) -> str:
    """Roda uma trava e devolve stdout+stderr.

    `precisa_banco`: a trava que confronta o Postgres não alcança o banco do host, então vai
    por `docker exec`. As demais leem código, e código é o do host — que é o atual, enquanto
    a imagem baked ainda pode estar uma versão atrás.
    """
    if precisa_banco:
        cmd = ["docker", "exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend",
               "python3", f"/app/scripts/qa/{script}"]
        cwd = None
    else:
        caminho = os.path.join(RAIZ, "backend/scripts/qa", script)
        if not os.path.exists(caminho):
            raise FileNotFoundError(script)
        cmd, cwd = [sys.executable, caminho], RAIZ
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=900, cwd=cwd,
                       env={**os.environ, "PYTHONPATH": BASE})
    return r.stdout + r.stderr


# ─────────────────────────────────────────────────────────────────── 1 a 4: agosto no banco

def _q(sql: str, **p) -> list[list[str]]:
    """Consulta o banco por `psql`, com os parâmetros já interpolados por @nome.

    ⚠️ O marcador é `@`, e não `:`, porque `:` COLIDE com o cast do Postgres: `issue_date::text`
    contém `:t`, e um parâmetro chamado `t` transformava a query em
    `issue_date:'certidao_negativa_federal'ext`. O `@` não aparece em SQL nenhum daqui.

    Por que não SQLAlchemy: **de nenhum lugar dava para medir as 10 condições.** Do host, o
    Postgres não responde (`Connect call failed 127.0.0.1:5432` — ele só existe na rede do
    compose). De dentro do container do backend, o banco responde mas o `ModuleView.tsx` não
    existe, e não há `docker` para alcançar as travas do host. O host é o único lugar que vê
    as três coisas: código do backend, código do front e o banco via `docker exec`.

    Interpolação manual porque `psql -c` não tem bind: cada valor passa por `_lit`, que só
    aceita o que este gate usa (data, inteiro, texto com aspas escapadas). Nada aqui vem de
    entrada de usuário — é um script de QA com SQL fixo.
    """
    for nome, valor in p.items():
        sql = sql.replace(f"@{nome}", _lit(valor))
    r = subprocess.run(
        ["docker", "exec", "conecta-pro-postgres", "psql", "-U", "postgres", "-d",
         "conecta_pro", "-tAF", "|", "-c", sql],
        capture_output=True, text=True, timeout=120)
    if r.returncode != 0:
        erro = r.stderr.strip()[:300]
        if _infra_caiu(erro):
            raise RuntimeError(
                f"o Postgres não respondeu ({erro}). Provável deploy de outra sessão em "
                f"curso — rode de novo. Ausência de resposta não é prova de defeito.")
        raise RuntimeError(f"psql falhou: {erro}")
    return [ln.split("|") for ln in r.stdout.strip().splitlines() if ln.strip()]


def _lit(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, date):
        return f"'{v.isoformat()}'"
    return "'" + str(v).replace("'", "''") + "'"


def _condicoes_de_banco() -> list[tuple[bool, str, str]]:
    out: list[tuple[bool, str, str]] = []
    empresas = _q("SELECT slug, regime_tributario, "
                  "       replace(replace(replace(cnpj,'.',''),'/',''),'-','') "
                  "  FROM empresas WHERE status = 'ativa' ORDER BY slug")

    # 1 · CERTIDÕES — exigidas, válidas, e com data DO EMISSOR.
    # Quatro defeitos distintos, e o gate separa cada um, porque a ação é diferente:
    #   faltando            → emitir
    #   vencida             → renovar
    #   sem data de emissão → proveniência desconhecida, conferir no portal antes de usar
    #   validade < emissão  → registro ANULADO de propósito. A estadual da Eletrônica está
    #                         assim porque o cliente da Sefaz-AM devolvia "regular" para
    #                         CNPJ inexistente; anular foi acerto, e a certidão segue por
    #                         emitir à mão.
    faltando, vencidas, sem_emissao, anuladas = [], [], [], []
    hoje = date.today()
    for slug, _regime, cnpj in empresas:
        for tipo in CERTIDOES_EXIGIDAS:
            r = _q("SELECT coalesce(issue_date::text,''), coalesce(expiry_date::text,''), "
                   "       coalesce(notes,'') "
                   "  FROM ged_certidoes WHERE cnpj = @c AND document_type = @t LIMIT 1",
                   c=cnpj, t=tipo)
            if not r:
                faltando.append(f"{slug}/{tipo}")
                continue
            emissao, validade, notas = r[0][0], r[0][1], (r[0][2] if len(r[0]) > 2 else "")
            # ⚠️ Validade VAZIA nem sempre é buraco. O Alvará de Localização e Funcionamento
            # da SEMEF diz, com todas as letras no próprio documento: "O alvará de
            # Funcionamento tem validade indeterminada". Cobrar data dele seria exigir um
            # campo que o emissor não emite — e a saída fácil (carimbar hoje+1 ano) é
            # exatamente a fabricação de validade que já criou quatro certidões falsas nesta
            # base. Sem data, e o documento dizendo que não tem, vale.
            indeterminada = "INDETERMINADA" in notas.upper()
            if not emissao:
                sem_emissao.append(f"{slug}/{tipo}")
            elif validade and validade < emissao:
                anuladas.append(f"{slug}/{tipo}")
            if (not validade and not indeterminada) or (validade and date.fromisoformat(validade) < hoje):
                vencidas.append(f"{slug}/{tipo}")
    det = (f"{len(faltando)} faltando · {len(vencidas)} vencida(s) · "
           f"{len(sem_emissao)} sem data do emissor · {len(anuladas)} anulada(s)")
    for rotulo, lista in (("faltando", faltando), ("vencidas", vencidas),
                          ("sem emissão", sem_emissao), ("anuladas", anuladas)):
        if lista:
            det += f"\n       {rotulo}: {', '.join(lista)}"
    out.append((not (faltando or vencidas or sem_emissao or anuladas),
                "1 · certidões dos 2 CNPJs válidas, com data do emissor", det))

    # 2 · OBRIGAÇÕES vencendo de 01/08 em diante, cada uma no CNPJ que a evidência sustenta.
    problemas: list[str] = []
    linhas = _q("SELECT e.slug, e.regime_tributario, o.tipo, o.competencia_ano, "
                "       coalesce(o.competencia_mes, 0), o.data_vencimento "
                "  FROM fiscal_obligations o JOIN empresas e ON e.id = o.empresa_id "
                " WHERE o.active AND o.data_vencimento >= @corte "
                " ORDER BY e.slug, o.data_vencimento", corte=CORTE)
    for slug, *_ in [e for e in empresas if not any(ln[0] == e[0] for ln in linhas)]:
        problemas.append(f"{slug}: NENHUMA obrigação vencendo de 08/2026 em diante")

    for slug, regime, tipo, ano, mes, _venc in linhas:
        if tipo == "DAS" and regime != "simples_nacional":
            problemas.append(f"{slug}: DAS em empresa {regime} (DAS só existe no Simples)")
    out.append((not problemas, "2 · obrigações de 08/2026 em diante no CNPJ e regime certos",
                f"{len(linhas)} obrigação(ões) medida(s), {len(problemas)} problema(s)"
                + ("\n       " + "\n       ".join(problemas) if problemas else "")))

    # 3 · GUIAS — obrigação vencida há mais de 5 dias sem valor nem recibo é prazo cego.
    # Só de 01/08 em diante: as de abr–jul são "status não conciliado do período de
    # homologação", decisão do Jordan, e NÃO se persegue retroativamente.
    sem_guia = _q("SELECT e.slug, o.tipo, o.data_vencimento::text "
                  "  FROM fiscal_obligations o JOIN empresas e ON e.id = o.empresa_id "
                  " WHERE o.active AND o.data_vencimento >= @corte "
                  "   AND o.data_vencimento < CURRENT_DATE - 5 "
                  "   AND o.status <> 'cumprida' "
                  "   AND (o.numero_recibo IS NULL OR o.numero_recibo = '') "
                  "   AND o.valor_devido IS NULL "
                  " ORDER BY o.data_vencimento", corte=CORTE)
    out.append((not sem_guia, "3 · obrigação vencida há >5 dias tem guia",
                f"{len(sem_guia)} sem guia"
                + ("\n       " + "\n       ".join(
                    f"{s}/{t} venceu {v}" for s, t, v in sem_guia) if sem_guia else "")))

    # 4 · NFS-e — contrato ativo fatura no mês, pelo CNPJ dele.
    #
    # ⚠️ SÓ COBRA A PARTIR DO DIA 25, e o número saiu do histórico, não de palpite. A casa
    # fatura no FIM do mês — medido em 17/08/2026, notas emitidas até o dia 17 de cada mês:
    #
    #     01/2026  0 de 13     04/2026  1 de 14     06/2026  2 de 17
    #     02/2026  0 de 12     05/2026  2 de 15     07/2026  3 de 16
    #     03/2026  1 de 12
    #
    # O grosso cai nos dias 24–30 (dia 30 sozinho tem 27 notas no ano). Cobrar antes disso
    # deixaria a condição VERMELHA 24 dias por mês sem nada de errado — exatamente o alarme
    # falso que este fechamento passou dois dias caçando, e que eu mesmo escrevi aqui.
    #
    # Antes do dia 25 a condição PASSA dizendo que ainda não é devida. É o mesmo princípio
    # do `calendario_service`, que não cria obrigação de mês aberto: não se afirma o que
    # ainda não venceu.
    DIA_DE_COBRAR = 25
    sem_nota = _q("SELECT e.slug, count(*)::text "
                  "  FROM contracts c JOIN empresas e ON e.id = c.empresa_id "
                  " WHERE c.status::text = 'active' "
                  "   AND NOT EXISTS (SELECT 1 FROM nfse_emitidas_nacional n "
                  "                    WHERE n.empresa_id = c.empresa_id "
                  "                      AND n.data_emissao >= @ini) "
                  " GROUP BY e.slug ORDER BY e.slug", ini=hoje.replace(day=1))
    faltam = " · ".join(f"{s}: {n} contrato(s) sem nota" for s, n in sem_nota)
    if hoje.day < DIA_DE_COBRAR:
        out.append((True, "4 · contrato ativo com NFS-e no mês, pelo CNPJ certo",
                    f"ainda não é devido — a casa fatura a partir do dia {DIA_DE_COBRAR} "
                    f"(hoje é {hoje.day}). Situação parcial: {faltam or 'todos já faturaram'}"))
    else:
        out.append((not sem_nota, "4 · contrato ativo com NFS-e no mês, pelo CNPJ certo",
                    faltam or "todos faturaram"))

    # 6 · ROTINAS — o sino sem falha recorrente, e o espelho do eSocial produzindo.
    # Falha de código que NÃO ESTÁ MAIS NO AR não é evidência sobre o sistema de agora.
    # A régua é o bake da imagem em uso; sem ela, cai para 48h.
    desde = _imagem_em_uso_criada_em()
    corte_sino = (f"created_at > TIMESTAMP '{desde}'" if desde
                  else "created_at > now() - interval '48 hours'")
    falhas = _q("SELECT title, count(*)::text FROM communication_notifications "
                f" WHERE {corte_sino} "
                "   AND title ILIKE '%Tarefa agendada falhou%' "
                " GROUP BY title ORDER BY 2 DESC")
    # O espelho não é medido pela janela (ela pode existir sem nunca ter sido consultada) e
    # sim pelo ACESSO ao governo, que é o que prova que a rotina produziu alguma coisa.
    ultimo_acesso = _q("SELECT coalesce(max(criado_em)::date::text, '') "
                       "  FROM esocial_espelho_acessos")
    ultimo = ultimo_acesso[0][0] if ultimo_acesso else ""
    espelho_ok = bool(ultimo) and (hoje - date.fromisoformat(ultimo)).days <= 2
    janela = (f"desde o bake em uso ({desde} UTC)" if desde else "nas últimas 48h")
    det6 = (f"{len(falhas)} tarefa(s) falhando {janela} · "
            f"último acesso do espelho ao governo: {ultimo or 'NUNCA'}")
    if desde and not falhas:
        det6 += ("\n       ⚠️ janela curta se o bake é recente — silêncio aqui prova menos "
                 "quanto mais novo for o deploy")
    if falhas:
        det6 += "\n       " + "\n       ".join(
            f"{t.replace('Tarefa agendada falhou: ', '')} ({n}×)" for t, n in falhas)
    out.append((not falhas and espelho_ok, "6 · rotinas: sino limpo e espelho produzindo", det6))

    return out


# ─────────────────────────────────────────────────────────────── 5 e 8: código, sem banco

def _c5_calculadoras() -> tuple[bool, str]:
    """5 · as 5 telas de cálculo exibem o número.

    Regra da casa: *"Calculado" sem número é defeito, não sucesso.* `type:"form"` no ModuleView
    exibe só `d.message`, então uma tela de cálculo assim responde "DAS calculado" e joga fora
    os R$13.030 que o motor devolveu.

    ⚠️ O contrato é `submit.showResult` — opt-in, de propósito: a maioria dos forms é AÇÃO, e
    despejar o corpo da resposta neles seria ruído. Medir a presença de `type:"form"` sozinho
    acusa as 5 injustamente; foi o que o raio-x de 14/08 concluiu, lendo a linha 495 do
    ModuleView sem ver o ramo do `showResult` na 568. As duas pontas já existem desde 09-10/08
    (`8e8181d8` no front, `4e3a905b` no builder) — este critério guarda contra a REGRESSÃO.

    Estático nas duas pontas. Que o painel de fato pinte na tela é lente de NAVEGADOR, e está
    declarada em NÃO COBERTO no relatório.
    """
    try:
        with open(f"{BASE}/modules/operacional/controllers/redesign_builders/fiscal.py",
                  encoding="utf-8") as f:
            builder = f.read()
    except OSError as e:  # noqa: BLE001
        return False, f"não li o builder: {e}"

    # O front não existe dentro do container do backend. Sem ele, metade do contrato fica
    # POR VERIFICAR — e por verificar não é verde. "NÃO VERIFICADO" é resultado válido;
    # "passou" sem evidência não é.
    caminho_front = f"{RAIZ}/frontend/src/components/redesign/ModuleView.tsx"
    if not os.path.exists(caminho_front):
        return False, ("NÃO VERIFICADO: o ModuleView não é alcançável daqui — "
                       "rode este gate no HOST para medir a ponta do front")
    with open(caminho_front, encoding="utf-8") as f:
        front = f.read()

    mudas = []
    for calc in CALCULADORAS:
        m = re.search(rf'out\["{re.escape(calc)}"\]\s*=\s*\{{(.{{0,1600}}?)\n    \}}', builder, re.S)
        if not m:
            mudas.append(f"{calc} (bloco não encontrado)")
        elif '"showResult": True' not in m.group(1):
            mudas.append(calc)
    if "showResult" not in front:
        return False, "o ModuleView não honra showResult — as 5 telas ficam mudas"
    return not mudas, f"{5 - len(mudas)}/5 com showResult, e o ModuleView honra" + (
        f" · sem painel: {', '.join(mudas)}" if mudas else "")


def _c8_tools() -> tuple[bool, str]:
    """8 · as 8 tools do agente fiscal registradas, e o agente sem SQL próprio."""
    achadas = set()
    for raiz, _d, arqs in os.walk(BASE + "/modules"):
        if "_quarentena" in raiz or "__pycache__" in raiz:
            continue
        for a in arqs:
            if not a.endswith(".py"):
                continue
            try:
                with open(os.path.join(raiz, a), encoding="utf-8") as f:
                    src = f.read()
            except OSError:
                continue
            for t in TOOLS_FISCAIS:
                if re.search(rf'ToolDef\([^)]*["\']{t}["\']', src, re.S) or \
                   re.search(rf'name\s*=\s*["\']{t}["\']', src):
                    achadas.add(t)
    faltam = [t for t in TOOLS_FISCAIS if t not in achadas]
    return not faltam, f"{len(achadas)}/{len(TOOLS_FISCAIS)} registradas" + (
        f" · faltam: {', '.join(faltam)}" if faltam else "")


# ────────────────────────────────────────────────────────── 7, 9 e 10: travas e oráculos

def _c7_beats() -> tuple[bool, str]:
    try:
        saida = _rodar("checar_beats.py", precisa_banco=True)  # precisa do celery_app registrado
    except Exception as e:  # noqa: BLE001
        return False, f"não rodou: {e}"
    if _infra_caiu(saida):
        return False, ("NÃO VERIFICADO: o container não respondeu — provável deploy em curso. "
                       "Ausência de resposta não é prova de defeito; rode de novo")
    # A trava é do SISTEMA INTEIRO; este gate é do FISCAL. Contar achado de outro terminal
    # aqui prende o fechamento deste módulo a um bug que não é meu para consertar —
    # `financial.auto_baixa_pagaveis` (do T1) segurou a condição por três dias. A condição 9
    # já filtrava por território; esta não filtrava.
    #
    # O de fora NÃO É ESCONDIDO: sai no detalhe, nomeado, para não virar silêncio conveniente.
    # Só não decide o meu fechamento.
    # ⚠️ `.strip(":")` NÃO É DETALHE. A camada "roda e não produz" imprime o nome seguido de
    # dois-pontos (`fiscal.certidoes.sync_diario: última produção em ...`), e a primeira
    # versão deste parser exigia o token inteiro casando `^[a-z_]+[.\w]*$` — o `:` reprovava
    # e o achado sumia. Resultado medido em 17/08/2026: a condição 7 imprimiu "0 no fiscal"
    # com um achado FISCAL na tela da trava, logo acima. Falso verde no meu próprio gate,
    # exatamente o que este fechamento passou dias caçando nos outros.
    meus, alheios = [], []
    for ln in saida.splitlines():
        toks = ln.strip().split()
        if not toks:
            continue
        nome = toks[0].strip(":·-—")
        if "." not in nome or not re.fullmatch(r"[a-z_]+(?:\.[a-z_0-9]+)+", nome):
            continue
        (meus if nome.startswith(_BEATS_MEUS) else alheios).append(nome)

    total = re.search(r"(\d+)\s+achado", saida)
    if total is None and "nenhum" not in saida.lower():
        return False, "saída não reconhecida (trava mudou de formato?)"

    det = f"{len(meus)} no fiscal" + (f": {', '.join(sorted(set(meus)))}" if meus else "")
    if alheios:
        det += f" · {len(set(alheios))} fora do módulo (não gateiam): {', '.join(sorted(set(alheios)))}"
    return not meus, det


def _c9_travas() -> tuple[bool, str]:
    """9 · repositorio · vocabulario · rotas_frontend == 0 no bloco fiscal/government."""
    total, detalhe = 0, []
    for script, precisa_banco in (("checar_repositorio.py", False),
                                  ("checar_vocabulario.py", True),
                                  ("checar_rotas_frontend.py", False)):
        try:
            saida = _rodar(script, precisa_banco=precisa_banco)
        except Exception as e:  # noqa: BLE001
            detalhe.append(f"{script}: não rodou ({e})")
            total += 1
            continue
        # ⚠️ `${` fora: é chamada montada por template literal, e a trava não resolve isso —
        # ela acusa `fetch(\`/api/v1/government/ecac${path}\`)` como rota inexistente sendo
        # que `ecac_controller` tem as rotas todas, e `path` é o sufixo que o helper recebe.
        # É a limitação documentada do grep (subestima f-string, superestima concatenação),
        # não defeito. Contar isso deixaria a condição 9 vermelha para sempre por engano.
        if _infra_caiu(saida):
            detalhe.append(f"{script.replace('checar_', '').replace('.py', '')}: NÃO VERIFICADO "
                           "(container mudo — deploy em curso?)")
            total += 1
            continue
        n = sum(1 for ln in saida.splitlines()
                if any(p in ln for p in MEU) and "${" not in ln
                and ("CRITICO" in ln or "x /api/v1/" in ln))
        total += n
        detalhe.append(f"{script.replace('checar_','').replace('.py','')}: {n}")
    return total == 0, " · ".join(detalhe)


def _c10_oraculos() -> tuple[bool, str]:
    """10 · os oráculos do fiscal verdes.

    Rodam no CONTAINER: oráculo confronta tela com banco, e o banco não responde ao host.
    ⚠️ O container serve a imagem BAKED — enquanto o deploy não roda, ele mede a versão
    anterior do código. Divergência entre este número e o resto do gate é sinal de bake
    pendente, não de defeito novo.
    """
    orq = os.path.join(BASE, "scripts/orq")
    testes = sorted(a for a in os.listdir(orq)
                    if re.search(r"(fiscal|contabil|esocial)", a) and a.endswith(".py"))

    def _roda(t: str):
        return subprocess.run(
            ["docker", "exec", "-e", "PYTHONPATH=/app", "conecta-pro-backend",
             "python3", f"/app/scripts/orq/{t}"],
            capture_output=True, text=True, timeout=600)

    vermelhos, mudos, transitorios = [], [], []
    for t in testes:
        r = _roda(t)
        nome = t.replace("test_oraculo_", "").replace("test_", "").replace(".py", "")
        if r.returncode == 0:
            continue
        if _infra_caiu(r.stdout + r.stderr):
            mudos.append(nome)      # o container não respondeu — não é veredito
            continue
        # ⚠️ REPETE ANTES DE ACUSAR. `_infra_caiu` só pega erro do daemon; um container
        # RECRIADO no meio da execução devolve erro de aplicação (conexão perdida, sessão
        # morta) e passava por vermelho. Aconteceu em 17/08/2026: o gate acusou
        # `fiscal_painel`, e ele passava quando rodado isolado um minuto depois — o deploy
        # tinha acabado de trocar o container.
        #
        # Oráculo é determinístico sobre o mesmo banco: se passa na segunda, o que falhou
        # foi o ambiente, não a regra. Uma repetição basta e custa pouco — só corre para
        # quem já falhou.
        r2 = _roda(t)
        if r2.returncode == 0:
            transitorios.append(nome)
        elif _infra_caiu(r2.stdout + r2.stderr):
            mudos.append(nome)
        else:
            vermelhos.append(nome)
    if mudos:
        return False, (f"NÃO VERIFICADO: o container não respondeu em {len(mudos)} de "
                       f"{len(testes)} ({', '.join(mudos)}) — provável deploy de outra sessão "
                       f"em curso. Ausência de resposta não é prova de defeito; rode de novo")
    det = f"{len(testes) - len(vermelhos)}/{len(testes)} verdes"
    if vermelhos:
        det += f" · vermelhos: {', '.join(vermelhos)}"
    if transitorios:
        det += (f" · {len(transitorios)} passou na repetição ({', '.join(transitorios)}) — "
                f"falha de ambiente, não da regra")
    return not vermelhos, det


def main() -> int:
    if not os.path.isdir(BASE):
        print(f"❌ Rode do HOST, em {RAIZ}. Dentro do container não há `docker` para alcançar "
              "as travas nem o código do front para medir a condição 5.")
        return 2

    print("\n╔══ FECHADO? · Fiscal / Contabilidade ═══════════════════════════════════")
    print(f"║  corte: vencimento >= {CORTE.isoformat()} · nada anterior é medido")
    print("╚════════════════════════════════════════════════════════════════════════\n")

    resultados: list[bool] = []

    print("AGOSTO EM DIANTE — o que fecha")
    de_banco = _condicoes_de_banco()
    for ok, titulo, det in de_banco[:4]:
        resultados.append(_ok(ok, titulo, det))

    print("\nO QUE SUSTENTA")
    for cond, titulo in ((_c5_calculadoras, "5 · as 5 calculadoras exibem o número"),):
        ok, det = cond()
        resultados.append(_ok(ok, titulo, det))
    ok, titulo, det = de_banco[4]
    resultados.append(_ok(ok, titulo, det))
    for cond, titulo in ((_c7_beats, "7 · checar_beats sem achados (importa · existe · PRODUZ)"),
                         (_c8_tools, "8 · as 8 tools do agente fiscal registradas"),
                         (_c9_travas, "9 · travas zeradas em fiscal/government"),
                         (_c10_oraculos, "10 · oráculos do fiscal verdes")):
        ok, det = cond()
        resultados.append(_ok(ok, titulo, det))

    verdes = sum(resultados)
    print(f"\n  {verdes}/{len(resultados)} condições verdes")
    if verdes < len(resultados):
        print("  ❌ O MÓDULO NÃO FECHOU.\n")
        return 1
    print("  ✅ FECHADO.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
