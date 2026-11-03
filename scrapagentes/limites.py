"""Limites da API (etapa 09): tamanho do corpo, requisições por chave e tempo de leitura do corpo.

São middlewares ASGI puros, sem dependência nova. O limite de requisições é em memória (um
processo de API só) e por chave; chaves erradas ou ausentes dividem um balde único, o que também
freia tentativas de adivinhar a chave. Nada aqui guarda nem registra o valor da chave recebida.
"""
import asyncio
import hmac
import json
import time
from collections import deque

JANELA_S = 60.0
ROTAS_LIVRES = {"/saude"}


class _CorpoGrande(Exception):
    pass


async def _responder(send, status: int, detalhe: str, extra: list[tuple[bytes, bytes]] | None = None):
    corpo = json.dumps({"detail": detalhe}, ensure_ascii=False).encode()
    cabecalhos = [(b"content-type", b"application/json"), (b"content-length", str(len(corpo)).encode())]
    await send({"type": "http.response.start", "status": status, "headers": cabecalhos + (extra or [])})
    await send({"type": "http.response.body", "body": corpo})


class LimiteDeCorpo:
    """413 quando o corpo passa do máximo (pelo Content-Length ou, sem ele, contando os bytes);
    408 quando o corpo demora demais para chegar."""

    def __init__(self, app, maximo_bytes: int, prazo_corpo_s: float):
        self.app, self.maximo, self.prazo = app, maximo_bytes, prazo_corpo_s

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        declarado = dict(scope["headers"]).get(b"content-length")
        if declarado and declarado.isdigit() and int(declarado) > self.maximo:
            return await _responder(send, 413, f"corpo maior que o máximo de {self.maximo // (1024 * 1024)} MiB")

        recebido = 0
        inicio = time.monotonic()
        iniciou_resposta = False

        async def receber():
            nonlocal recebido
            restante = self.prazo - (time.monotonic() - inicio)
            mensagem = await asyncio.wait_for(receive(), timeout=max(restante, 0.001))
            if mensagem["type"] == "http.request":
                recebido += len(mensagem.get("body", b""))
                if recebido > self.maximo:
                    raise _CorpoGrande()
            return mensagem

        async def enviar(mensagem):
            nonlocal iniciou_resposta
            if mensagem["type"] == "http.response.start":
                iniciou_resposta = True
            await send(mensagem)

        try:
            await self.app(scope, receber, enviar)
        except _CorpoGrande:
            if not iniciou_resposta:
                await _responder(send, 413, f"corpo maior que o máximo de {self.maximo // (1024 * 1024)} MiB")
        except asyncio.TimeoutError:
            if not iniciou_resposta:
                await _responder(send, 408, "tempo esgotado ao receber o corpo da requisição")


class LimiteDeRequisicoes:
    """Janela deslizante de 60 s por chave. `/saude` fica livre. 429 com `Retry-After`."""

    def __init__(self, app, por_minuto: int, chave_valida: str | None = None):
        self.app, self.limite = app, por_minuto
        self.chave_valida = chave_valida.encode() if chave_valida else None
        self.janelas: dict[str, deque[float]] = {}

    def _balde(self, headers: dict) -> str:
        chave = headers.get(b"x-api-key")
        if chave and self.chave_valida and hmac.compare_digest(chave, self.chave_valida):
            return "chave-valida"
        return "sem-chave-valida"  # ausentes e erradas dividem o mesmo balde

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope["path"] in ROTAS_LIVRES or self.limite <= 0:
            return await self.app(scope, receive, send)
        agora = time.monotonic()
        janela = self.janelas.setdefault(self._balde(dict(scope["headers"])), deque())
        while janela and agora - janela[0] >= JANELA_S:
            janela.popleft()
        if len(janela) >= self.limite:
            espera = int(JANELA_S - (agora - janela[0])) + 1
            return await _responder(
                send, 429, "limite de requisições por minuto atingido",
                [(b"retry-after", str(espera).encode())],
            )
        janela.append(agora)
        if len(self.janelas) > 1000:  # nunca cresce sem fim
            for k in [k for k, v in self.janelas.items() if not v or agora - v[-1] >= JANELA_S]:
                self.janelas.pop(k, None)
        await self.app(scope, receive, send)
