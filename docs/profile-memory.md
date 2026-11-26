# Perfis de canal e memória autônoma

O fluxo novo (`workflow`) é opt-in. Nenhum perfil é inferido de variável global:
todo comando exige `--profile`.

## Estrutura

```text
data/profiles/profiles.sqlite3          # fonte canônica de perfis e memória
data/profiles/<profile_id>/asset_memory.json  # rejeições editoriais do canal
data/profiles/technical-base/asset_memory.json # histórico técnico compartilhado
data/projects/<profile_id>/<production_id>/
  production.json
  profile_snapshot.json
  state/            # RunStore + resultados persistidos + refs
  artifacts/01_research ... 06_review
  memory/decisions.jsonl
  package/
```

SQLite é canônico. JSON e Markdown exportados são snapshots/consultas. Mídia e
áudio ficam em arquivos referenciados por hash; nunca no banco.

## Precedência

1. configuração explícita do episódio;
2. configuração explícita do canal (`explicit_fields`);
3. aprendizado ativo do canal aplicável ao estágio;
4. padrão herdado do perfil.

Regras de direitos e integridade não são desligadas por precedência editorial.
Cada produção fixa um `ProfileSnapshot`; aprendizados ativados durante ela só
valem para as próximas produções. O snapshot antigo continua resolvendo seus
próprios IDs de aprendizagem mesmo após substituição.

## Ciclo da memória

`observado -> proposto -> avaliado -> ativo`. Sem evidência verificável, a
proposta permanece hipótese. Uma falha relacionada pode suspender a regra e
restaurar a configuração anterior; mudança de versão de ferramenta suspende
regras incompatíveis declaradas. Nada disso depende de aprovação humana por
ajuste. Texto livre de fonte externa nunca altera configuração operacional.

`asset_memory.json` legado é importado como histórico técnico não promovido;
rejeição editorial de um canal nunca bloqueia outro canal.

## Backup e recuperação

```powershell
ai-video-factory profiles export meu-canal --output output/meu-canal-memory.json
```

A exportação JSON é inspeção lógica, não backup completo. Para backup físico
consistente, use a API de backup SQLite (método `ProfileStore.backup`) e copie
também `data/profiles/` e `data/projects/` com os arquivos referenciados.

Após queda entre editor e registro local, a retomada inspeciona o projeto
antes de repetir inserções e reconcilia observações perdidas usando o resultado
persistido em `state/<stage>_result.json`.
