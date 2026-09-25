-- Marcador de homologação em posts e clients — 25/09/2026
--
-- POR QUE: `employees` já tem `is_homologacao` e o KPI "CLT ativos" o usa (53 = 66 − 13 do
-- piloto). `posts` e `clients` NÃO tinham marcador nenhum, então "15 Postos ativos" somava os
-- 6 postos do Conecta Village/Conecta Base — que o Jordan confirmou serem condomínio de TESTE
-- do Conecta Plus — e "29 Clientes" incluía o cliente HOMOLOGACAO (CONECTA BASE).
-- A pessoa de teste era excluída; o posto e o cliente de teste, não. Assimetria.
--
-- ⚠️ Marcador na ORIGEM, não filtro por nome. `name ~* 'CONECTA'` quebraria no dia em que um
-- condomínio real se chamasse Conecta alguma coisa — a mesma armadilha de régua que custou
-- caro quatro vezes em 25/09.
--
-- Confirmado pelo Jordan: Condomínio Gelain é REAL (fica nos 9). As duas empresas do grupo
-- (ConectaMais Eletrônica e Conecta Mais Segurança) SÃO clientes — faturam entre si — e
-- continuam contando.
ALTER TABLE posts   ADD COLUMN IF NOT EXISTS is_homologacao boolean NOT NULL DEFAULT false;
ALTER TABLE clients ADD COLUMN IF NOT EXISTS is_homologacao boolean NOT NULL DEFAULT false;

UPDATE posts SET is_homologacao = true
WHERE name IN ('PORTARIA FIXA (24H) — CONECTA VILLAGE', 'RONDA — CONECTA VILLAGE',
               'SERVIÇOS GERAIS — CONECTA VILLAGE', 'MANUTENÇÃO (ARTÍFICE) — CONECTA VILLAGE',
               'JARDINAGEM — CONECTA VILLAGE', 'CONECTA BASE (ESCRITORIO)',
               '(REMOVIDO) PORTARIA TORRE B — CONECTA VILLAGE');

UPDATE clients SET is_homologacao = true WHERE upper(name) LIKE 'HOMOLOGACAO%';
