---
name: oraculo-conecta
description: Como ESCREVER um oráculo no Conecta PRO (backend/scripts/orq/) que não apodrece. Substitui superpowers:test-driven-development aqui — não é ciclo vermelho-verde-refatora, é uma checagem executável por lógica não-trivial, que afirma a REGRA e não a fotografia. Use ao criar qualquer oráculo, e ao consertar oráculo que ficou vermelho por mudança legítima do sistema.
---

# Oráculo — Conecta PRO

Há 65 em `backend/scripts/orq/`. Rodam sozinhos às 05:00; vermelho vira alerta no sino.

TDD genérico assume teste de unidade sobre código novo. Aqui o oráculo compara **o que a
tela mostra** com **o que o banco tem**, em produção, num sistema que muda por baixo. O
inimigo não é o bug — é o oráculo virar mentira e ninguém perceber.

## A regra que governa tudo: afirme a REGRA, nunca a fotografia

Em 11–12/08/2026, das 16 falhas de oráculo, **15 não eram defeito de produto**. Eram
retratos congelados:

| Congelado | O que aconteceu | Como escrever |
|---|---|---|
| `WHERE email='fulano@…'` | a pessoa saiu; 4 oráculos estouraram em NoneType | por PAPEL: `_fixtures.exigir_usuario(db, "supervisor")` |
| `nomes == {4 tools}` | o produto GANHOU 4 capacidades e o teste reprovou a melhoria | núcleo ⊆ conjunto + "nada org-wide entra" |
| `scr["slug"]` | telas viraram abas; slug virou stub `redirect` | `_fixtures.tela(scr, slug)` |
| `type == "dash"` | a tela virou chat de propósito | afirme o que importa: rota existe, campo certo, lente certa |
| `"lider": {"sst"}` | permissão daquele usuário mudou | trave a TRADUÇÃO permissão→módulo, com usuário sintético |
| UUID fixo de pessoa | | pré-condição: "um colaborador com batidas" |

Pergunta a se fazer em cada asserção: **isto continua verdade se o sistema melhorar?** Se
não, você congelou dado.

## Compare com a VERDADE, não com a query que você audita

O QA de 09/08 conferiu os KPIs do fiscal contra as queries do builder e aprovou. Batiam — a
query é que estava errada (`NOT IN ('pago',…)` numa tabela que diz `'cumprida'`: 31
anunciadas, 5 reais).

**Escreva a consulta de verdade de forma independente, no oráculo.** Se ela for um
copy-paste da query do builder, o oráculo só prova que você sabe copiar.

## Prove que o oráculo PEGA

Oráculo que nunca viu vermelho não vale. Rode contra o código anterior:

```bash
git show HEAD:backend/<arquivo> > /tmp/ANTES.py
docker cp /tmp/ANTES.py conecta-pro-backend:/app/<arquivo>
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/<oraculo>.py   # FALHA
docker cp backend/<arquivo> conecta-pro-backend:/app/<arquivo>                              # restaura
```

## Suspenders: trave a volta do defeito exato

Além da asserção principal, uma que impeça o erro específico de voltar:

```python
# o KPI não pode voltar a ser o TOTAL de obrigações (foi o defeito original)
if total != pendentes:
    assert kpi["v"] != str(total), "voltou a contar todas como abertas"
```

## Invariante > valor

O melhor oráculo do módulo contábil não fixa números: fixa **Ativo = Passivo + PL**. Mês
novo entra sozinho; erro de classificação futuro reprova sozinho. Procure a identidade do
domínio antes de fixar um número.

## Forma

```python
"""<O que prova>. <Por que existe — o defeito real que motivou, com números.>"""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from _fixtures import exigir_usuario, tela   # papel, resolvedor de redirect

async def main() -> None:
    async with async_session_factory() as db:
        ...
        print("OK <o que passou, com o número>")
    print("TEST <nome> PASS")

if __name__ == "__main__":
    asyncio.run(main())
```

- **versione**: oráculo fora do git some no próximo clone;
- **nome `test_*.py`** em `backend/scripts/orq/` — a varredura diária pega sozinha;
- **limpe o que escrever — na ENTRADA e na saída, e por PREFIXO**. A de saída (`finally`) é
  para o caso normal; a de entrada é para quando **não houve saída**: execução morta por sinal
  não roda `finally` nenhum. Um assert vermelho deixou 4 apontamentos de teste numa folha de
  produção; uma execução abandonada deixou **15 registros `ZZE2E` no CRM**, e separá-los dos
  leads reais deu trabalho.
  ⚠️ **Apague por prefixo, nunca pela lista de ids que a execução gerou** — a execução que
  morreu não deixa a lista dela para a seguinte, então limpar por id só limpa o próprio lixo,
  e o lixo órfão é exatamente o que sobra. Use prefixo fixo (`ZZ…`): além de casar com o
  abandonado, ordena no fim de qualquer listagem alfabética, então o que escapar aparece
  agrupado em vez de escondido no meio do dado real;
- **imprima o número**, não só "OK" — é o que permite conferir sem reler o código.

## Quando NÃO escrever oráculo

Lógica trivial (um `if`, um formatador). Ponytail vale aqui: YAGNI se aplica a teste também.
O gatilho é **lógica não-trivial**: um cálculo, uma classificação, um gate, um caminho de
dinheiro/fisco/governo.
