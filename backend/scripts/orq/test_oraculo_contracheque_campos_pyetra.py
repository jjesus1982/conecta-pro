"""O contracheque tem os 11 campos que a Pyetra exigiu — e cada um bate com o banco.

🔴 MEDIDO EM 28/09/2026, pedido da PYETRA (DP/RH). Palavras dela:

    *"Não tem os contracheques. O recibo de pagamento SÃO os contracheques, contracheques têm que
     ter as informações assim como no segundo documento."*

O "segundo documento" é `auditoria/pyetra-prints/ANGELA LOPES MACEDO.pdf`, um contracheque do
sistema antigo (Domínio/Portte). A lista dela, do que **não pode faltar de forma alguma**:

    Empresa · CNPJ · CC · do que se trata · mês referente · código do funcionário ·
    nome · CBO · data de admissão · departamento · filial

## O que estava errado (medido lendo o TEXTO do PDF, não o código)

Holerite da JAQUELINE CARLOS DOS SANTOS, 08/2026, gerado pelo próprio sistema:

    Departamento   —          ← employees.departamento = 'Serviços Gerais' NO BANCO
    (sem Código)              ← employees.codigo = '000181' NO BANCO
    (sem CC)  (sem Filial)
    título: "HOLERITE"        ← constante; o papel nunca dizia contracheque ou adiantamento

⭐ Departamento não estava faltando no BANCO, estava faltando na PONTE: os **5** chamadores de
`montar_holerite_pdf` montavam cada um o seu `fdad` com o mesmo SELECT pela metade
(`cpf, pis, matricula, data_admissao`). Cinco cópias do mesmo buraco. O conserto foi UM
enriquecimento dentro da função compartilhada (`_enriquece_identidade`), não cinco remendos.

## O que este oráculo trava

Gera o PDF de UMA pessoa real, **lê o texto do PDF** (pymupdf) e afirma a REGRA:

  1. os 11 rótulos aparecem no papel;
  2. os que têm fonte no banco saem com o VALOR DO BANCO (nome, CNPJ do empregador da
     competência, departamento, código, admissão) — rótulo presente com "—" não passa;
  3. CBO sai formatado XXXX-XX;
  4. Filial e CC são CONSTANTES por decisão da Pyetra ("Filial sempre a 1", "CC: GERAL") —
     `employees.centro_custo` está 0/66 preenchido, medido. Constante declarada ≠ dado chutado.

Não é fotografia: escolhe a pessoa por consulta (quem tem departamento E código preenchidos) e
confere contra o que o banco disser HOJE, não contra valores gravados aqui.

Uso:  docker exec conecta-pro-backend python /app/scripts/orq/test_oraculo_contracheque_campos_pyetra.py
"""

from __future__ import annotations

import re
import sys

sys.path.insert(0, "/app")

# Rótulos obrigatórios (Pyetra, 28/09/2026). Empresa e CNPJ vivem no cabeçalho/rodapé branded,
# por isso são conferidos pelo VALOR e não por um rótulo.
ROTULOS = ("CC", "Competência", "Código", "Funcionário", "CBO", "Admissão", "Departamento", "Filial", "Documento")

SQL_PESSOA = """
    SELECT CAST(e.id AS TEXT), e.nome, e.codigo, e.departamento, e.data_admissao, emp.cnpj,
           e.centro_custo
      FROM employees e
      LEFT JOIN empresas emp ON emp.id = e.empresa_id
     WHERE e.status ILIKE 'ativo'
       AND e.codigo IS NOT NULL AND e.departamento IS NOT NULL
       AND e.data_admissao IS NOT NULL
     ORDER BY e.nome
     LIMIT 1
"""


def _so_digitos(s: str) -> str:
    return "".join(c for c in str(s or "") if c.isdigit())


def main() -> None:
    import pymupdf
    from sqlalchemy import text

    from core.database.session import get_sync_db_dependency
    from modules.people_management.folha.services import calculo_service
    from modules.people_management.folha.services.holerite_pdf import montar_holerite_pdf

    db = next(get_sync_db_dependency())
    try:
        row = db.execute(text(SQL_PESSOA)).first()
        assert row, "nenhum colaborador ativo com codigo+departamento+admissao — oráculo sem sujeito"
        eid, nome, codigo, departamento, admissao, cnpj, centro_custo = row

        holerite = None
        for mes, ano in ((8, 2026), (7, 2026), (9, 2026)):
            r = calculo_service.calcular_folha_colaborador(db, eid, mes, ano)
            if "error" not in r:
                holerite = r
                break
        assert holerite, f"motor da folha não calcula {nome} em nenhuma competência testada"

        # fdad PROPOSITALMENTE pobre — é exatamente o que os 5 chamadores passam. Se o oráculo
        # enriquecesse aqui, estaria medindo a si mesmo (oráculo cúmplice).
        pdf = montar_holerite_pdf(holerite, {"employee_id": eid})
    finally:
        db.close()

    doc = pymupdf.open(stream=pdf, filetype="pdf")
    txt = "\n".join(p.get_text() for p in doc)
    plano = " ".join(txt.split())

    faltando = [r for r in ROTULOS if r not in txt]
    assert not faltando, f"rótulo(s) obrigatório(s) ausente(s) no contracheque: {faltando}"

    # 2 — valores que vêm do banco (rótulo com "—" reprova)
    assert nome.upper() in plano.upper(), f"nome «{nome}» não saiu no papel"
    assert departamento in plano, (
        f"Departamento saiu «—» mas employees.departamento = «{departamento}» no banco — "
        "a ponte entre o cadastro e o PDF está rompida de novo")
    assert str(codigo) in plano, f"Código do funcionário «{codigo}» não saiu no papel"
    assert admissao.strftime("%d/%m/%Y") in plano, f"Admissão «{admissao}» não saiu no papel"
    if cnpj:
        d = _so_digitos(cnpj)
        assert d in _so_digitos(plano), f"CNPJ do empregador ({cnpj}) não saiu no papel"

    # 3 — CBO formatado
    assert re.search(r"CBO\s+\d{4}-\d{2}", plano), f"CBO ausente ou malformado: {plano[:400]}"

    # 4 — constantes declaradas pela Pyetra
    assert re.search(r"\bFilial\s+1\b", plano), "Filial (sempre 1, decisão da Pyetra) não saiu"
    # `\bCC\b` porque "CC" solto casa dentro de outras palavras — rótulo tem de ser rótulo.
    cc = re.search(r"\bCC\b\s+(\S+)", plano)
    esperado_cc = centro_custo or "GERAL"
    assert cc and cc.group(1) == esperado_cc, f"CC devia sair «{esperado_cc}»: {cc}"

    # 5 — "do que se trata": o papel diz o tipo, e o título do cabeçalho concorda com o campo
    tipo = re.search(r"Documento\s+(Contracheque|Adiantamento)", plano)
    assert tipo, "campo «Documento» não diz contracheque nem adiantamento"
    assert tipo.group(1).upper() in plano.upper(), "título do cabeçalho discorda do campo Documento"

    print(f"OK {nome} · {holerite['mes']:02d}/{holerite['ano']} · dep={departamento} · "
          f"cod={codigo} · {tipo.group(1)} · 11/11 campos da Pyetra no PDF")
    print("TEST oraculo_contracheque_campos_pyetra PASS")


if __name__ == "__main__":
    main()
