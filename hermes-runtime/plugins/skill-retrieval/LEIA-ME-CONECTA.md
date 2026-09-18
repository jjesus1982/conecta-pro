# skill-retrieval nesta casa

Plugin de terceiro (MIT, `moonlight-lupin/agent-skills`), auditado em 18/09/2026 antes de
instalar: sem rede, sem `subprocess`, sem `exec`, sem escrita em disco; um hook só
(`pre_llm_call`) que falha devolvendo `None`. Hashes do que foi baixado em `ORIGEM.sha256`.

## Duas variantes, e a versão do Hermes decide qual vale

| arquivo | serve a | por quê |
|---|---|---|
| `__init__.py` | **Hermes >= 0.21** (o nosso hoje) | o original do autor, sem fork a manter |
| `__init__.py.para-hermes-0.19-0.20` | Hermes 0.19.x e 0.20.x | leva a ADAPTAÇÃO DA CASA |

**Da 0.21 em diante**, a decomposição de setembro/2026 fez todo chamador resolver
`build_skills_system_prompt` por `agent.prompt_builder`, e o patch do autor alcança. Mais que
isso: usar a variante adaptada ali **desliga o plugin** — o Hermes recusa carregar plugin que
importe caminhos removidos em 14/09 (`hermes plugins compat` mostra a linha).

**Até a 0.20.x**, o chamador resolve por `run_agent`, que importou a função para o próprio
namespace, e o patch do autor NÃO alcança. Sem a adaptação o plugin liga só a metade que
ADICIONA tokens. Medido na 0.19: 26.793 com o original contra 26.569 sem plugin nenhum — pior
que não instalar.

## Se você fizer rollback do Hermes para < 0.21

Troque o arquivo:

    cp __init__.py.para-hermes-0.19-0.20 __init__.py
    docker cp . conecta-pro-hermes:/data/plugins/skill-retrieval/
    docker restart conecta-pro-hermes

O caçador `checar_hermes_skill_retrieval.py` acusa se você esquecer — ele conhece a versão e
cobra a variante certa nos dois sentidos.
