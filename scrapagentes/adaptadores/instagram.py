"""Adaptador `instagram`: posts públicos (foto, carrossel e reel), sem login.

Duas camadas:
- `AdaptadorInstagram` aplica as regras do contrato sobre dados já lidos (`DadosPost`);
- uma fonte entrega esses dados e baixa a mídia. A padrão é `FonteInstaloader`; nos testes entra
  uma fonte gravada, sem rede.

Configuração (só aqui, o núcleo não lê): `SCRAPAGENTES_PROXY` (ex.: `socks5h://127.0.0.1:1080`, o
túnel do celular; pode carregar credenciais, nunca é registrada em log nem em mensagem de erro) e
`SCRAPAGENTES_IG_INTERVALO_S` (intervalo mínimo entre consultas ao Instagram, padrão 5 s).
Proxy configurado e fora do ar vira `indisponivel`; nunca se cai em silêncio para o IP da VPS.

Modo de inspeção: `python -m scrapagentes.adaptadores.instagram <url>` resolve a URL, imprime o
relatório e apaga a mídia. Com `--dados` imprime só os dados lidos, em JSON (para gravar fixtures).
"""
import json
import os
import re
import shutil
import sys
import tempfile
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import timezone
from pathlib import Path
from urllib.parse import urlparse

from scrapagentes import midia
from scrapagentes.adaptadores.base import (
    Adaptador, Bloqueado, ErroAdaptador, ExigeLogin, FormatoNaoSuportado, Indisponivel,
    NaoEncontrado, Resolvido,
)

HOSTS = {"instagram.com", "www.instagram.com", "m.instagram.com"}
_CAMINHO = re.compile(r"^/(?:[A-Za-z0-9._]+/)?(?:p|reel|reels|tv)/([A-Za-z0-9_-]+)/?$")
PROXIES_ACEITOS = {"socks5h", "socks5", "http", "https"}
INTERVALO_PADRAO_S = 5.0
LIMITE_DOWNLOAD_BYTES = 300 * 1024 * 1024


@dataclass
class MidiaRemota:
    url: str
    video: bool


@dataclass
class DadosPost:
    """O que a fonte leu do post, já em tipos simples (é o que as fixtures gravam)."""
    shortcode: str
    tipo: str  # GraphImage, GraphVideo ou GraphSidecar (vocabulário do Instaloader)
    conta: str
    data_utc: str  # ISO 8601 com fuso
    legenda: str
    curtidas: int | None
    comentarios: int | None
    visualizacoes: int | None
    duracao_s: float | None
    midias: list[MidiaRemota] = field(default_factory=list)

    @classmethod
    def de_dict(cls, d: dict) -> "DadosPost":
        return cls(**{**d, "midias": [MidiaRemota(**m) for m in d["midias"]]})


# ---------- regras do contrato (puras, testáveis sem rede) ----------

def extrair_shortcode(url: str) -> str:
    """Devolve o shortcode de uma URL de post do Instagram; ValueError se não for uma."""
    partes = urlparse((url or "").strip())
    if partes.scheme not in ("http", "https") or (partes.hostname or "").lower() not in HOSTS:
        raise ValueError("não é uma URL de post do Instagram")
    m = _CAMINHO.match(partes.path)
    if not m:
        raise ValueError("a URL não aponta para um post (/p/, /reel/ ou /tv/)")
    return m.group(1)


def classificar(dados: DadosPost) -> str:
    """Formato do post no vocabulário do projeto."""
    if not dados.midias:
        raise Indisponivel("o Instagram não devolveu mídia para o post")
    if dados.tipo == "GraphImage":
        if dados.midias[0].video:
            raise FormatoNaoSuportado("post marcado como imagem, mas a mídia é vídeo")
        return "foto"
    if dados.tipo == "GraphVideo":
        if len(dados.midias) != 1 or not dados.midias[0].video:
            raise FormatoNaoSuportado("post de vídeo sem exatamente um arquivo de vídeo")
        return "video"
    if dados.tipo == "GraphSidecar":
        if any(m.video for m in dados.midias):
            raise FormatoNaoSuportado("carrossel com vídeo em algum slide não é suportado")
        return "carrossel"
    raise FormatoNaoSuportado(f"tipo de post desconhecido: {dados.tipo}")


def metricas_de(dados: DadosPost) -> dict[str, float]:
    """Só entra o que veio: curtidas ocultas (-1) e visualizações ausentes ficam de fora."""
    saida = {}
    for nome, valor in (
        ("curtidas", dados.curtidas), ("comentarios", dados.comentarios),
        ("visualizacoes", dados.visualizacoes),
    ):
        if valor is not None and valor >= 0:
            saida[nome] = float(valor)
    return saida


def _extensao(midia_remota: MidiaRemota) -> str:
    sufixo = Path(urlparse(midia_remota.url).path).suffix.lower()
    if midia_remota.video:
        return sufixo if sufixo in {".mp4", ".mov", ".webm"} else ".mp4"
    return sufixo if sufixo in {".jpg", ".jpeg", ".png", ".webp"} else ".jpg"


# ---------- adaptador ----------

class AdaptadorInstagram(Adaptador):
    nome = "instagram"
    formatos = ("video", "foto", "carrossel")
    metricas_suportadas = frozenset({"curtidas", "comentarios", "visualizacoes"})

    def __init__(self, fonte=None, pasta_tmp: Path | None = None):
        self._fonte_injetada = fonte
        self._pasta_tmp = pasta_tmp

    def _fonte(self):
        if self._fonte_injetada is None:
            self._fonte_injetada = FonteInstaloader.do_ambiente()
        return self._fonte_injetada

    def reconhece(self, url: str) -> bool:
        try:
            extrair_shortcode(url)
        except ValueError:
            return False
        return True

    def canonizar_url(self, url: str, entrada: dict | None = None) -> str:
        return f"https://www.instagram.com/p/{extrair_shortcode(url)}/"

    def resolver(self, url: str, entrada: dict | None = None) -> Resolvido:
        fonte = self._fonte()
        dados = fonte.obter(extrair_shortcode(url))
        formato = classificar(dados)
        pasta = Path(tempfile.mkdtemp(prefix="scrapagentes-ig-", dir=self._pasta_tmp))
        try:
            arquivos = [
                fonte.baixar(m.url, pasta / f"{i:03d}{_extensao(m)}")
                for i, m in enumerate(dados.midias, start=1)
            ]
            duracao = None
            if formato == "video":
                duracao = dados.duracao_s or midia.duracao_video(arquivos[0])
                if not duracao or duracao <= 0:
                    raise Indisponivel("não foi possível ler a duração do vídeo baixado")
            return Resolvido(
                conta=dados.conta, formato=formato, data_publicacao=dados.data_utc,
                legenda=dados.legenda or "", duracao_s=duracao, arquivos=arquivos,
                metricas=metricas_de(dados), pasta_temporaria=pasta,
            )
        except BaseException:
            shutil.rmtree(pasta, ignore_errors=True)
            raise

    def coletar_metricas(self, item: dict, entrada: dict | None = None) -> dict[str, float]:
        dados = self._fonte().obter(extrair_shortcode(item["url"]))
        return metricas_de(dados)


# ---------- fonte real: Instaloader ----------

class Limitador:
    """Garante um intervalo mínimo entre consultas (vale para todas as threads do processo)."""

    def __init__(self, intervalo_s: float, relogio=time.monotonic, dormir=time.sleep):
        self._intervalo, self._relogio, self._dormir = intervalo_s, relogio, dormir
        self._ultima: float | None = None
        self._trava = threading.Lock()

    def esperar(self) -> None:
        with self._trava:
            if self._ultima is not None:
                falta = self._intervalo - (self._relogio() - self._ultima)
                if falta > 0:
                    self._dormir(falta)
            self._ultima = self._relogio()


def validar_proxy(proxy: str | None) -> str | None:
    if not proxy:
        return None
    esquema = urlparse(proxy).scheme
    if esquema not in PROXIES_ACEITOS:
        # Não ecoa o valor: pode conter credenciais.
        raise ValueError(f"SCRAPAGENTES_PROXY com esquema inválido; aceitos: {sorted(PROXIES_ACEITOS)}")
    return proxy


class FonteInstaloader:
    def __init__(self, proxy: str | None = None, intervalo_s: float = INTERVALO_PADRAO_S,
                 timeout_s: float = 25, limitador: Limitador | None = None):
        import instaloader
        import requests

        self._il = instaloader
        self._proxy = validar_proxy(proxy)
        self._limitador = limitador or Limitador(intervalo_s)
        self._loader = instaloader.Instaloader(
            quiet=True, download_pictures=False, download_videos=False,
            download_video_thumbnails=False, download_geotags=False, download_comments=False,
            save_metadata=False, compress_json=False,
            max_connection_attempts=1, request_timeout=timeout_s,
        )
        self._http = requests.Session()
        if self._proxy:
            proxies = {"http": self._proxy, "https": self._proxy}
            self._http.proxies.update(proxies)
            # O Instaloader não expõe proxy por opção; a sessão dele é a mesma usada nas consultas.
            self._loader.context._session.proxies.update(proxies)

    @classmethod
    def do_ambiente(cls) -> "FonteInstaloader":
        return cls(
            proxy=os.environ.get("SCRAPAGENTES_PROXY") or None,
            intervalo_s=float(os.environ.get("SCRAPAGENTES_IG_INTERVALO_S", INTERVALO_PADRAO_S)),
        )

    def _traduzir(self, exc: Exception) -> ErroAdaptador:
        """Instaloader -> erros tipados. Nunca repassa o texto original: ele pode citar o proxy."""
        e = self._il.exceptions
        via = " (via proxy configurado)" if self._proxy else ""
        if isinstance(exc, ErroAdaptador):
            return exc
        if isinstance(exc, e.QueryReturnedNotFoundException):
            return NaoEncontrado("o Instagram respondeu que o post não existe")
        if isinstance(exc, (e.TooManyRequestsException, e.QueryReturnedForbiddenException)):
            return Bloqueado("o Instagram limitou ou bloqueou as consultas (429/403)")
        if isinstance(exc, (e.LoginRequiredException, e.PrivateProfileNotFollowedException)):
            return ExigeLogin("o post exige login (conta privada ou conteúdo restrito)")
        if isinstance(exc, e.QueryReturnedBadRequestException):
            return Indisponivel("o Instagram recusou a consulta (400)")
        if isinstance(exc, e.BadResponseException):
            return Indisponivel(
                "o Instagram não devolveu os dados do post (removido, restrito ou falha do servidor)"
            )
        if isinstance(exc, e.ConnectionException):
            return Indisponivel(f"falha de conexão com o Instagram{via}")
        if isinstance(exc, e.InstaloaderException):
            return Indisponivel(f"falha do Instaloader: {type(exc).__name__}")
        return Indisponivel(f"falha inesperada ao consultar o Instagram: {type(exc).__name__}")

    def obter(self, shortcode: str) -> DadosPost:
        self._limitador.esperar()
        try:
            p = self._il.Post.from_shortcode(self._loader.context, shortcode)
            if p.typename == "GraphSidecar":
                midias = [MidiaRemota(n.video_url if n.is_video else n.display_url, bool(n.is_video))
                          for n in p.get_sidecar_nodes()]
            elif p.is_video:
                midias = [MidiaRemota(p.video_url, True)]
            else:
                midias = [MidiaRemota(p.url, False)]
            return DadosPost(
                shortcode=shortcode, tipo=p.typename, conta=p.owner_username,
                data_utc=p.date_utc.replace(tzinfo=timezone.utc).isoformat(),
                legenda=p.caption or "", curtidas=p.likes, comentarios=p.comments,
                visualizacoes=p.video_view_count if p.is_video else None,
                duracao_s=p.video_duration if p.is_video else None, midias=midias,
            )
        except Exception as exc:
            raise self._traduzir(exc) from None

    def baixar(self, url: str, destino: Path) -> Path:
        if urlparse(url).scheme != "https":
            raise Indisponivel("o Instagram devolveu um endereço de mídia que não é https")
        via = " (via proxy configurado)" if self._proxy else ""
        try:
            with self._http.get(url, stream=True, timeout=(10, 60)) as r:
                if r.status_code == 404:
                    raise NaoEncontrado("a mídia do post não está mais disponível")
                if r.status_code in (401, 403, 429):
                    raise Bloqueado(f"a CDN do Instagram recusou o download ({r.status_code})")
                if r.status_code != 200:
                    raise Indisponivel(f"a CDN do Instagram respondeu {r.status_code}")
                total = 0
                with destino.open("wb") as f:
                    for bloco in r.iter_content(1024 * 256):
                        total += len(bloco)
                        if total > LIMITE_DOWNLOAD_BYTES:
                            raise Indisponivel("a mídia passa do limite de tamanho aceito")
                        f.write(bloco)
        except ErroAdaptador:
            raise
        except Exception as exc:
            raise Indisponivel(f"falha ao baixar a mídia{via}: {type(exc).__name__}") from None
        if destino.stat().st_size == 0:
            raise Indisponivel("a mídia baixada veio vazia")
        return destino


# ---------- modo de inspeção ----------

def _relatorio(url: str) -> None:
    adaptador = AdaptadorInstagram()
    r = adaptador.resolver(adaptador.canonizar_url(url))
    try:
        print(f"url canônica : {adaptador.canonizar_url(url)}")
        print(f"formato      : {r.formato}")
        print(f"conta        : {r.conta}")
        print(f"data (UTC)   : {r.data_publicacao}")
        print(f"legenda      : {len(r.legenda)} caracteres" + (f" | {r.legenda[:80]!r}" if r.legenda else " (vazia)"))
        print(f"duração (s)  : {r.duracao_s}")
        print(f"métricas     : {r.metricas or 'nenhuma'}")
        print(f"mídia        : {len(r.arquivos)} arquivo(s)")
        for a in r.arquivos:
            print(f"  - {a.name}  {a.stat().st_size} bytes")
    finally:
        if r.pasta_temporaria:
            shutil.rmtree(r.pasta_temporaria, ignore_errors=True)


def main(argv: list[str]) -> int:
    soh_dados = "--dados" in argv
    urls = [a for a in argv if not a.startswith("--")]
    if len(urls) != 1:
        print("uso: python -m scrapagentes.adaptadores.instagram [--dados] <url>", file=sys.stderr)
        return 2
    try:
        if soh_dados:
            dados = FonteInstaloader.do_ambiente().obter(extrair_shortcode(urls[0]))
            print(json.dumps(asdict(dados), ensure_ascii=False, indent=2))
        else:
            _relatorio(urls[0])
    except (ErroAdaptador, ValueError) as exc:
        codigo = getattr(exc, "codigo", "entrada_invalida")
        print(f"ERRO {codigo}: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
