---
name: entregue-de-verdade
description: Checagem antes de dizer "pronto/funcionando/entregue" no Conecta PRO. Substitui superpowers:verification-before-completion aqui — a diferença é que neste sistema "feito" e "entregue" são estados distintos, e três coisas específicas separam um do outro. Use antes de QUALQUER frase de conclusão, e sempre que for reportar resultado ao Jordan.
---

# Entregue de verdade — Conecta PRO

`verification-before-completion` genérico diz: não afirme o que não verificou. Correto, e
insuficiente aqui. Neste sistema existe um estado intermediário que engana:

> **FEITO** = o código está certo e o teste passa.
> **ENTREGUE** = a pessoa que abre o sistema vê o resultado.

Em 12/08/2026 eu disse "pronto" três vezes estando apenas em FEITO.

## Os três portões

Faltando **um**, não é entregue:

### 1. Servido pela ROTA REAL, depois do bake

`docker cp` **não recarrega módulo já importado** pelo servidor. O oráculo roda `python3`
novo e enxerga a mudança; a API continua com o código velho em memória.

```bash
# depois do bake, com token real
curl -s "http://localhost:8080/api/v1/redesign/data/<slug>" -H "Authorization: Bearer $TK"
```

Caso real: as telas multi-CNPJ tinham 3 oráculos verdes e a rota devolvia `AUSENTE` para as
três. Só o bake entregou.

### 2. Oráculo verde — e que PEGA o defeito

Oráculo que passa antes e depois do conserto não prova nada. Rode-o contra o código anterior
e veja falhar:

```bash
git show HEAD:backend/<arquivo> > /tmp/ANTES.py
docker cp /tmp/ANTES.py conecta-pro-backend:/app/<arquivo>
docker exec -e PYTHONPATH=/app conecta-pro-backend python3 /app/scripts/orq/<oraculo>.py  # tem que FALHAR
```

### 3. Nenhuma superfície nova sem vigia

Tela, KPI ou número novo sem oráculo é dívida no dia em que nasce. O Balanço Patrimonial
ficou meses exibindo PL de +R$ 2,02 milhões onde havia prejuízo de R$ 97 mil — não havia
oráculo contábil, e nada apontava a ausência.

## O que NÃO conta como verificação

| Isso | Por que não basta |
|---|---|
| "o endpoint respondeu 201" | `type:"form"` descarta o corpo; calculadora pode devolver o número e a tela jogar fora |
| "o status voltou `criada`" | o sync de CND devolveu `criada` com o portal FORA DO AR. A prova é o número do documento, não o status da operação |
| "o teste passa" | ver portão 2 |
| "está no commit" | ver portão 1 |
| ausência de erro | silêncio não é aprovação — "NÃO VERIFICADO" é resultado válido |

## ⭐ Heurística sobre texto de código erra nos DOIS sentidos

Grep/regex sobre corpo de função **não é conservador**: infla e zera. Seis medições erradas num
único dia (24/08/2026), três para mais e três para menos:

| o que eu media | disse | é |
|---|---|---|
| período no corpo do handler (sem seguir helper) | 11 sem servidor | **1** |
| equivalência de capacidade por NOME | 112 lacunas | **43** |
| prefixo exigindo aspas coladas | **0** fora do padrão | 23 |
| marca de teste por CITAÇÃO no arquivo | 6 sem marca | **27** |
| limpeza de entrada exigindo literal `'ZZ` | 29 sem entrada | 20 |
| desmonte só como `DELETE … LIKE` | 20 sem entrada | 18 |

⚠️ **O mais perigoso dos seis foi o `0`, não os inflados.** Número inflado alguém confere;
zero ninguém confere, porque parece boa notícia. `0 fora do padrão` significava "meu regex não
achou nada", e foi lido como "está tudo certo".

⚠️ A sexta é a que fecha o argumento: o detector **não reconheceu dois desmontes que eu tinha
acabado de escrever**, porque um usava `UPDATE … LIKE` e o outro `DELETE … strpos`.

**Antídoto, nesta ordem:**

1. **Prefira COMPORTAMENTO a FORMA.** Onde der para executar, execute:
   `roda · conta antes · conta depois` não tem como fugir; nenhum regex sabe quantas formas de
   escrever um `DELETE` existem. Foi a troca que consertou a condição 2 do `fechado_bartolo`
   (procurava nome de variável no fonte → virou sonda contra o serviço no ar) e a trava de
   desmonte dos oráculos.
2. **Meça a mesma coisa por outro caminho e desconfie quando divergir.** Os seis foram pegos
   assim, nenhum por releitura do regex.
3. **Confira um a um antes de travar.** Trava que grita sem motivo é trava que se aprende a
   ignorar — e a que zera é pior, porque ninguém volta nela.

## Ao reportar ao Jordan

Diga nesta ordem: **o número medido**, depois a conclusão. Nunca o contrário.

- ✅ "obrigações em aberto: 54 → 28; valor R$ 214.226,97 → R$ 92.965,65"
- ❌ "corrigi o filtro de obrigações"

E diga o que **não** foi coberto. Toda vez. Em 11/08 a lente TELA ficou sem navegador
(Playwright indisponível) e isso foi dito no relatório — silêncio ali teria virado
"verificado" na cabeça de quem lê.

## Autocorreção

Se você já afirmou algo e depois mediu diferente, **corrija na hora, com o número**, e siga.
Sem preâmbulo, sem autoflagelo. Exemplo real: "o erro do faturamento é de 4%, não de 2,6× —
comparei com uma tabela só."
