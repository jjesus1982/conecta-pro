BEGIN;
-- Coordenada do Condomínio Green Hills derivada das BATIDAS REAIS — 25/09/2026.
--
-- POR QUE: era o único posto real sem latitude/longitude, e por isso 14 batidas COM GPS ficavam
-- com `dentro_geofence` NULO: sem coordenada no posto, o raio de 150 m não tem contra o que
-- comparar. A pessoa batia no lugar certo e o sistema não conseguia afirmar isso.
--
-- ⚠️ A MÉDIA NÃO SERVIA. Ela dava espalhamento de 3.577 × 3.925 metros e eu quase concluí que
-- o GPS era inútil aqui. Olhando ponto a ponto: 12 das 14 batidas caem dentro de ~40 metros, e
-- as 2 restantes estão em -3.0890/-60.0294 — que é o Condomínio PRIME ARENA (-3.08837/-60.02851).
-- São batidas feitas em OUTRO posto por quem estava alocado no Green Hills. Dois pontos fora
-- arruinaram a média de doze que concordavam.
--
-- Derivo pela MEDIANA do agrupamento, que é imune a esses dois. Raio 150 m, igual aos outros 8.
UPDATE posts SET
  latitude  = (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY c.latitude)
               FROM gp_clock_punches c WHERE c.posto_id = posts.id::text
                 AND c.latitude BETWEEN -3.06 AND -3.05),
  longitude = (SELECT percentile_cont(0.5) WITHIN GROUP (ORDER BY c.longitude)
               FROM gp_clock_punches c WHERE c.posto_id = posts.id::text
                 AND c.longitude BETWEEN -60.00 AND -59.99),
  geofence_raio_metros = coalesce(geofence_raio_metros, 150),
  updated_at = now()
WHERE name ILIKE '%GREEN HILLS%' AND (latitude IS NULL OR longitude IS NULL);
COMMIT;
