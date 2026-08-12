# MVP — fechar `serviços` com o Arsenal (2026-08-12)

Módulo escolhido por ser pequeno. O objetivo era duplo: fechar o módulo e **testar o Arsenal
pelo uso**. O segundo rendeu mais que o primeiro — de novo.

> **Serviços é casca, e isso é diagnóstico, não desculpa.** 54 rotas montadas, 0 ordens no
> banco, e a tela do redesign mostra outra coisa (diaristas e contratos, lendo a tabela
> legada `ordens_servico` — não `service_orders`, que é a do módulo).

---

## 1. O que ficou fechado

| Dimensão | Antes | Depois | Prova |
|---|---|---|---|
| Chamada a método inexistente (backend) | 78 | **0** | `checar_repositorio` · sistema 139 → 61 |
| Rotas em 500 | 4 de 6 | **0** | 15/15 GET conferidas por HTTP após o bake |
| Contrato de forma (dict × schema) | 2 | **0** | trava nova, provada contra o estado real |
| Vigia do módulo | nenhum | **1 oráculo** | provado em vermelho 3× |
| Rotas fantasma no frontend | 9 | **0** | 7 repontadas, 4 removidas |
| Código do frontend invisível ao git | 73 arquivos | **0** | `.gitignore` corrigido, 73 versionados |

O oráculo (`backend/scripts/orq/test_oraculo_servicos.py`) vigia duas coisas que nenhuma
trava estática vê: os números da **tela** contra consultas independentes, e a **camada de
serviço rodando** contra o banco. Provado em vermelho contra três defeitos injetados e
revertidos: código anterior ao conserto, envelope de schema removido, e `LIMIT 200 → 3`.

## 2. As cinco barreiras — e todas reaparecem nos outros módulos

### 2.1 Código escrito contra uma API que nunca existiu

78 chamadas no backend, 9 no frontend. **Não é bug de lógica: é código que nunca rodou.** O
sintoma que apareceu (4 rotas em 500) era 5% da família.

Restam **61 no backend** (financial 19, operacional 17, ged 12, people_management 10) e
**84 alcançáveis no frontend**.

### 2.2 A doença atravessa a parede, e nenhuma ferramenta olhava os dois lados

A trava do repositório só lê Python. Os oráculos só olham telas do redesign. O cliente
gerado do OpenAPI espelha o backend por construção — então **dá impressão de cobertura**.
No vão entre eles moravam 666 chamadas do frontend para rotas que não existem.

Nasceu daí `checar_rotas_frontend.py`.

### 2.3 Resíduo de reorganização vira ruína silenciosa

`/api/v1/hr` **não existe mais** — a reorg 35→9 moveu tudo para `/api/v1/people-management`
(596 rotas). Sobraram clientes inteiros (`employeePortalService`, `timeTrackingService`,
`payrollIntegrationService`) chamando o prefixo velho. **Nenhuma página os usa** — são 582
chamadas fora de alcance de tela.

Isto não é dívida a consertar: é **código morto a remover**, e o mapa está na trava.

### 2.4 Ferramenta com verde incompleto é pior que ferramenta nenhuma

`checar_repositorio` disse `services: 0` com o dashboard executivo ainda em 500. Ela
verificava "o método existe" — mas *existe e devolve outra forma* quebra igual. Ganhou um
segundo olho.

**Regra que fica: ao escrever qualquer trava, pergunte o que ela ainda deixa passar.**

### 2.5 O git era cego em 73 arquivos de código

A regra `lib/` (do bloco de virtualenv Python, que esconde `backend/venv/lib` com 20.827
arquivos) engolia `frontend/src/lib` — 73 arquivos de código, entre eles `src/lib/pdf.ts` e
o `axios-instance`.

Sem histórico, sem revisão, sem backup no repositório. E **a regra da parede entre terminais
lê `git status`: ela era cega ali**. Dois terminais podiam se sobrescrever sem sinal nenhum.

Encontrado porque fui atrás de nove URLs erradas num arquivo que ninguém usa.

## 3. Meus erros nesta sessão — todos de método

| Erro | Como pegou | Regra que fica |
|---|---|---|
| `ServiceAIService(ServiceRepository(db))` — construtor recebe `db` | o `AttributeError` parecia defeito do sistema | **prove o arreio antes de acusar o código** |
| "206 achados são o gerador duplicando segmento" | testei: **0 de 206** passam a existir sem a duplicata | hipótese bonita morre pelo dado, não pela convicção |
| "185 de 205 arquivos são alcançáveis" | o proxy era *alguém importa*; andando dos `app/**`, os campeões **não são usados por página nenhuma** | alcance se mede da TELA para trás |
| 3 de 14 achados devolviam **200** no curl | eu normalizava a barra final só de um lado | **falso positivo mata a confiança mais rápido que achado nenhum** |
| 7 erros de tipo nos meus arquivos | rodei a mesma checagem num arquivo intocado: **48 erros** | de novo o arreio; no `tsconfig` real, zero |

Cinco erros, quatro pegos por medição e um por comparação com linha de base. **Nenhum
chegou a virar afirmação para o Jordan** — e é isso que o Arsenal está comprando.

## 4. Mapa macro — por onde seguir

| Frontend → 404 (alcançável) | | Backend → método inexistente | |
|---|---|---|---|
| people-management | 36 | financial | 19 |
| portal | 9 | operacional | 17 |
| ged | 8 | ged | 12 |
| juridico | 8 | people_management | 10 |
| campo | 5 | ai · hr · integrations | 1 cada |
| financial | 4 | | |

**Ordem sugerida:** `ged` e `people-management` aparecem nos dois lados — são os que dão
mais retorno por passada. `financial` tem a maior dívida de backend, **mas o T1 trabalha
lá: a parede vale.**

## 5. O que o MVP diz sobre fechar um módulo

1. **"Fechado" não é uma coisa só.** Serviços tem a dimensão de contrato fechada e a de
   produto aberta (0 dado, 38 rotas de escrita nunca exercitadas, tela mostrando outra
   tabela). Relatar as duas separadamente é obrigação.
2. **O sintoma é a ponta.** 4 rotas em 500 → 78 chamadas → 139 no sistema → 666 no frontend
   → 73 arquivos fora do git. Cada camada só apareceu porque a anterior foi medida até o fim.
3. **Toda trava precisa de self-check e de uma prova contra o defeito real.** Duas das
   minhas deram número errado antes de merecer confiança.
4. **Módulo pequeno não significa trabalho pequeno** — significa superfície pequena para
   errar enquanto se aprende o roteiro.

## 6. Não coberto

- Navegador real (Playwright não usado nesta sessão).
- As 38 rotas de escrita de serviços — tabelas vazias, nada a exercitar sem dado.
- Decisão de produto: **`ordens_servico` (tela) × `service_orders` (módulo)** são dois
  mundos. Qual é a verdade é decisão do Jordan, não minha.
- Os 582 chamados frontend fora de alcance: mapeados, não removidos.
