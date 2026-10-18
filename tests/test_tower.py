import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ / "scripts"))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name)
        self.agents = self.home / ".claude" / "agents"
        self.agents.mkdir(parents=True)
        os.environ["CLAUDE_CONFIG_DIR"] = str(self.home / ".claude")
        os.environ["TOWERAGENT_HOME"] = str(self.home / ".toweragent")
        import importlib
        import tower
        self.tower = importlib.reload(tower)

    def tearDown(self):
        self.tmp.cleanup()

    def agente(self, arquivo, texto):
        (self.agents / arquivo).write_text(texto, encoding="utf-8")


class TestDescoberta(Base):
    def test_sem_agentes_abre_vazio(self):
        d = self.tower.estado(None)
        self.assertEqual(d["agentes"], [])
        self.assertEqual(d["nome"], "TowerAgent")

    def test_le_so_o_cabecalho(self):
        self.agente("a.md", "---\nname: tradutora\ndescription: Traduz textos\ncolor: purple\n---\nPROMPT_PRIVADO\n")
        d = self.tower.estado(None)
        self.assertEqual(d["agentes"][0]["nome"], "tradutora")
        self.assertEqual(d["agentes"][0]["cor"], "#8a5cf0")
        self.assertNotIn("PROMPT_PRIVADO", json.dumps(d))

    def test_esconde_chaves(self):
        self.agente("a.md", "---\nname: x\ndescription: usa sk-ABCDEFGHIJKLMNOPQRSTUVWX e ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123\n---\n")
        papel = self.tower.estado(None)["agentes"][0]["papel"]
        self.assertNotIn("sk-ABC", papel)
        self.assertNotIn("ghp_", papel)
        self.assertIn("[oculto]", papel)

    def test_equipe_e_chefe_inexistente(self):
        self.agente("a.md", "---\nname: chefe\n---\n")
        self.agente("b.md", "---\nname: ajudante\ntower_chefe: chefe\n---\n")
        self.agente("c.md", "---\nname: orfao\ntower_chefe: ninguem\n---\n")
        ags = {a["id"]: a for a in self.tower.estado(None)["agentes"]}
        self.assertEqual(ags["ajudante"]["chefe"], "chefe")
        self.assertIsNone(ags["orfao"]["chefe"])

    def test_sem_frontmatter_usa_nome_do_arquivo(self):
        self.agente("meu-agente.md", "só texto")
        self.assertEqual(self.tower.estado(None)["agentes"][0]["id"], "meu-agente")

    def test_nome_do_predio_fica_salvo(self):
        self.tower.salvar_config(nome="Torre Aurora")
        self.assertEqual(self.tower.estado(None)["nome"], "Torre Aurora")

    def test_pagina_embute_sem_fechar_script(self):
        self.agente("a.md", "---\nname: x\ndescription: </script><b>oi\n---\n")
        html = self.tower.pagina(self.tower.estado(None))
        self.assertNotIn("</script><b>", html)
        self.assertIn("const AO_VIVO = /*TOWER_AO_VIVO*/false", html)


class TestHook(Base):
    def rodar(self, evento):
        env = dict(os.environ)
        subprocess.run([sys.executable, str(RAIZ / "scripts" / "hook.py")], input=json.dumps(evento), text=True, env=env, check=True)
        return json.loads((self.home / ".toweragent" / "estado.json").read_text())["agentes"]

    def test_acende_e_apaga(self):
        self.agente("a.md", "---\nname: arquiteto\n---\n")
        ag = self.rodar({"hook_event_name": "PreToolUse", "tool_name": "Agent",
                         "tool_input": {"subagent_type": "arquiteto", "description": "Estrutura", "prompt": "PROMPT_PRIVADO"}})
        self.assertEqual(ag["arquiteto"]["status"], "trabalhando")
        self.assertNotIn("PROMPT_PRIVADO", json.dumps(ag))
        self.assertEqual(self.tower.estado(None)["agentes"][0]["status"], "trabalhando")
        ag = self.rodar({"hook_event_name": "PostToolUse", "tool_name": "Agent", "tool_input": {"subagent_type": "arquiteto"}})
        self.assertEqual(ag["arquiteto"]["status"], "livre")

    def test_hook_nunca_falha(self):
        r = subprocess.run([sys.executable, str(RAIZ / "scripts" / "hook.py")], input="lixo", text=True)
        self.assertEqual(r.returncode, 0)


if __name__ == "__main__":
    unittest.main()
