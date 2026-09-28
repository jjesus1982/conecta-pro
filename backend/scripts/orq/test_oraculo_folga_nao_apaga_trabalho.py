"""Folga não conta como falta — e dia trabalhado nunca vira folga.

🔴 PEDIDO DA PYETRA, 28/09/2026: *"quando o funcionário folga em um dia para trabalhar no outro,
na sólides o dia não trabalhado é colocado 'folga', pois assim não tem desconto"*.

⭐ A capacidade existia INTEIRA e nunca foi ligada. Medido no dia:

| medida | valor |
|---|---|
| `shifts.is_off_day = true` | **40 linhas, todas de agosto/2026** |
| código de produção que ESCREVE nessa coluna | **nenhum** (só a migração, com default false) |
| dias de escala sem batida em setembro | **110, de 33 pessoas** |

O custo de não marcar, lido no próprio `espelho_service`: dia de escala sem batida e sem
cobertura soma `_esperado_turno` ao esperado (**débito de jornada no saldo**) e faz
`dsr_entitled = False` (**perde o DSR da semana**).

## O que este oráculo trava

1. **O espelho continua PULANDO o dia marcado como folga.** É a razão de existir da coluna; se
   alguém tirar essa guarda, a marcação da Pyetra passa a não servir para nada e ninguém nota —
   a tela seguiria mostrando o botão.
2. **⭐ Dia com batida NÃO pode virar folga.** É a trava que protege a pessoa: marcar folga num
   dia trabalhado apagaria trabalho pago. Afirmada na ROTA, que é quem recebe o clique.
3. **Dia sem turno recusa** em vez de fingir sucesso — é caso diferente (o extra não lançado).
4. **A rota grava trilha e prova por leitura posterior.** Ato que decide desconto de folha sem
   rastro é pior que ato nenhum, e `UPDATE n` não é prova.

⚠️ Afirma a REGRA, nunca a fotografia: nenhum nome, id ou data. As 40 linhas de agosto podem
virar 400 sem o oráculo piscar.
"""

import ast
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

_ESPELHO = "/app/modules/people_management/hr/services/espelho_service.py"
_ROTA = "/app/modules/operacional/controllers/redesign_builders/_dgx_f7_ponto.py"


def _fonte(caminho: str) -> str:
    with open(caminho, encoding="utf-8") as fh:
        return fh.read()


def main() -> None:
    esp = _fonte(_ESPELHO)

    # 1 — o espelho pula o dia de folga ANTES de transformá-lo em falta.
    assert "is_off_day" in esp, (
        "`is_off_day` desapareceu do espelho — a folga que a Pyetra marca deixaria de ser "
        "respeitada e o dia voltaria a virar falta, sem ninguém notar"
    )
    arvore = ast.parse(esp)
    # A guarda tem de ser um `continue` guardado por is_off_day, dentro do laço que gera
    # `dia_sem_batida`. Verifica na ÁRVORE: texto solto poderia estar só num comentário.
    guardas = 0
    for no in ast.walk(arvore):
        if not isinstance(no, ast.If):
            continue
        cond = ast.unparse(no.test)
        if "is_off_day" in cond and any(isinstance(c, ast.Continue) for c in no.body):
            guardas += 1
    assert guardas >= 1, (
        "nenhum `if ... is_off_day ...: continue` no espelho — a folga virou texto decorativo. "
        "Sem essa guarda, marcar folga não impede o débito de jornada nem a perda do DSR"
    )

    rota = _fonte(_ROTA)

    # 2 — ⭐ A TRAVA QUE PROTEGE A PESSOA: dia com batida não vira folga.
    assert "ponto-marcar-folga" in rota, (
        "a rota /action/ponto-marcar-folga sumiu — a Pyetra volta a não ter porta nenhuma para "
        "marcar folga, e a coluna volta a ser capacidade desligada"
    )
    arv_rota = ast.parse(rota)
    fn = next(
        (n for n in ast.walk(arv_rota)
         if isinstance(n, ast.AsyncFunctionDef) and n.name == "rd_ponto_marcar_folga"),
        None,
    )
    assert fn is not None, "rd_ponto_marcar_folga desapareceu"
    corpo = ast.unparse(fn)
    assert "gp_clock_punches" in corpo and "409" in corpo, (
        "a rota de folga não consulta mais as batidas do dia antes de marcar (ou perdeu o 409). "
        "Marcar folga num dia trabalhado APAGA trabalho pago — esta é a trava que protege a "
        "pessoa, e ela tem de recusar, não avisar"
    )
    # 3 — dia sem turno recusa em vez de fingir sucesso
    assert "404" in corpo, (
        "a rota deixou de recusar dia sem turno lançado. Fingir sucesso ali esconde um caso "
        "DIFERENTE (o extra que ninguém lançou) atrás de uma mensagem de êxito"
    )
    # 4 — trilha obrigatória e prova por leitura posterior
    assert "gp_audit_logs" in corpo, (
        "a rota de folga não grava mais trilha — ato que decide desconto de folha sem rastro"
    )
    assert "db.commit" in corpo, (
        "a rota perdeu o commit: `flush` sem commit já fez uma rotina desta casa relatar "
        "sucesso e gravar nada"
    )
    assert corpo.count("SELECT count(*) FROM shifts") >= 1 and "não se confirmou na leitura" in corpo, (
        "a rota deixou de CONFERIR por leitura posterior o que gravou. A linha «UPDATE n» do "
        "driver já mentiu nesta casa; o que vale é o estado depois do commit"
    )

    print(f"OK o espelho pula o dia de folga ({guardas} guarda(s) na árvore, não no comentário)")
    print("OK dia com batida é RECUSADO (409) — folga nunca apaga trabalho pago")
    print("OK dia sem turno é RECUSADO (404) — não finge sucesso sobre outro problema")
    print("OK a rota grava trilha, dá commit e confere por leitura posterior")
    print("TEST oraculo_folga_nao_apaga_trabalho PASS")


if __name__ == "__main__":
    main()
