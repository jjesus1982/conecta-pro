# MISSÃO (para o CIC conectado ao Sólides/Tangerino): destravar o cadastro completo dos funcionários

Você é um agente com acesso ao portal **Sólides / Tangerino** (empregador) da empresa
**JORDAN SANTOS DE JESUS LTDA — CNPJ 35.710.481/0001-03**. Outro sistema (o ERP "Conecta PRO")
precisa **enriquecer o cadastro dos 46 funcionários ativos** com os dados completos que hoje só
existem no Sólides. Sua missão é trazer **uma de duas coisas** (a primeira é a preferida).

---

## CONTEXTO TÉCNICO (o que já sabemos)
- A API do Tangerino (`https://employer.tangerino.com.br`) tem um schema **`EmployeeDTO` com 127
  campos** que contém TODO o cadastro: RG, CTPS, filiação, endereço, estado civil, título de eleitor,
  reservista, celular, escolaridade, etc.
- Esse cadastro completo só é retornado pelo endpoint **`GET /occupational-health/employees`**.
- Esse endpoint **NÃO** aceita o token de API normal (Basic). Ele exige **DOIS** parâmetros que
  ainda não temos:
  1. Um header HTTP **`integration-token`** (credencial de integração separada).
  2. Um query param **`mainCompanyExternalCode`** (o "código externo" da empresa na integração).
- Empresa: `company.id = 2114953` no Tangerino · CNPJ `35.710.481/0001-03`.

---

## OBJETIVO A (PREFERIDO) — obter o `integration-token` + `mainCompanyExternalCode`

### Passo 1 — Achar/gerar o token de integração
No portal Sólides/Tangerino (logado como admin), procure por:
- **Configurações → Integrações** (ou **Integrações / API / Webhooks**), OU
- **Saúde Ocupacional / SST → Integração** (o token costuma ficar na integração de saúde ocupacional/SST,
  porque o endpoint é `/occupational-health/...`), OU
- **Configurações da Empresa → Integrações / Tokens de API**.

Gere (ou copie, se já existir) o **token de integração** (pode aparecer como "integration token",
"token de integração", "chave de integração SST", "API key de saúde ocupacional").

### Passo 2 — Achar o `mainCompanyExternalCode`
É o **código externo da empresa** configurado na integração (NÃO é o CNPJ nem o id interno 2114953).
Procure na mesma tela de integração por um campo tipo "código externo", "external code",
"código da empresa na integração", "employer external code". Anote o valor exato.

### Passo 3 — VALIDAR antes de retornar (importante)
Com o token e o código, teste o endpoint (substitua `<TOKEN>` e `<CODE>`):
```bash
curl -s "https://employer.tangerino.com.br/occupational-health/employees?page=0&size=2&mainCompanyExternalCode=<CODE>" \
  -H "integration-token: <TOKEN>" -H "Accept: application/json" | head -c 800
```
- **Sucesso:** HTTP 200 + um JSON com `content[...]` trazendo funcionários com campos como
  `motherName`, `ctps`, `employeeAddress`, `maritalStatus`. Se vier isso → **deu certo**.
- **HTTP 401** = token errado/inválido. **HTTP 400 "Missing request header 'integration-token'"** = o
  header não foi enviado. **HTTP 400 com outra msg** = falta/erro no `mainCompanyExternalCode`.

### O QUE RETORNAR (Objetivo A)
```
INTEGRATION_TOKEN: <o token>
MAIN_COMPANY_EXTERNAL_CODE: <o código>
TESTE: <cole as ~800 primeiras chars da resposta do curl acima>
```

---

## OBJETIVO B (ALTERNATIVO, se não achar o token) — exportar o cadastro completo

Se não houver/achar o token de integração, **exporte a lista de colaboradores com o cadastro completo**
direto do portal Sólides (Gestão de Pessoas / DP):
- Vá em **Colaboradores / Funcionários** → procure por **Exportar / Relatório / Download** (CSV ou Excel).
- Garanta que o export inclua, além do nome/CPF, o **máximo** destes campos:

| Campo desejado |
|---|
| CPF (obrigatório — é a chave), Nome |
| RG, Órgão Emissor do RG, UF do RG |
| CTPS Número, CTPS Série, CTPS UF, CTPS Data de Emissão |
| Estado Civil, Nacionalidade, Naturalidade |
| Nome da Mãe, Nome do Pai |
| CEP, Logradouro, Número, Complemento, Bairro, Cidade, UF |
| Título de Eleitor, Zona, Seção |
| Certificado de Reservista |
| Email, Telefone, Celular |
| Escolaridade, Raça/Cor, PIS, Data de Nascimento, Data de Admissão |

### O QUE RETORNAR (Objetivo B)
- O arquivo **CSV/Excel** exportado (ou o conteúdo dele).
- Se for possível escolher o separador, prefira **`;`** (padrão Excel BR). Mantenha o **CPF** como texto
  (não perca zeros à esquerda).

---

## RESUMO DO QUE PRECISO DE VOLTA
1. **(Preferido)** `INTEGRATION_TOKEN` + `MAIN_COMPANY_EXTERNAL_CODE` + o teste do curl dando 200. **OU**
2. **(Alternativo)** o **CSV/Excel** do cadastro completo dos colaboradores (com CPF + os campos da tabela).

Qualquer um dos dois destrava o preenchimento automático do cadastro dos 46 funcionários no Conecta PRO.
Não precisa de mais nada além disso. Se algo na tela não bater com os nomes acima, descreva o que você
vê (prints/descrição) que eu adapto.
