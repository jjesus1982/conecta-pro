---
name: veracity-sweep
description: Use ao caçar/eliminar dado SIMULADO (mock/hardcoded/fantasma/placeholder) em qualquer módulo do Conecta PRO — dashboards, KPIs, listas, stats, relatórios. O oráculo é "valor exibido == fato no banco". Cobre o loop finder→fixer→verificador com papéis separados, classificação em 5 baldes, prova por curl vs query, e o princípio "aguardando dado honesto, nunca fabricar". Invoque antes de dar um módulo como "pronto/real".
---

# Veracity Sweep — caçar dado simulado no Conecta PRO

## O oráculo (regra inegociável)
**Todo campo exibido tem que ter um FATO no banco por trás.** Nada é "verde/real" sem prova: `valor exibido == valor no banco` (mesmo funcionário/competência), provado com **curl vs query**.

## Classificação (5 baldes)
- **HARDCODED** — literal chumbado (`"total": 0`, listas de exemplo, `mock/fake/exemplo/demo`, `random`, `np.random`).
- **FANTASMA** — lê tabela vazia/errada enquanto o real está em outra populada (ex.: `health_epi_deliveries`=0 vs `gp_epi_deliveries`=220; `ged_documents`=0 vs `ged_kit_documents`=2046).
- **PLACEHOLDER** — `TODO`/`--`/`N/A`/`0.0` fixo/`uuid4()` falso/`Emp#<uuid>` em vez de nome/"Simular..." em comentário.
- **WRONG-MATH** — cálculo incorreto (divide incomensuráveis → cobertura 409%; janela de data quebrada `.replace(day=day-30)`; margem 100% por custo 0).
- **VAZIO-REAL** (✅ OK) — tabela existe e está vazia e isso é sinalizado honestamente ("aguardando dado"), não mascarado. E **REAL** (✅ OK) — vem de query em tabela populada.

## O loop (3 papéis NUNCA no mesmo ator — ver [[superpowers:requesting-code-review]])
1. **FINDER** (subagentes read-only, 1 por módulo, em paralelo — ver [[superpowers:dispatching-parallel-agents]]): inventaria cada campo exibido, cruza com a tabela que deveria alimentar, classifica. Ancora evidência em `arquivo:linha` + a query/curl. NÃO edita.
2. **FIXER** (outro ator): aplica a correção — hardcoded/fantasma/placeholder/wrong-math → lê o dado real; vazio-real → sinaliza "aguardando dado". Edita SÓ host, NÃO deploya.
3. **VERIFICADOR** (você, o orquestrador): deploya, faz `curl` vs `query` (o oráculo), e só então marca verde. Ver [[superpowers:verification-before-completion]] e [[deploy-bake]].

## Oráculo — como tirar o retrato do banco (o que é real)
```
docker exec -e PYTHONPATH=/app conecta-pro-backend python -c "
from core.database.session import SyncSessionLocal; from sqlalchemy import text
db=SyncSessionLocal()
for r in db.execute(text('SELECT relname,n_live_tup FROM pg_stat_user_tables WHERE n_live_tup>0 ORDER BY 2 DESC')).fetchall(): print(r[1], r[0])"
```
Tabelas populadas conhecidas (referência p/ detectar fantasma): employees, gp_clock_punches, ged_kit_documents, inter_transactions, contracts, proposals, clients, leads, commissions, executive_kpis, hr_payslips, gp_epi_deliveries, gp_asos, gp_risks, ged_certidoes.

## Curl (o oráculo do lado exibido)
Login (form-urlencoded, porta 8080): `curl -s -X POST http://localhost:8080/api/v1/auth/login -H "Content-Type: application/x-www-form-urlencoded" -d "username=admin@conectapro.com.br&password=admin123"` → `access_token` → Bearer. Endpoints `/operacional/ai/*` não exigem auth. Respostas costumam ser `{data:{...}}` ou envelope `{success,message,data}` — confira a chave certa antes de concluir "vazio".

## Regras de ouro
- Onde há fonte real → lê real. Onde NÃO há → "aguardando dado"/`0`/`None`/HTTP 501 honesto. **NUNCA fabricar.**
- **Dado legal (folha/fiscal/eSocial) não se inventa** — ver [[folha-cct]]. Simulador de folha só como fallback rotulado; priorizar dado oficial (Domínio/Portte).
- Documento fiscal (NFC-e/eSocial) **jamais** diz "autorizado/enviado" sem transmissão real → 501.
- Distinga **schema drift** (500 honesto, model≠banco) de **mock** (dado falso exibido). Drift = ver [[finding-schema-drift]], não é violação do oráculo.
- Registre o inventário e as correções em `auditoria/` com prova antes→depois.
