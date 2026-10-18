---
description: Abre o prédio 3D dos seus agentes. Use /tower Nome do Prédio para batizar.
argument-hint: "[nome do prédio]"
allowed-tools: Bash(python3:*), Bash(python:*)
---

Abra o prédio do TowerAgent para o usuário.

1. Se `$ARGUMENTS` não estiver vazio, ele é o nome do prédio. Rode em segundo plano (run_in_background):
   `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tower.py" serve --nome "$ARGUMENTS" --projeto "$PWD"`
   Se estiver vazio, rode o mesmo comando sem `--nome` (usa o nome salvo, ou "TowerAgent").
2. Depois rode `python3 "${CLAUDE_PLUGIN_ROOT}/scripts/tower.py" listar --projeto "$PWD"` e diga em uma ou duas frases:
   o nome do prédio, quantos andares (agentes) ele tem e o endereço http://127.0.0.1:7979/.
3. Se não houver nenhum agente, diga que o prédio abre só com recepção, andar do Claude e cobertura,
   e que cada agente criado em `~/.claude/agents/` ou `.claude/agents/` ganha um andar sozinho.

No Windows, se `python3` não existir, use `python` nos mesmos comandos.

Não leia o conteúdo dos arquivos de agentes; o script já lê só o cabeçalho.
