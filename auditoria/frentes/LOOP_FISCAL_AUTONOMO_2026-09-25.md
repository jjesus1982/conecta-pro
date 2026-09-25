# Loop fiscal autônomo — 25/09/2026, noite

Autonomia do dono: *«prossiga em loop em tudo referente a fiscal e contabilidade, vou me
ausentar agora mas você tem total autonomia para tudo»*.

## O que mudou, em números medidos

| | Antes | Depois |
|---|---:|---:|
| NCMs com CEST do Convênio 142/18 | 0 | **1.317** |
| NCMs provados **fora** do Convênio (não são ST) | — | **7.822** |
| Clientes com endereço completo | 15 de 29 | **27 de 29** |
| Clientes com «Manaus/AM» no campo cidade | 5 | **0** |
| NFS-e de produção com XML assinado | 1 de 115 | **114 de 115** |
| Itens na conferência de prontidão | 3 | **2** (nenhum bloqueia) |

## Os oito defeitos consertados, e por que nenhum tinha teste que pegasse

1. **A senha do certificado vinha de outra fonte que o caminho.** `_buscar_xml_nfse` lia o
   `.pfx` da empresa e a senha de `CERT_A1_PASSWORD`. As **26 NFS-e da Patrimonial** nunca
   foram consultadas — o certificado dela abria com a senha da Eletrônica.
2. **«Não respondeu» contado como «não tem».** A função devolvia `None` para os dois casos, e
   o relatório somava. Dizia «o ADN não tem 43 notas» quando o ADN nunca fora perguntado.
3. **`http_502` classificado como «o fisco não tem».** O ADN devolve 5xx intermitente; a nº
   120 voltou vazia num lote e com 7.601 caracteres quando perguntada de novo.
4. **`ORDER BY numero DESC` lexicográfico** («99» antes de «121») — me fez inventar um padrão
   temporal que não existia.
5. **O preview da NF-e não mostrava o emitente.** Quem abria «Conferir antes de transmitir»
   não via uma linha da própria empresa — no mesmo dia em que o endereço dela estava errado.
6. **Marketing dentro do campo fiscal.** Toda nota sem dados adicionais saía com «NF-e emitida
   pelo Conecta PRO ERP.» no `infCpl`, que vai assinado ao fisco — contrariando a decisão do
   dono, que pediu a identificação **no pé da folha**, fora do quadro fiscal.
7. **5 clientes com a UF colada na cidade** («Manaus/AM») — sairia `<xMun>Manaus/AM</xMun>`.
8. **O município do tomador suposto como «Manaus»** quando o cadastro está vazio — e município
   do tomador decide **onde o ISS é devido**.

> Nenhum destes oito aparece num teste de unidade. Cada um só surgiu **fazendo a coisa real** e
> **lendo a saída**, não o código.

## Os achados que são decisão do dono

**6 produtos entraram com ICMS retido por ST e o NCM deles não está no Convênio** — não são ST
em lugar nenhum. Se o fornecedor reteve ICMS indevido, a casa pagou embutido no preço: há
hipótese de **restituição**. E revendê-los como CST 60 seria não destacar ICMS devido.

**Dos 14 CESTs que fornecedores declararam nas notas, 3 estão errados** — um controle remoto de
portão como «peça de veículo automotor». Copiar o CEST do fornecedor propaga o erro dele com o
nosso CNPJ embaixo.

**1.376 NCMs ambíguos** (2+ CESTs para o mesmo NCM); **32** dos 100 produtos caem aí. Decidir
exige ler a descrição contra a do Convênio — é do contador.

## O que eu quase reportei errado, três vezes

- **30 produtos em contradição** → eram **6**. A primeira contagem somava «fora do Convênio»
  com «ambíguo que eu não gravei». Ausência de gravação não é ausência de CEST.
- **«O ADN não tem 43 notas»** → tinha **todas**. Era o certificado e o 502.
- **«Faltava o protocolo na NF-e»** → não faltava. O bloco vem com prefixo de namespace e o
  meu filtro procurava sem.

> Nos três casos a lente devolveu um resultado **plausível** em vez de erro. É isso que faz o
> defeito sobreviver: «0 linhas», «sem protocolo», «sem XML» são respostas que se aceita sem
> desconfiar. Exceção teria sido vista em 5 segundos.

## Ferramentas que ficaram, em `backend/scripts/fiscal/`

| Script | O que faz |
|---|---|
| `importar_cest_convenio142.py` | baixa e importa a tabela oficial do CONFAZ |
| `conferir_cest_produtos.py` | confere os produtos contra ela; marca o suspeito sem apagar |
| `preencher_endereco_cliente_receita.py` | endereço de cliente vindo do cadastro da Receita |
| `backfill_xml_nfse.py` | busca o XML assinado no portal nacional — pausado, retomável, honesto |
| `comparar_preview_vs_real.py` | o preview diz o mesmo que o XML autorizado? |

Todos com conferência antes de `--aplicar`, e todos gravando **por item** — o lote que
sobrevive ao deploy de outra sessão é o que comita incrementalmente.
