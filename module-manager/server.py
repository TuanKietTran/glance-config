#!/usr/bin/env python3
"""Glance YAML module manager and small tailnet-only web UI."""

import argparse
import html
import http.server
import json
import os
from pathlib import Path
import re
import subprocess
import tempfile
import threading
import time
from urllib.parse import urlparse

import yaml

ROOT = Path(os.environ.get("GLANCE_ROOT", "/opt/glance"))
BASE_PATH = ROOT / "glance.base.yml"
OUTPUT_PATH = ROOT / "glance.yml"
MODULES_DIR = ROOT / "modules"
STATE_PATH = ROOT / "modules-enabled.json"
LOCK = threading.RLock()
SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")


def module_files():
    return sorted(MODULES_DIR.glob("*.yml"))


def load_module(path):
    raw = path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw)
    if not isinstance(data, dict) or not isinstance(data.get("pages"), list):
        raise ValueError(f"{path.name}: expected a mapping with a pages list")
    slug = path.stem
    if not SLUG_RE.fullmatch(slug):
        raise ValueError(f"invalid module filename: {path.name}")
    marker = re.search(r"(?m)^pages:\s*$", raw)
    if not marker:
        raise ValueError(f"{path.name}: pages must be a top-level block")
    page_yaml = raw[marker.end():].lstrip("\r\n").rstrip() + "\n"
    return {
        "slug": slug,
        "name": str(data.get("name") or slug),
        "description": str(data.get("description") or ""),
        "default": bool(data.get("enabled_by_default", False)),
        "css": str(data.get("css_snippet") or "").rstrip(),
        "pages": data["pages"],
        "page_yaml": page_yaml,
    }


def modules():
    return [load_module(path) for path in module_files()]


def load_state(available):
    if STATE_PATH.exists():
        state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
        enabled = set(state.get("enabled", []))
    else:
        enabled = {m["slug"] for m in available if m["default"]}
    known = {m["slug"] for m in available}
    return enabled & known


def save_state(enabled):
    atomic_write(STATE_PATH, json.dumps({"enabled": sorted(enabled)}, indent=2) + "\n")


def atomic_write(path, content):
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def render(base, enabled, available):
    selected = [m for m in available if m["slug"] in enabled]
    result = base.rstrip() + "\n"

    css = []
    for module in selected:
        if module["css"]:
            css.append(f"/* module:{module['slug']} */\n{module['css']}\n/* /module:{module['slug']} */")
    if css:
        closing = re.search(r"(?m)^(\s*)</style>\s*$", result)
        if not closing:
            raise ValueError("base config has no </style> in document.head")
        indent = closing.group(1)
        injected = "\n\n".join("\n".join(indent + line if line else "" for line in block.splitlines()) for block in css)
        result = result[:closing.start()] + injected + "\n" + result[closing.start():]

    if selected:
        pages_key = re.search(r"(?m)^pages:\s*$", result)
        if not pages_key:
            raise ValueError("base config has no top-level pages block")
        additions = []
        for module in selected:
            additions.append(f"  # module:{module['slug']}\n{module['page_yaml'].rstrip()}\n  # /module:{module['slug']}")
        result = result.rstrip() + "\n\n" + "\n\n".join(additions) + "\n"

    parsed = yaml.safe_load(result)
    if not isinstance(parsed, dict) or not isinstance(parsed.get("pages"), list):
        raise ValueError("rendered config has no pages list")
    names = [page.get("name") for page in parsed["pages"] if isinstance(page, dict)]
    duplicates = sorted({name for name in names if name and names.count(name) > 1})
    if duplicates:
        raise ValueError("duplicate page name(s): " + ", ".join(duplicates))
    return result


def restart_glance(previous):
    completed = subprocess.run(["systemctl", "restart", "glance"], capture_output=True, text=True)
    time.sleep(0.5)
    active = subprocess.run(["systemctl", "is-active", "--quiet", "glance"]).returncode == 0
    if completed.returncode == 0 and active:
        return
    error = (completed.stderr or completed.stdout or "Glance failed to start").strip()
    if previous is not None:
        atomic_write(OUTPUT_PATH, previous)
        subprocess.run(["systemctl", "restart", "glance"], capture_output=True)
    raise RuntimeError(error)


def reconcile(restart=False):
    with LOCK:
        available = modules()
        enabled = load_state(available)
        base = BASE_PATH.read_text(encoding="utf-8")
        generated = render(base, enabled, available)
        previous = OUTPUT_PATH.read_text(encoding="utf-8") if OUTPUT_PATH.exists() else None
        atomic_write(OUTPUT_PATH, generated)
        save_state(enabled)
        if restart and generated != previous:
            restart_glance(previous)
        return available, enabled


PAGE = """<!doctype html>
<html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Glance configuration</title>
<script src="https://cdn.jsdelivr.net/npm/monaco-editor@0.52.0/min/vs/loader.js"></script>
<style>
:root{color-scheme:dark;--bg:#11131a;--panel:#1b1e27;--line:#343846;--primary:#bd93f9;--text:#f1f1f3;--muted:#a5a7b1}
*{box-sizing:border-box}html,body{height:100%;margin:0;background:var(--bg);color:var(--text);font:14px system-ui,sans-serif}
header{height:52px;padding:8px 14px;display:flex;align-items:center;gap:10px;border-bottom:1px solid var(--line)}
h1{font-size:16px;margin:0 16px 0 0}.tab,button{border:1px solid var(--line);border-radius:6px;background:var(--panel);color:var(--text);padding:7px 12px;cursor:pointer}.tab.active,button.primary{background:var(--primary);color:#17121f;border-color:var(--primary);font-weight:700}#status{margin-left:auto;color:var(--muted);font-size:12px}.view{display:none;height:calc(100% - 52px)}.view.active{display:block}#modules{padding:18px;overflow:auto}.card{max-width:760px;background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:15px;margin-bottom:12px;display:flex;gap:14px;align-items:center}.card h2{font-size:15px;margin:0 0 5px}.card p{color:var(--muted);margin:0}.toggle{margin-left:auto;min-width:84px}.toggle.on{background:#50c878;color:#08160c;border-color:#50c878;font-weight:700}#yaml{position:relative}#editor{height:100%}#save{position:absolute;z-index:5;right:20px;top:12px}
</style></head><body>
<header><h1>Glance Config</h1><button class="tab active" data-view="modules">Modules</button><button class="tab" data-view="yaml">Base YAML</button><span id="status"></span></header>
<section id="modules" class="view active"><div id="module-list"></div></section>
<section id="yaml" class="view"><button id="save" class="primary">Save &amp; apply</button><div id="editor"></div></section>
<script>
const base='./';let editor;
function status(text,bad=false){const e=document.getElementById('status');e.textContent=text;e.style.color=bad?'#ff7070':''}
async function request(path,options){const r=await fetch(base+path,options);const text=await r.text();if(!r.ok)throw new Error(text);return text?JSON.parse(text):null}
async function loadModules(){const data=await request('api/modules');const list=document.getElementById('module-list');list.innerHTML='';data.modules.forEach(m=>{const card=document.createElement('div');card.className='card';card.innerHTML='<div><h2>'+m.name+'</h2><p>'+m.description+'</p></div>';const b=document.createElement('button');b.className='toggle '+(m.enabled?'on':'');b.textContent=m.enabled?'Enabled':'Disabled';b.onclick=async()=>{b.disabled=true;status('Applying…');try{await request('api/modules/'+m.slug,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({enabled:!m.enabled})});status('Applied '+new Date().toLocaleTimeString());await loadModules()}catch(e){status(e.message,true)}finally{b.disabled=false}};card.appendChild(b);list.appendChild(card)})}
document.querySelectorAll('.tab').forEach(t=>t.onclick=()=>{document.querySelectorAll('.tab,.view').forEach(e=>e.classList.remove('active'));t.classList.add('active');document.getElementById(t.dataset.view).classList.add('active');if(t.dataset.view==='yaml'&&editor)editor.layout()});
require.config({paths:{vs:'https://cdn.jsdelivr.net/npm/monaco-editor@0.52.0/min/vs'}});require(['vs/editor/editor.main'],async()=>{const text=await fetch(base+'api/config').then(r=>r.text());editor=monaco.editor.create(document.getElementById('editor'),{value:text,language:'yaml',theme:'vs-dark',automaticLayout:true,minimap:{enabled:false}})});
document.getElementById('save').onclick=async()=>{status('Saving…');try{await request('api/config',{method:'POST',body:editor.getValue()});status('Saved and applied '+new Date().toLocaleTimeString())}catch(e){status(e.message,true)}};loadModules().catch(e=>status(e.message,true));
</script></body></html>"""


class Handler(http.server.BaseHTTPRequestHandler):
    def send_body(self, status, body, content_type="text/plain; charset=utf-8"):
        encoded = body.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(encoded)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(encoded)

    def do_GET(self):
        path = urlparse(self.path).path.rstrip("/") or "/"
        try:
            if path == "/":
                self.send_body(200, PAGE, "text/html; charset=utf-8")
            elif path == "/api/config":
                self.send_body(200, BASE_PATH.read_text(encoding="utf-8"))
            elif path == "/api/modules":
                available, enabled = reconcile()
                payload = {"modules": [{"slug": m["slug"], "name": m["name"], "description": m["description"], "enabled": m["slug"] in enabled} for m in available]}
                self.send_body(200, json.dumps(payload), "application/json")
            else:
                self.send_body(404, "not found")
        except Exception as exc:
            self.send_body(500, str(exc))

    def do_POST(self):
        path = urlparse(self.path).path.rstrip("/")
        length = int(self.headers.get("Content-Length", "0"))
        body = self.rfile.read(length)
        try:
            if path == "/api/config":
                candidate = body.decode("utf-8")
                parsed = yaml.safe_load(candidate)
                if not isinstance(parsed, dict) or not isinstance(parsed.get("pages"), list):
                    raise ValueError("YAML must contain a top-level pages list")
                previous = BASE_PATH.read_text(encoding="utf-8")
                atomic_write(BASE_PATH, candidate.rstrip() + "\n")
                try:
                    reconcile(restart=True)
                except Exception:
                    atomic_write(BASE_PATH, previous)
                    reconcile()
                    raise
            else:
                match = re.fullmatch(r"/api/modules/([a-z0-9][a-z0-9-]*)", path)
                if not match:
                    self.send_body(404, "not found")
                    return
                payload = json.loads(body or b"{}")
                if not isinstance(payload.get("enabled"), bool):
                    raise ValueError("enabled must be boolean")
                with LOCK:
                    available = modules()
                    known = {m["slug"] for m in available}
                    slug = match.group(1)
                    if slug not in known:
                        raise ValueError("unknown module")
                    enabled = load_state(available)
                    old_enabled = set(enabled)
                    enabled.add(slug) if payload["enabled"] else enabled.discard(slug)
                    save_state(enabled)
                    try:
                        reconcile(restart=True)
                    except Exception:
                        save_state(old_enabled)
                        reconcile()
                        raise
            self.send_body(200, json.dumps({"ok": True}), "application/json")
        except (ValueError, yaml.YAMLError, json.JSONDecodeError) as exc:
            self.send_body(400, str(exc))
        except Exception as exc:
            self.send_body(500, str(exc))

    def log_message(self, fmt, *args):
        print(f"{self.client_address[0]} {fmt % args}")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--reconcile", action="store_true")
    parser.add_argument("--restart", action="store_true")
    parser.add_argument("--host", default=os.environ.get("HOST", "127.0.0.1"))
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", "8081")))
    args = parser.parse_args()
    if args.reconcile:
        reconcile(restart=args.restart)
        return
    reconcile()
    server = http.server.ThreadingHTTPServer((args.host, args.port), Handler)
    print(f"Glance module manager listening on {args.host}:{args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()
