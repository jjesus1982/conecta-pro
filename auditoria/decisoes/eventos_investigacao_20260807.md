# Investigação — `gedeon.cliente.espelhar` e `dp.ponto.registrado` (2026-08-07)

Os dois casos que ficaram marcados como "investigar" na fila de eventos. READ-ONLY: nada
foi alterado. Ambos são **decisão sua** — um é arquitetura, o outro é produto.

---

## 1 · `gedeon.cliente.espelhar` — uma cascata inacabada

**Não é lixo.** É uma ordem que ninguém executa.

### O que é

Nasce dentro do handler `_on_cliente_ativo` (`gedeon.py:527`), que reage a
`crm.cliente.ativo`. Ou seja, é um evento de **segundo nível**: cliente vira ativo → GEDEON
anota o tipo de kit → e então publica isto:

```python
event_type="gedeon.cliente.espelhar",
payload={
    "cliente_id": ..., "nome": ..., "tipo_contrato": ...,
    "servicos": [...],
    "modulos": ["ged", "operacional", "financeiro", "fiscal", "portal"],   # ← a ordem
}
```

O campo `modulos` é literalmente uma **lista de quem deveria agir**. O GEDEON está pedindo a
cinco módulos que espelhem o cliente novo.

### O estado

| | |
|---|---|
| Disparos medidos | **10** |
| Assinantes | **0** — nenhum dos 5 módulos ouve |
| No catálogo `EventTypes` | **não** — é string literal ad-hoc, fora da convenção |

**Consequência real:** quando um cliente vira ativo, os 5 módulos não sabem. Alguém cadastra
o cliente em cada um na mão, ou não cadastra.

### Decisão

- **(a) Formalizar e implementar** — pôr no catálogo como `GEDEON_CLIENTE_ESPELHAR` e escrever
  um subscriber por módulo. É trabalho real: cada um precisa saber o que "espelhar cliente"
  significa no seu domínio (criar posto? abrir régua de faturamento? criar pasta no GED?).
  ⚠️ O de operacional criaria posto — seu território.
- **(b) Formalizar só no catálogo** e implementar 1 ou 2 módulos por vez, começando pelo GED
  (é documental, não toca operação nem dinheiro).
- **(c) Remover** — se o espelhamento é feito à mão de propósito e ninguém quer automatizar.

**Recomendo (b), começando pelo GED.** Tira o evento da informalidade sem prometer os cinco.

⚠️ **Independente da escolha:** um evento fora do catálogo é dívida por si só. Ninguém
descobre que ele existe lendo `EventTypes`. Eu só o achei lendo o stream do Redis.

---

## 2 · `dp.ponto.registrado` × `ponto.batida.registrada` — dois sistemas de ponto

**Não é duplicata de evento. É duplicata de SUBSISTEMA**, e o barramento só a tornou visível.

### Os dois caminhos

| | `dp.ponto.registrado` | `ponto.batida.registrada` |
|---|---|---|
| Publica em | `hr/publishers.py:242` | `ponto/publishers.py:39` |
| Chamado por | `hr/controllers/time_tracking_controller.py`<br>`hr/controllers/time_record_controller.py` (**4 pontos**) | `ponto/controllers/punch_controller.py` (**1 ponto**) |
| Grava em | `gp_clock_punches` | `gp_clock_punches` |
| Payload | `employee_id`, `tipo`, `record_id` | `punch_id`, `employee_id`, nome, `punch_type`, **timestamp**, **lat/lng**, **cliente_id** |
| Disparos | 3 | 8 |
| Assinantes | 0 | 0 |

**Os dois gravam na mesma tabela.** É o mesmo fato do mundo — "alguém bateu ponto" —
anunciado por dois códigos diferentes, com nomes diferentes e payloads diferentes.

### Por que isso importa mais do que parece

1. **Já apareceu antes, por outro ângulo.** O raio-x do DP registrou: *"existem
   `POST /ponto/batida/me` e `POST /hr/time-records/clock-in` — investigar qual é a canônica
   antes de wirar qualquer uma"*. É o mesmo problema visto do lado da rota.
2. **É a mesma família do defeito de pareamento** que consertei hoje: havia **três**
   implementações de pareamento de batida e só duas tinham sido alinhadas. Ponto é o
   subsistema com mais cópias no sistema.
3. **Quem assinar corre risco de contar dobrado.** Se um dia alguém ligar um subscriber em
   `ponto.batida.registrada` para atualizar presença, e outro em `dp.ponto.registrado`, a
   mesma batida conta duas vezes — dependendo de por qual tela foi registrada.

### Qual é o canônico

Pela evidência, **`ponto.batida.registrada`**:

- payload mais rico: traz `punch_timestamp`, `cliente_id` e geolocalização
- `cliente_id` é o que o `gedeon_context` precisa — sem ele, nenhum handler do GEDEON funciona
- nasce no módulo `ponto`, que é o dono do domínio
- o `dp.ponto.registrado` não carrega nem o horário da batida

### Decisão

- **(a) Eleger `ponto.batida.registrada` como único** e fazer os 4 pontos de chamada do HR
  publicarem ele. ⚠️ Mexe em `hr/controllers`, território do DP — há terminal ativo lá.
- **(b) Manter os dois** e documentar que `dp.ponto.registrado` é legado do caminho clássico,
  que morre junto com o clássico.
- **(c) Depreciar** `dp.ponto.registrado`: marcar no catálogo, parar de publicar, remover
  quando o caminho clássico do HR for desligado.

**Recomendo (c).** É a que reconhece a realidade — o caminho clássico vai ser desligado de
qualquer forma — sem forçar refatoração agora num módulo com terminal ativo.

⚠️ **Não ligue subscriber em nenhum dos dois** até isto estar decidido. Ligar nos dois conta
dobrado; ligar em um só perde as batidas do outro caminho.

---

## Resumo

| Caso | Natureza | Recomendo |
|---|---|---|
| `gedeon.cliente.espelhar` | cascata inacabada, fora do catálogo | formalizar + implementar só o GED |
| `dp.ponto.registrado` | duplicação de subsistema, não de evento | depreciar; canônico é `ponto.batida.registrada` |

Nenhum dos dois foi alterado. O segundo, em particular, **não deve receber subscriber** até
você decidir qual é o canônico.
