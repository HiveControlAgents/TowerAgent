#!/usr/bin/env python3
"""Hook do Claude Code: acende o andar do agente enquanto ele trabalha.

Grava só em ~/.toweragent/estado.json: id do agente, status, hora e a descrição
curta da tarefa (no máximo 80 caracteres, sem o prompt). Nunca bloqueia o Claude:
qualquer erro é ignorado e o hook sai com código 0.
"""
import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tower import ESTADO, CASA, limpar, slug  # noqa: E402


def registrar(agente: str, status: str, tarefa: str = ""):
    CASA.mkdir(parents=True, exist_ok=True)
    try:
        dados = json.loads(ESTADO.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        dados = {}
    ag = dados.setdefault("agentes", {})
    antigo = ag.get(slug(agente), {})
    if not tarefa and status == antigo.get("status"):
        tarefa = antigo.get("tarefa", "")  # SubagentStart não traz a descrição; mantém a do PreToolUse
    ag[slug(agente)] = {"status": status, "tarefa": limpar(tarefa, 80), "t": time.time(),
                        "quando": time.strftime("%Y-%m-%dT%H:%M:%S")}
    tmp = ESTADO.with_suffix(".tmp")
    tmp.write_text(json.dumps(dados, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp, ESTADO)


def main():
    try:
        ev = json.load(sys.stdin)
    except ValueError:
        return
    nome_ev = ev.get("hook_event_name", "")
    entrada = ev.get("tool_input") or {}
    agente = entrada.get("subagent_type") or ev.get("agent_type")
    if not agente:
        return
    if nome_ev in ("PreToolUse", "SubagentStart"):
        registrar(agente, "trabalhando", entrada.get("description", ""))
    elif nome_ev == "PostToolUse" and entrada.get("run_in_background"):
        return  # agente em segundo plano: quem apaga a luz é o SubagentStop
    elif nome_ev in ("PostToolUse", "SubagentStop"):
        registrar(agente, "livre")
    elif nome_ev == "PostToolUseFailure":
        registrar(agente, "erro")


if __name__ == "__main__":
    try:
        main()
    except Exception:  # o prédio nunca pode atrapalhar o trabalho
        pass
    sys.exit(0)
