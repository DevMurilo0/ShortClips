"""ShortForge Vercel API gateway.

This HTTP function is deliberately LIGHTWEIGHT. Video encoding and AI transcription
must run in a persistent worker. No user-uploaded media passes through this function.
"""
from http.server import BaseHTTPRequestHandler
import hmac
import json
import os
import re
from urllib.parse import urlsplit
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError


MAX_JSON = 32 * 1024
JOB_PATTERN = re.compile(r"/api/jobs/[a-f0-9]{8,40}(?:/(?:cancel|retry))?$")


def env(key):
    return os.environ.get(key, "").strip()


def configuration():
    worker = env("SHORTFORGE_WORKER_URL").rstrip("/")
    secret = env("SHORTFORGE_WORKER_SECRET")
    public_key = env("SHORTFORGE_PUBLIC_ACCESS_KEY")
    origin = env("SHORTFORGE_FRONTEND_ORIGIN").rstrip("/")
    valid_worker = bool(worker and urlsplit(worker).scheme == "https"
                        and urlsplit(worker).netloc
                        and not urlsplit(worker).username
                        and urlsplit(worker).path in ("", "/")
                        and not urlsplit(worker).query)
    return {
        "worker": worker if valid_worker else "",
        "secret": secret,
        "public_key": public_key,
        "origin": origin,
        "ready": bool(valid_worker and secret and public_key and origin),
    }


class handler(BaseHTTPRequestHandler):
    def _cors(self):
        origin = self.headers.get("Origin", "").rstrip("/")
        allowed = configuration()["origin"]
        if origin and origin == allowed:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _reply(self, status, data, extra=None):
        raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Content-Length", str(len(raw)))
        self._cors()
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(raw)

    def _path(self):
        return urlsplit(self.path).path

    def _authorized(self, cfg):
        expected = cfg["public_key"]
        if not expected:
            return False
        header = self.headers.get("Authorization", "")
        scheme, _, submitted = header.partition(" ")
        return (scheme.lower() == "bearer"
                and hmac.compare_digest(submitted.strip(), expected))

    def _validate_origin(self, cfg):
        origin = self.headers.get("Origin", "").rstrip("/")
        return not origin or (cfg["origin"] and hmac.compare_digest(origin, cfg["origin"]))

    def _check(self):
        cfg = configuration()
        if not self._validate_origin(cfg):
            self._reply(403, {"error": "Origem não permitida."})
            return None
        if not cfg["ready"]:
            self._reply(503, {"error": "A API está instalada, mas o worker e a autenticação ainda não foram configurados."})
            return None
        if not self._authorized(cfg):
            self._reply(401, {"error": "Chave de acesso inválida ou ausente."},
                        {"WWW-Authenticate": "Bearer"})
            return None
        return cfg

    def _proxy(self, cfg, method, payload=None):
        path = self._path()
        if path not in ("/api/jobs", "/api/jobs/latest") and not JOB_PATTERN.fullmatch(path):
            return self._reply(404, {"error": "Rota não encontrada."})
        if method == "POST" and path != "/api/jobs" and not path.endswith(("/cancel", "/retry")):
            return self._reply(405, {"error": "Método não permitido."})
        body = None
        if method == "POST":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if not 0 < length <= MAX_JSON:
                    raise ValueError("Corpo da solicitação inválido.")
                body = self.rfile.read(length)
                data = json.loads(body)
                if not isinstance(data, dict):
                    raise ValueError("JSON deve ser um objeto.")
            except (ValueError, json.JSONDecodeError):
                return self._reply(400, {"error": "JSON inválido."})
        url = cfg["worker"] + path
        headers = {"Accept": "application/json",
                   "X-ShortForge-Worker-Secret": cfg["secret"]}
        if method == "POST":
            headers["Content-Type"] = "application/json"
        request = Request(url, data=body, headers=headers, method=method)
        try:
            with urlopen(request, timeout=25) as response:
                result = response.read(MAX_JSON * 24 + 1)
                if len(result) > MAX_JSON * 24:
                    raise ValueError("Resposta da API interna muito grande.")
                data = json.loads(result)
                return self._reply(response.status, data)
        except HTTPError as exc:
            try:
                body = exc.read(MAX_JSON)
                detail = json.loads(body)
            except (ValueError, json.JSONDecodeError):
                detail = {"error": "Falha comunicando-se com o worker."}
            return self._reply(exc.code, detail)
        except (URLError, OSError, ValueError, TimeoutError):
            return self._reply(502, {"error": "O worker de processamento não está respondendo."})

    def do_OPTIONS(self):
        cfg = configuration()
        if not cfg["origin"] or self.headers.get("Origin", "").rstrip("/") != cfg["origin"]:
            return self._reply(403, {"error": "Origem não permitida."})
        self.send_response(204)
        self._cors()
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type, Authorization")
        self.send_header("Access-Control-Max-Age", "3600")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        if self._path() == "/api/health":
            cfg = configuration()
            return self._reply(200, {"ok": True, "service": "ShortForge API",
                                     "ready": cfg["ready"],
                                     "processor": "separate-worker",
                                     "reason": None if cfg["ready"] else "Worker não configurado."})
        cfg = self._check()
        if cfg is None:
            return
        if self._path().startswith("/downloads/"):
            return self._reply(501, {"error": "Downloads públicos exigem armazenamento de objetos e URLs assinadas; não estão habilitados nesta versão."})
        return self._proxy(cfg, "GET")

    def do_POST(self):
        cfg = self._check()
        if cfg is None:
            return
        return self._proxy(cfg, "POST")
