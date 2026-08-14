# GED por documentos — compartilhamento e aprovação (quarentena, 14/08/2026)

Estes quatro arquivos chamavam **11 endpoints que o backend não tem**. Provado pela rota
real, não por grep:

```
GET  /api/v1/ged/documents/{id}/shares      → HTTP 404
GET  /api/v1/ged/documents/{id}/approvals   → HTTP 404
```

`ged_document_shares` tem **0 linhas**; tabela de aprovação de documento não existe.

**E a cadeia inteira era morta:** ninguém renderiza o `DocumentShareDialog` e ninguém importa
o `approvalService` — só os barris `components/ged/index.ts` e `services/ged/index.ts` os
reexportavam. Zero consumidores.

**Por que sai em vez de ser implementado:** a decisão do módulo é **GED por KITS**, não por
documento avulso. Um cliente de documentos que promete compartilhamento e aprovação diz ao
usuário o contrário do que o produto faz.

Quarentena e não deleção: se a decisão mudar, o código está aqui inteiro, com o histórico
do git preservado (`git mv`).
