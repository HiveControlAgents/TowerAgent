#!/usr/bin/env python3
"""TowerAgent: um prédio 3D com um andar para cada agente do Claude Code.

Uso:
  python3 tower.py serve --nome "Torre Aurora"     # abre no navegador, ao vivo
  python3 tower.py build --nome "Torre Aurora" -o torre.html   # arquivo único, sem servidor
  python3 tower.py listar                           # mostra o que seria exibido

Privacidade: só lê o cabeçalho (frontmatter) dos agentes: nome, descrição curta,
cor e campos tower_*. O corpo do agente (o prompt) nunca é lido para a página,
nada sai da sua máquina e o servidor só escuta em 127.0.0.1.
"""
from __future__ import annotations

import argparse
import hashlib
import http.server
import json
import os
import re
import socketserver
import sys
import threading
import time
import webbrowser
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
WEB = RAIZ / "web" / "index.html"
CASA = Path(os.environ.get("TOWERAGENT_HOME", Path.home() / ".toweragent"))
CONFIG = CASA / "config.json"
ESTADO = CASA / "estado.json"

PALETA = ["#2fb9a3", "#d45ac8", "#e0577a", "#ef7d3c", "#d7a531", "#5aa0e6", "#8a5cf0", "#3fb0c9", "#e8453c", "#4fae5b"]
CORES_CLAUDE = {"red": "#e8453c", "blue": "#5aa0e6", "green": "#4fae5b", "yellow": "#d7a531", "purple": "#8a5cf0",
                "orange": "#ef7d3c", "pink": "#e0577a", "cyan": "#3fb0c9"}
LIMITE_DESCRICAO = 160
# padrões de chaves conhecidas: se aparecerem numa descrição, viram [oculto]
SEGREDO = re.compile(
    r"(sk-[A-Za-z0-9_\-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|github_pat_[A-Za-z0-9_]{20,}|xox[abpr]-[A-Za-z0-9\-]{10,}"
    r"|AKIA[0-9A-Z]{16}|AIza[0-9A-Za-z_\-]{30,}|eyJ[A-Za-z0-9_\-]{20,}\.[A-Za-z0-9_\-]{10,}"
    r"|(?:api[_-]?key|token|secret|senha|password)\s*[:=]\s*\S+)", re.I)


# ---------- leitura dos agentes ----------
def frontmatter(caminho: Path) -> dict:
    """Lê só o bloco --- ... --- do topo. Para de ler no segundo ---."""
    dados, dentro = {}, False
    try:
        with caminho.open(encoding="utf-8", errors="replace") as f:
            for n, linha in enumerate(f):
                s = linha.rstrip("\n")
                if n == 0:
                    if s.strip() != "---":
                        return {}
                    dentro = True
                    continue
                if s.strip() == "---":
                    break
                if n > 80:
                    break
                m = re.match(r"^([A-Za-z_][\w\-]*)\s*:\s*(.*)$", s)
                if m and dentro:
                    v = m.group(2).strip()
                    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
                        v = v[1:-1]
                    dados[m.group(1).lower()] = v
    except OSError:
        return {}
    return dados


def limpar(texto: str, limite: int = LIMITE_DESCRICAO) -> str:
    texto = SEGREDO.sub("[oculto]", str(texto or ""))
    texto = re.sub(r"<[^>]*>", "", texto).replace("\\n", " ")
    texto = re.sub(r"\s+", " ", texto).strip()
    return texto if len(texto) <= limite else texto[: limite - 1].rstrip() + "…"


def slug(nome: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", nome.lower()).strip("-")
    return s or "agente"


def cor_de(nome: str, pedida: str) -> str:
    pedida = (pedida or "").strip().lower()
    if pedida in CORES_CLAUDE:
        return CORES_CLAUDE[pedida]
    if re.fullmatch(r"#[0-9a-f]{6}", pedida):
        return pedida
    return PALETA[int(hashlib.sha1(nome.encode()).hexdigest(), 16) % len(PALETA)]


def pastas_de_agentes(projeto: Path | None, com_plugins: bool) -> list[tuple[str, Path]]:
    claude = Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude"))
    pastas = [("usuário", claude / "agents")]
    if projeto:
        pastas.append(("projeto", projeto / ".claude" / "agents"))
    if com_plugins:
        for p in sorted((claude / "plugins" / "cache").glob("**/agents")):  # só plugins instalados
            if p.is_dir() and "toweragent" not in str(p).lower():
                pastas.append(("plugin", p))
    return pastas


def descobrir(projeto: Path | None = None, com_plugins: bool = True) -> list[dict]:
    vistos, agentes = set(), []
    for origem, pasta in pastas_de_agentes(projeto, com_plugins):
        if not pasta.is_dir():
            continue
        for arq in sorted(pasta.glob("*.md")):
            fm = frontmatter(arq)
            nome = limpar(fm.get("name") or arq.stem, 40)
            ident = slug(nome)
            if not nome or ident in vistos:
                continue
            vistos.add(ident)
            agentes.append({
                "id": ident,
                "nome": nome,
                "papel": limpar(fm.get("description", "")),
                "cor": cor_de(nome, fm.get("color", "")),
                "origem": origem,
                "chefe": slug(fm["tower_chefe"]) if fm.get("tower_chefe") else None,
                "andar_nome": limpar(fm.get("tower_andar", ""), 30) or None,
                "cargo": limpar(fm.get("tower_cargo", ""), 30) or None,
            })
    ids = {a["id"] for a in agentes}
    for a in agentes:  # chefe que não existe vira agente de andar próprio
        if a["chefe"] not in ids or a["chefe"] == a["id"]:
            a["chefe"] = None
    return agentes


# ---------- estado ao vivo (escrito pelos hooks) ----------
def ler_json(caminho: Path, padrao):
    try:
        return json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return padrao


def config() -> dict:
    return ler_json(CONFIG, {})


def salvar_config(**novos) -> dict:
    c = config()
    c.update({k: v for k, v in novos.items() if v is not None})
    CASA.mkdir(parents=True, exist_ok=True)
    CONFIG.write_text(json.dumps(c, ensure_ascii=False, indent=2), encoding="utf-8")
    return c


def estado(projeto: Path | None = None) -> dict:
    c = config()
    vivo = ler_json(ESTADO, {}).get("agentes", {})
    agora = time.time()
    agentes = descobrir(projeto, c.get("plugins", True))
    for a in agentes:
        v = vivo.get(a["id"], {})
        st = v.get("status", "livre")
        # trabalho sem fim registrado há mais de 30 min: considera encerrado
        if st == "trabalhando" and agora - v.get("t", 0) > 1800:
            st = "livre"
        a["status"] = st
        a["tarefa"] = limpar(v.get("tarefa", ""), 80) if st == "trabalhando" else ""
        a["ultima"] = v.get("quando")
    return {
        "nome": c.get("nome") or "TowerAgent",
        "dono": limpar(c.get("dono", "") or "Você", 30),
        "agentes": agentes,
        "atualizado": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }


# ---------- página ----------
def pagina(dados: dict, ao_vivo: bool = False) -> str:
    """Embute os dados na página. ao_vivo=True: a página também consulta /api/estado a cada 4 s."""
    html = WEB.read_text(encoding="utf-8")
    bloco = json.dumps(dados, ensure_ascii=False).replace("</", "<\\/").replace("\u2028", "\\u2028").replace("\u2029", "\\u2029")
    html = html.replace("/*TOWER_DADOS*/null", bloco, 1)
    if ao_vivo:
        html = html.replace("/*TOWER_AO_VIVO*/false", "true", 1)
    return html


class Manipulador(http.server.BaseHTTPRequestHandler):
    projeto: Path | None = None

    def log_message(self, *args):
        pass

    def _enviar(self, corpo: bytes, tipo: str, codigo: int = 200):
        self.send_response(codigo)
        self.send_header("Content-Type", tipo)
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(corpo)))
        self.end_headers()
        self.wfile.write(corpo)

    def do_GET(self):
        rota = self.path.split("?")[0]
        if rota in ("/", "/index.html"):
            self._enviar(pagina(estado(self.projeto), ao_vivo=True).encode("utf-8"), "text/html; charset=utf-8")
        elif rota == "/api/estado":
            self._enviar(json.dumps(estado(self.projeto), ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")
        else:
            self._enviar(b"nao encontrado", "text/plain", 404)


def servir(porta: int, abrir: bool, projeto: Path | None):
    Manipulador.projeto = projeto
    socketserver.TCPServer.allow_reuse_address = True
    try:
        srv = socketserver.ThreadingTCPServer(("127.0.0.1", porta), Manipulador)
    except OSError:
        url = f"http://127.0.0.1:{porta}/"
        print(f"A porta {porta} já está em uso; o prédio provavelmente já está aberto em {url}")
        if abrir:
            webbrowser.open(url)
        return
    url = f"http://127.0.0.1:{porta}/"
    print(f"{estado(projeto)['nome']} aberto em {url} (Ctrl+C para fechar)")
    if abrir:
        threading.Timer(.6, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="tower", description="Prédio 3D dos seus agentes do Claude Code")
    sub = ap.add_subparsers(dest="cmd")
    for nome in ("serve", "build", "listar", "nomear"):
        p = sub.add_parser(nome)
        p.add_argument("--nome", help="nome do prédio (fica salvo)")
        p.add_argument("--dono", help="quem mora na cobertura (padrão: Você)")
        p.add_argument("--projeto", default=os.getcwd(), help="pasta do projeto para ler .claude/agents")
        if nome == "serve":
            p.add_argument("--porta", type=int, default=int(os.environ.get("TOWERAGENT_PORT", 7979)))
            p.add_argument("--sem-abrir", action="store_true")
        if nome == "build":
            p.add_argument("-o", "--saida", default="torre.html")
    a = ap.parse_args(argv)
    if not a.cmd:
        ap.print_help()
        return 0
    nome = " ".join(a.nome.split())[:40] if a.nome else None
    salvar_config(nome=nome, dono=a.dono)
    projeto = Path(a.projeto).resolve() if a.projeto else None
    if a.cmd == "serve":
        servir(a.porta, not a.sem_abrir, projeto)
    elif a.cmd == "build":
        Path(a.saida).write_text(pagina(estado(projeto)), encoding="utf-8")
        print(f"Prédio salvo em {Path(a.saida).resolve()}")
    elif a.cmd == "listar":
        d = estado(projeto)
        print(f"{d['nome']}: {len(d['agentes'])} agente(s)")
        for ag in d["agentes"]:
            chefe = f" (equipe de {ag['chefe']})" if ag["chefe"] else ""
            print(f"  - {ag['nome']} [{ag['origem']}] {ag['status']}{chefe}")
    elif a.cmd == "nomear":
        print(f"Nome do prédio: {config().get('nome', 'TowerAgent')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
