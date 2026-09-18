-- DDL da SPEC R6 (validação do Cowork, 18/09/2026) — ADITIVO e IDEMPOTENTE.
-- REGRAS da casa: só ADD COLUMN / CREATE INDEX. Nenhum DROP, nenhum ALTER estreitando.
-- ⚠️ Dívida de alembic declarada: nasce por SQL direto porque alembic/versions é zona
-- proibida para sessão autônoma. Vira migration pela mão do Jordan.
BEGIN;

-- ══════════════════ R6-1 · congelar o documento na emissão ══════════════════
-- Sem isto o contrato é RE-RENDERIZADO do dado vivo a cada chamada, e o que o cliente
-- assinou pode divergir do que se re-renderiza um mês depois — basta alguém trocar o
-- representante, um item ou o valor. É a mesma patologia que o manifesto do CTR-2026-00022
-- exibiu. `content`, `clauses` e `pdf_file_path` já existiam e nasciam nulos; faltava o
-- HASH, que é o que permite comparar o congelado com um render novo.
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS conteudo_hash varchar(64);
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS emitido_em    timestamp;
ALTER TABLE contracts ADD COLUMN IF NOT EXISTS emitido_por   varchar(160);

COMMIT;

-- ══════════════════ R6-8 · uma solicitação AGUARDANDO por posição ══════════════════
-- ⚠️ DIVERGÊNCIA DECLARADA do pedido, e a medição é o motivo. A SPEC pediu
-- "de-duplicar à mão e então criar UNIQUE (contrato, ordem)". Medi as 10 linhas com
-- `reference_code` de contrato e NÃO HÁ o que de-duplicar: o invariante que importa não é
-- "uma linha não-cancelada por ordem" — é "uma linha AGUARDANDO por ordem".
--
-- No CTR-2026-00022 a ordem 1 tem uma SIGNED (lote de 09/09, hash 65e08207…) e uma PENDING
-- (lote de 11/09). As duas são legítimas: a primeira é fato consumado com assinatura, IP e
-- hash; a segunda é o instrumento atual. Uma constraint sobre "não-cancelada" obrigaria a
-- cancelar a assinada — destruir prova para agradar o schema, como o próprio Cowork disse.
--
-- Índice PARCIAL sobre o que aguarda ação. Ele impede o segundo lote aberto (a causa real) e
-- preserva o histórico por construção. E exige `reference_code` não vazio: 3.168 linhas de
-- holerite/kit não têm ordem por contrato e não podem ser varridas por esta régua.
CREATE UNIQUE INDEX IF NOT EXISTS ux_sig_pendente_por_posicao
    ON sig_signature_requests (reference_code, signature_order)
 WHERE coalesce(reference_code, '') <> ''
   AND upper(coalesce(status, '')) IN ('PENDING', 'PENDENTE', 'SENT', 'ENVIADA',
                                       'AWAITING', 'VIEWED');
