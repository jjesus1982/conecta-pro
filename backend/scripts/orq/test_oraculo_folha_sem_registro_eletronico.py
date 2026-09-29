"""A folha de ponto imprime o mês INTEIRO, e grade de escala nunca se disfarça de batida.

🔴 MEDIDO EM 28/09/2026, competência agosto. Das **3.420 batidas do mês, só 1.390 são MEDIÇÃO**
(41%). O resto é grade: o Tangerino traz **65% das batidas em hora cheia** e o `web` tem
**4 horários distintos para 414 batidas**. `FONTES_MEDIDAS` corretamente não conta isso — e a
consequência é que os 68 espelhos de agosto têm média de **9,2 dias** num mês de 31.

A tabela deste PDF percorria só `dias`, então a folha de ponto que iria para 7 condomínios de
cliente sairia com ~9 linhas num mês de 31. **Folha com dois terços do mês ausente não é folha
incompleta, é folha que esconde.**

Decisão do Jordan («2», 28/09): o dia existe na página, rotulado «Sem registro eletrônico», com
o horário da escala ao lado apenas como referência.

## O que este oráculo trava

1. **O calendário é do PERÍODO, não da lista de dias medidos.** Se voltar a percorrer `dias`, a
   folha volta a esconder o mês.
2. **⭐ A grade sai SEMPRE marcada.** Nunca um horário nu na coluna de pontos: `(ref. …)` e o
   rótulo da ocorrência. Horário de escala impresso como batida é fabricação de registro
   trabalhista — é a asserção mais importante deste arquivo.
3. **A nota de pé existe quando há o caso.** Sem ela «Sem registro eletrônico» é lido como
   FALTA, que é o contrário do que o rótulo diz.
4. **Sem grade, não inventa.** Dia sem medição e sem escala sai «—», nunca 00:00.

⚠️ Afirma a REGRA: monta o espelho com dados sintéticos, sem nome, id ou data de ninguém.
"""

import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, "/app")

import pymupdf  # noqa: E402

from modules.people_management.hr.services.espelho_ponto_pdf import (  # noqa: E402
    montar_espelho_ponto_pdf,
)


def _texto(pdf: bytes) -> str:
    d = pymupdf.open(stream=pdf, filetype="pdf")
    try:
        return "".join(p.get_text() for p in d)
    finally:
        d.close()


#: Espelho sintético: agosto tem 31 dias e só DOIS medidos — a proporção real de 09/2026.
ESP = {
    "employee_name": "COLABORADOR SINTETICO",
    "mes": 8,
    "ano": 2026,
    "dias": [
        {"date": "2026-08-04", "entrada": "06:03", "saida": "18:07", "worked": 724, "expected": 720},
        {"date": "2026-08-06", "entrada": "05:58", "saida": "18:01", "worked": 723, "expected": 720},
    ],
}
#: A grade em hora CHEIA, que é justamente a assinatura do Tangerino.
GRADE = {"2026-08-08": "06:00 18:00", "2026-08-10": "06:00 18:00"}


def main() -> None:
    txt = _texto(montar_espelho_ponto_pdf(dict(ESP), grade=dict(GRADE)))

    # 1 — o mês INTEIRO está na página
    dias_impressos = len(re.findall(r"\b\d{2}/08\b", txt))
    assert dias_impressos >= 31, (
        f"a folha imprimiu {dias_impressos} linhas de dia num mês de 31 — voltou a percorrer só "
        "os dias medidos, e o cliente recebe folha de ponto com o mês escondido"
    )

    # 2 — ⭐ A ASSERÇÃO QUE PROTEGE O DOCUMENTO: a grade nunca aparece nua.
    assert "ref. 06:00 18:00" in txt, (
        "o horário de escala deixou de sair marcado como referência — se ele aparecer sem o "
        "«ref.», passa a ser lido como batida, e horário que ninguém marcou virou registro de "
        "ponto num documento assinado"
    )
    # Nenhum «06:00 18:00» pode existir FORA de um «ref. …». Conta as duas coisas.
    nus = len(re.findall(r"(?<!ref\. )06:00 18:00", txt))
    assert nus == 0, (
        f"{nus} ocorrência(s) de horário de grade SEM o prefixo «ref.» — é exatamente a "
        "fabricação que esta casa proíbe"
    )
    # O rótulo QUEBRA EM LINHAS na coluna estreita (o extrator devolve "Sem registro\neletrônico"),
    # então a contagem tolera espaço em branco no meio. Buscar a frase colada devolvia 0 num PDF
    # que tinha 29 — teste que mede o layout em vez do conteúdo reprova código correto.
    n_rot = len(re.findall(r"Sem\s+registro\s+eletr", txt))
    assert n_rot >= 29, (
        "os dias sem medição perderam o rótulo «Sem registro eletrônico» — sem ele o leitor não "
        f"tem como distinguir dia não marcado de dia trabalhado (achei {n_rot})"
    )

    # 3 — a nota que impede a leitura «falta»
    assert "não foi computado nas horas trabalhadas" in txt, (
        "a nota de pé sumiu: «Sem registro eletrônico» sem explicação é lido como FALTA, que é o "
        "oposto do que o rótulo afirma"
    )

    # 4 — sem grade, não inventa. Folha de mês COMPLETO não leva nota (não vira ruído).
    esp_cheio = dict(ESP)
    esp_cheio["dias"] = [
        {"date": f"2026-08-{d:02d}", "entrada": "06:00", "saida": "18:00", "worked": 720, "expected": 720}
        for d in range(1, 32)
    ]
    txt_cheio = _texto(montar_espelho_ponto_pdf(esp_cheio))
    assert not re.search(r"Sem\s+registro\s+eletr", txt_cheio), (
        "mês inteiro medido e a folha ainda diz «Sem registro eletrônico» — alarme que toca "
        "sempre ninguém lê"
    )
    assert "não foi computado nas horas trabalhadas" not in txt_cheio, (
        "a nota apareceu num mês completo: ela tem de existir só quando existe o caso"
    )
    # E sem grade nenhuma, o dia não medido não ganha hora inventada.
    #
    # ⚠️ O escopo é a TABELA DIÁRIA, não o documento: «TOTAIS DO PERÍODO · Horas trabalhadas»
    # legitimamente imprime 00:00 quando não há total. A primeira versão desta asserção varria o
    # PDF inteiro e reprovava por causa do rodapé — medir o lugar errado é o defeito que este
    # projeto mais paga, e ele não poupa quem escreve o oráculo.
    txt_sem_grade = _texto(montar_espelho_ponto_pdf(dict(ESP)))
    tabela = txt_sem_grade.split("TOTAIS DO PERÍODO")[0]
    assert "00:00" not in tabela, (
        "apareceu 00:00 na tabela diária de um dia sem medição e sem escala — zero pareceria "
        "marcação real"
    )

    print(f"OK o mês inteiro está na folha ({dias_impressos} linhas de dia, 2 medidos)")
    print("OK a grade sai como «ref. …» e NUNCA nua — 0 horário de escala disfarçado de batida")
    print(f"OK {n_rot} dias rotulados + nota de pé explicando")
    print("OK mês completo não leva rótulo nem nota · dia sem escala não ganha 00:00")
    print("TEST oraculo_folha_sem_registro_eletronico PASS")


if __name__ == "__main__":
    main()
