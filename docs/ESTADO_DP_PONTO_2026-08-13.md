# Estado do DP / Rollout do Ponto — 13/08/2026

Documento de passagem. Tudo aqui foi **medido no banco ou verificado em produção**, não
estimado. O que não foi verificado está marcado como tal.

---

## 1. O que está NO AR e verificado

Todas as mudanças de backend abaixo foram bakeadas na imagem e conferidas **depois** do
recreate, com o container `healthy` — não só copiadas com `docker cp`.

| Mudança | Onde | Efeito medido |
|---|---|---|
| Lembrete de ponto por WhatsApp | `operacional/lembrete_ponto.py` + beat 60s | Roda, **não envia** (dry-run) |
| Coorte única do ponto | `ponto/coorte_ponto.py` | 52 → 49 pessoas |
| Primeiro acesso não repete | `primeiro_acesso_controller.py` | Corta o recadastro diário |
| Ativação não ressuscita conta | `primeiro_acesso_controller.py` | Duplicata deixou de voltar |
| Validação de telefone | `lembrete_ponto.py` | Recusa número inválido |
| Contagem honesta do painel | `painel_ponto_controller.py` | Pendentes 7 → 4 |
| Ausentes fora da escalada | `notification_triggers.py` | −45 turnos de alerta falso |
| Trava de CPF duplicado | índice `ux_employees_cpf_ativo` | Testada: banco recusa |
| Trava de acesso do `/redesign` | `RedesignGuard.tsx`, `types/modules.ts` | Publicada, bundle conferido |

### Dados corrigidos (não é código)

- **68 contas** da coorte restritas a `self:portal`, sem permissão de gestão.
- **21 contas corporativas** desativadas; **15 contas órfãs** excluídas (backup em
  `/root/conecta-backups/contas_soltas_excluidas_2026-08-12.csv`).
- **4 contas criadas** para quem não tinha login: Alexandre, Cintia, Kelly Patricia, Nailson.
- **3 alocações** lançadas: Alexandre → Mirante das Flores; Kelly Patricia e Nailson → Ideal
  Flores da Cidade.
- **Keyson**: pedido de demissão registrado, último dia 14/08 (datas de verbas **pendentes do DP**).
- **Elen Xavier**: conta renomeada para o e-mail pessoal; login provado.

---

## 2. O que está PRONTO mas DESLIGADO

**Lembrete por WhatsApp.** `PONTO_LEMBRETE_ENABLED` não está definida, então cai no default
`false`: a task roda a cada 60s, calcula, loga o que enviaria e **não envia nada**.
`ponto_lembrete_log` está em 0.

Medição real do dry-run em 12/08: 50 mensagens teriam saído para 19 pessoas numa manhã; 6 pessoas
saíram da fila sozinhas ao bater o ponto. O teto de 3 por turno funcionou.

**Antes de ligar:** o canal é Baileys no número da empresa, o mesmo do comercial. Corrigir os 5
telefones abaixo primeiro — falha repetida de envio é o gatilho clássico de banimento.

---

## 3. Pendências — o que falta, e de quem depende

### Depende do RH (dado, não código)

1. **5 telefones.** Inválidos: Anilson `(99) 1361-770`, Euler `929848631485`, Jeovane
   `982064669`. Sem número: Graciene Pereira de Castro e Paulo da Silva Lamego.
2. **Verbas do Keyson** no processo de desligamento (criado incompleto de propósito).
3. **Férias do Eidy** e qualquer outro afastamento não lançado — a coorte exclui por data
   automaticamente assim que o registro existir.

### Depende de decisão de negócio

4. **Folha duplicada.** 363 pares de holerite no mesmo funcionário-mês, **353 com líquido
   diferente**, maior divergência R$ 3.628,08. Qual fonte manda, e a partir de qual competência?
   Enquanto não houver regra, o portal mostra um dos dois sem critério. Ver `RESPOSTAS_T2_DP.md`.
5. **eSocial.** 0 eventos transmitidos por nós; do S-2230 do SST, 1 consta transmitido e
   **nenhum tem recibo gravado**. Tratar como não entregue até aparecer protocolo.

### Não investigado (assumido como risco aberto)

6. **Gate humano entre folha calculada e pagamento efetuado.** Não rastreei o caminho até a
   efetivação bancária. É a próxima apuração que eu faria, antes de qualquer ajuste cosmético.
7. **5 telas vazias** do DP (das 21 totais; 8 do portal e 8 do GED têm explicação).
8. **Rotas `/hr` × `/human-resources`** — não é resíduo: o serviço do portal (people_management)
   importa o repositório de `modules/hr`. Não medi chamada real rota a rota.

---

## 4. Armadilhas medidas (custaram tempo hoje)

- **`docker cp` não é deploy.** Some no recreate. Só o bake é durável, e a verificação vale
  depois do recreate.
- **Build do frontend com 8 GB de heap morre e retorna exit 0**, sem gerar `BUILD_ID` nem
  `standalone`. Usar `--max-old-space-size=6144` e conferir os artefatos antes de publicar.
- **A árvore do frontend tem trabalho não commitado de outra sessão.** Compilar publica junto.
  Isolar com patch antes.
- **`JOIN` infla contagem**: "4 líderes" eram 3 pessoas com 6 contas. Contar pessoas, não linhas.
- **`isSelfServiceUser` não reconhece `role='agente'`** — só `funcionario` ou a permissão
  `self:portal`. Foi por isso que a Elen atravessou a trava das telas antigas.

---

## 5. Tabelas vivas × mortas (para não auditar a errada)

| Assunto | Viva | Vazia / morta |
|---|---|---|
| Ponto | `gp_clock_punches` (7.806) | `time_entries` (0) |
| Justificativa | `gp_justifications` (1) | `time_justifications` (0) |
| Hora extra | (no cálculo da folha) | `overtime_records` (0) |
| GED | `ged_kit_documents` (2.625), `onvio_documents` (901) | `ged_documents` (0) |
| eSocial | `esocial_espelho_janelas` (367) — dado **puxado** do governo | `eventos_esocial` (0) |
