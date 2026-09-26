BEGIN;
CREATE TABLE IF NOT EXISTS employee_alocacoes_bkp_20260925 AS SELECT * FROM employee_alocacoes;

-- 1) posto_id vem de `allocations`, que é quem recebeu a planilha de setembro (fonte da verdade
--    declarada pelo dono). Onde as duas discordavam, a discordância era DESATUALIZAÇÃO: os 7
--    casos são exatamente as pessoas movidas hoje pela planilha.
UPDATE employee_alocacoes ea SET posto_id = a.post_id
FROM allocations a
WHERE a.employee_id = ea.employee_id AND coalesce(a.is_active,true)
  AND coalesce(ea.ativo,true) AND ea.posto_id IS NULL;

-- 2) quem não tem linha em allocations: se o cliente do condomínio tem UM posto ativo só,
--    não há ambiguidade. Com 2+, deixo nulo de propósito — chute aqui muda quem o sistema
--    acha que está no posto, e isso volta em folha.
UPDATE employee_alocacoes ea SET posto_id = p.id
FROM condominios cd JOIN posts p ON p.client_id = cd.client_id
     AND coalesce(p.is_active,true) AND NOT coalesce(p.is_homologacao,false)
WHERE cd.id = ea.condominio_id AND coalesce(ea.ativo,true) AND ea.posto_id IS NULL
  AND (SELECT count(*) FROM posts p2 WHERE p2.client_id=cd.client_id
       AND coalesce(p2.is_active,true) AND NOT coalesce(p2.is_homologacao,false)) = 1;

-- 3) o condomínio também estava velho nos 7 — alinho pelo posto que acabou de ser gravado,
--    senão as duas tabelas voltam a contar histórias diferentes na próxima leitura.
UPDATE employee_alocacoes ea SET condominio_id = cd.id
FROM posts p JOIN condominios cd ON cd.client_id = p.client_id
WHERE p.id = ea.posto_id AND coalesce(ea.ativo,true) AND ea.condominio_id <> cd.id;
COMMIT;
