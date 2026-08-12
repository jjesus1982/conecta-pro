#!/usr/bin/env python3
"""Cada número que importa: QUEM, de fora daqui, confirma — e quando confirmou?

Ideia do T1 (12/08/2026), e ela fecha o buraco que os outros 67 oráculos não alcançam.

Nossos oráculos comparam **exibido == banco**. Os dois lados são nossos. Se o próprio banco
de dados estiver errado, o oráculo fica VERDE e o número continua mentiroso — e isso não é
hipótese: num único dia o extrato teve 880 linhas duplicadas (R$563.979,07), 94 registros com
sinal invertido (R$785 mil, "RECEBIMENTO" virando saída) e uma ponte recriando duplicata
todo dia. Nenhum oráculo de tela acusaria: a tela mostrava fielmente o que o banco tinha.

O que pega isso é confronto com fonte **fora do nosso controle**: o saldo que o banco
informa, a certidão que o órgão emite, o recibo que o governo devolve, a folha que a Portte
fecha. É o padrão que o T1 nomeou depois de errar três vezes seguidas: *"o que me pegou foi
sempre uma medição contra algo de fora, nunca uma releitura do meu próprio código."*

COMO ESTA TRAVA NÃO VIRA MENTIRA. A data da última prova **não é escrita à mão** — cada
âncora declara um SQL que a lê do próprio dado. Registro mantido por humano envelhece e passa
a afirmar prova que não houve; aqui, se a sincronização parar, a idade cresce sozinha.

O que ela NÃO faz: não confere valor contra a fonte (isso é trabalho do oráculo específico) e
não sabe o que você esqueceu de registrar. **Âncora ausente é o achado mais perigoso** — o
número que ninguém de fora confirma nem aparece aqui. Por isso `--listar` existe: leia a
lista e pergunte o que está faltando.

    python3 backend/scripts/qa/checar_oraculo_externo.py
    python3 backend/scripts/qa/checar_oraculo_externo.py --listar
    python3 backend/scripts/qa/checar_oraculo_externo.py --self-check
"""
from __future__ import annotations

import subprocess
import sys
from datetime import date, datetime

#: Cada âncora: o número que importa, a fonte DE FORA que o prova, o SQL que diz quando essa
#: fonte falou pela última vez, e por quantos dias essa palavra vale.
#: `validade_dias=None` → a própria fonte carrega o prazo (certidão traz vencimento).
ANCORAS = [
    {
        "numero": "saldo em caixa",
        "fonte": "API de saldo do próprio banco (Inter/Cora)",
        "sql": "SELECT max(last_balance_update)::date FROM bank_accounts",
        "validade_dias": 2,
        "obs": "NÃO use last_sync_at: coluna morta, ninguém escreve nela (erro medido do T1)",
    },
    {
        "numero": "extrato bancário",
        "fonte": "extrato do banco (importação)",
        "sql": "SELECT max(transaction_date) FROM bank_transactions",
        "validade_dias": 3,
        "obs": "o razão inteiro deriva daqui — quebrou 3x em silêncio em 11/08",
    },
    {
        "numero": "pagamentos efetivados",
        "fonte": "confirmação do Inter (único que transmite)",
        "sql": "SELECT max(created_at)::date FROM inter_payments",
        "validade_dias": 30,
        "obs": "Cora não tem PIX de saída na API; 89% do dinheiro sai por lá, fora do sistema",
    },
    {
        "numero": "certidões (CND/CRF/CNDT)",
        "fonte": "portal do órgão emissor",
        # 1a versão usava min(expiry_date): a certidão VENCIDA MAIS ANTIGA. Vermelho para
        # sempre, impossível de calar — a lição do T1 ("alarme que toca sempre é alarme que
        # ninguém lê") batendo na minha própria ferramenta. A pergunta certa é QUANDO um
        # emissor falou conosco pela última vez. Vencimento é assunto do oráculo de certidões.
        "sql": "SELECT max(issue_date) FROM ged_certidoes",
        "validade_dias": 90,
        "obs": "sem data do emissor não existe certidão — nunca estimar validade",
    },
    {
        "numero": "eventos eSocial",
        "fonte": "consulta ao governo (espelho)",
        "sql": "SELECT max(consultada_em)::date FROM esocial_espelho_janelas",
        "validade_dias": 30,
        "obs": "S-1200 é da Portte; aqui só o espelho de consulta",
    },
    {
        "numero": "folha de pagamento",
        "fonte": "fechamento da Portte (contabilidade externa)",
        "sql": "SELECT max(competence_end) FROM hr_payslips WHERE source_system='portte'",
        "validade_dias": 45,   # uma competência + folga do fechamento
        "obs": "Portte é fonte de verdade fiscal; nossa folha converge para ela",
    },
    {
        "numero": "notas fiscais de serviço",
        "fonte": "prefeitura / SEFAZ",
        # `nfses` (27 linhas, parada em 12/02) é LEGADA; a viva é nfse_emitidas_nacional.
        # Apontar para a tabela errada rendeu um "181 dias sem nota" que não existia —
        # âncora errada mente com a mesma confiança de âncora certa.
        "sql": ("SELECT greatest("
                "coalesce((SELECT max(data_emissao) FROM nfse_emitidas_nacional),'1900-01-01'),"
                "coalesce((SELECT max(data_emissao) FROM nfses),'1900-01-01'))::date"),
        "validade_dias": 45,
        "obs": "a tabela viva é nfse_emitidas_nacional; `nfses` e nfse_manaus_historico são histórico",
    },
]

_PSQL = ["docker", "exec", "conecta-pro-postgres", "psql", "-U", "postgres",
         "-d", "conecta_pro", "-t", "-A", "-c"]


def _consultar(sql: str) -> date | None:
    r = subprocess.run(_PSQL + [sql], capture_output=True, text=True)
    bruto = (r.stdout or "").strip().splitlines()
    if r.returncode != 0 or not bruto or not bruto[0].strip():
        return None
    try:
        return datetime.fromisoformat(bruto[0].strip()[:10]).date()
    except ValueError:
        return None


def avaliar(ancoras: list[dict], hoje: date, consultar=_consultar) -> list[dict]:
    out = []
    for a in ancoras:
        quando = consultar(a["sql"])
        if quando is None:
            out.append({**a, "quando": None, "idade": None, "status": "NUNCA"})
            continue
        idade = (hoje - quando).days
        if a["validade_dias"] is None:
            # a fonte traz o próprio prazo: o que importa é se já venceu
            status = "VENCIDA" if idade > 0 else "ok"
        else:
            status = "VELHA" if idade > a["validade_dias"] else "ok"
        out.append({**a, "quando": quando, "idade": idade, "status": status})
    return out


def _self_check() -> None:
    hoje = date(2026, 8, 12)
    falso = {
        "SELECT fresca": date(2026, 8, 12),
        "SELECT velha": date(2026, 1, 1),
        "SELECT vencida": date(2026, 8, 1),
        "SELECT nunca": None,
    }
    ancoras = [
        {"numero": "fresca", "fonte": "x", "sql": "SELECT fresca", "validade_dias": 2, "obs": ""},
        {"numero": "velha", "fonte": "x", "sql": "SELECT velha", "validade_dias": 2, "obs": ""},
        {"numero": "vencida", "fonte": "x", "sql": "SELECT vencida", "validade_dias": None, "obs": ""},
        {"numero": "nunca", "fonte": "x", "sql": "SELECT nunca", "validade_dias": 2, "obs": ""},
    ]
    got = {a["numero"]: a["status"] for a in avaliar(ancoras, hoje, falso.get)}
    assert got == {"fresca": "ok", "velha": "VELHA", "vencida": "VENCIDA", "nunca": "NUNCA"}, got

    # a âncora sem prazo próprio NÃO pode ser julgada pela régua de dias
    so_prazo = [{"numero": "vencida", "fonte": "x", "sql": "SELECT vencida",
                 "validade_dias": None, "obs": ""}]
    assert avaliar(so_prazo, date(2026, 7, 1), falso.get)[0]["status"] == "ok", \
        "certidão dentro da validade acusada como vencida"
    print("self-check OK — distingue fresca, velha, vencida e nunca provada, "
          "e respeita o prazo que a própria fonte carrega")


def main() -> int:
    hoje = date.today()
    linhas = avaliar(ANCORAS, hoje)
    ruins = [a for a in linhas if a["status"] != "ok"]

    print(f"{len(ANCORAS)} número(s) ancorado(s) em fonte externa "
          f"— {len(ruins)} sem confirmação válida:\n")
    for a in sorted(linhas, key=lambda x: (x["status"] == "ok", x["numero"])):
        quando = a["quando"].isoformat() if a["quando"] else "—"
        idade = f"{a['idade']}d" if a["idade"] is not None else "—"
        marca = "  " if a["status"] == "ok" else "x "
        print(f"{marca}{a['numero']:<26} {a['status']:<8} {quando}  ({idade})")
        print(f"    fonte: {a['fonte']}")
        if a["status"] != "ok" and a["obs"]:
            print(f"    ⚠ {a['obs']}")

    print("\nÂNCORA AUSENTE É O PIOR ACHADO: o número que ninguém de fora confirma não "
          "aparece nesta lista.\nLeia com `--listar` e pergunte o que está faltando.")
    print(f"TOTAL: {len(ruins)}")   # linha canônica lida por checar_regressao.py
    return 1 if ruins else 0


if __name__ == "__main__":
    if "--self-check" in sys.argv:
        _self_check()
        raise SystemExit(0)
    if "--listar" in sys.argv:
        for a in ANCORAS:
            prazo = f"{a['validade_dias']}d" if a["validade_dias"] else "prazo da própria fonte"
            print(f"  {a['numero']:<26} <- {a['fonte']}  ({prazo})")
        raise SystemExit(0)
    raise SystemExit(main())
