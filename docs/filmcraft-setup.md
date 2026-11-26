# FilmCraft — integração via MCP nativo

O fluxo novo usa o servidor MCP que acompanha o FilmCraft. Não criamos outro
servidor nem um editor substituto. Começamos em modo `bridge`, com o aplicativo
aberto; o modo `headless` é uma evolução do mesmo adaptador.

## Configuração

1. Copie `config/filmcraft.example.toml` para `config/filmcraft.toml`.
2. Preencha `command`/`args` com o executável do servidor MCP instalado.
3. Defina o segredo do bridge apenas no ambiente, por exemplo:

```powershell
$env:FILMCRAFT_BRIDGE_SECRET = "valor-local"
```

Nunca coloque o segredo no perfil, no SQLite, em prompts ou em logs. O cliente
redacta padrões óbvios de segredo em mensagens de erro.

## Diagnóstico

`ai-video-factory workflow filmcraft-doctor` verifica executável, modo e
capacidades declaradas sem iniciar uma exportação. A leitura é `read-only`:
a conexão negocia `initialize` e lista as ferramentas reais da versão instalada.

## Limites conhecidos

- A exportação pode concluir com mídia offline; o adaptador inspeciona arquivos,
  avisos e manifesto antes de aceitar a entrega.
- Codificador por hardware pode recair para software; a configuração efetiva é
  registrada no `editing_bundle.json`.
- Lotes MCP não são transacionais: após timeout de mutação, o cliente devolve
  `indeterminate` e exige inspeção antes de repetir qualquer inserção.
- Mapa de tempos: 254.016.000.000 ticks por segundo, confirmado nas
  capacidades negociadas. O plano usa aritmética racional e inteira.
