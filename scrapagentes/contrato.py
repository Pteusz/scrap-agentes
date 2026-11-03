"""Suite de contrato reutilizável (SPEC, seção 4).

Todo adaptador precisa passar em `verificar_adaptador`: campos obrigatórios presentes, formato
dentro do vocabulário declarado, métricas com nomes e valores numéricos e erros tipados.
Falhas levantam AssertionError com a explicação.
"""
from dataclasses import dataclass
from datetime import datetime
from numbers import Real
from pathlib import Path

from scrapagentes.adaptadores.base import (
    ERROS_TIPADOS, METRICAS_PADRAO, Adaptador, ErroAdaptador, Resolvido,
)


@dataclass
class Exemplo:
    """Entrada que o adaptador deve resolver com sucesso."""
    url: str
    entrada: dict | None = None


@dataclass
class ExemploErro:
    """Entrada que deve falhar com um erro tipado específico."""
    url: str
    erro: type[ErroAdaptador]
    entrada: dict | None = None


def _exigir(condicao: bool, mensagem: str) -> None:
    if not condicao:
        raise AssertionError(f"contrato do adaptador violado: {mensagem}")


def _verificar_metricas(adaptador: Adaptador, metricas, origem: str) -> None:
    _exigir(isinstance(metricas, dict), f"{origem}: métricas devem ser um dict nome -> valor")
    permitidas = set(METRICAS_PADRAO) | set(adaptador.metricas_suportadas)
    for nome, valor in metricas.items():
        _exigir(isinstance(nome, str) and nome, f"{origem}: nome de métrica inválido: {nome!r}")
        _exigir(nome in permitidas, f"{origem}: métrica não declarada pelo adaptador: {nome}")
        _exigir(
            isinstance(valor, Real) and not isinstance(valor, bool),
            f"{origem}: valor não numérico em {nome}: {valor!r}",
        )


def _verificar_resolvido(adaptador: Adaptador, r: Resolvido) -> None:
    _exigir(isinstance(r, Resolvido), "resolver deve devolver Resolvido")
    _exigir(bool(r.conta), "conta ausente")
    _exigir(r.formato in adaptador.formatos, f"formato fora do vocabulário declarado: {r.formato}")
    try:
        datetime.fromisoformat(r.data_publicacao)
    except (TypeError, ValueError):
        raise AssertionError("contrato do adaptador violado: data_publicacao não é ISO 8601")
    _exigir(isinstance(r.legenda, str), "legenda deve ser texto (pode ser vazia)")
    _exigir(len(r.arquivos) >= 1, "nenhum arquivo de mídia devolvido")
    for a in r.arquivos:
        _exigir(Path(a).is_file() and Path(a).stat().st_size > 0, f"arquivo ausente ou vazio: {a}")
    if r.formato == "video":
        _exigir(isinstance(r.duracao_s, Real) and r.duracao_s > 0, "vídeo exige duracao_s > 0")
    else:
        _exigir(r.duracao_s is None, "duracao_s só existe em vídeo")
    _verificar_metricas(adaptador, r.metricas, "resolver")


def verificar_adaptador(
    adaptador: Adaptador, exemplos: list[Exemplo], exemplos_erro: list[ExemploErro] = ()
) -> None:
    _exigir(isinstance(adaptador.nome, str) and adaptador.nome, "nome da rede ausente")
    _exigir(len(adaptador.formatos) > 0, "formatos válidos não declarados")
    _exigir(len(exemplos) > 0, "a suite precisa de ao menos um exemplo válido")

    for ex in exemplos:
        url = adaptador.canonizar_url(ex.url, ex.entrada)
        _exigir(isinstance(url, str) and url, "canonizar_url deve devolver texto não vazio")
        _exigir(
            adaptador.canonizar_url(url, ex.entrada) == url,
            "canonizar_url deve ser idempotente",
        )
        _exigir(adaptador.reconhece(url) in (True, False), "reconhece deve devolver bool")
        resolvido = adaptador.resolver(url, ex.entrada)
        _verificar_resolvido(adaptador, resolvido)
        coletadas = adaptador.coletar_metricas(
            {"rede": adaptador.nome, "url": url, "formato": resolvido.formato}, ex.entrada
        )
        _verificar_metricas(adaptador, coletadas, "coletar_metricas")

    for ex in exemplos_erro:
        _exigir(ex.erro in ERROS_TIPADOS, f"{ex.erro} não é um erro tipado do contrato")
        try:
            adaptador.resolver(ex.url, ex.entrada)
        except ErroAdaptador as exc:
            _exigir(
                type(exc) is ex.erro,
                f"esperava {ex.erro.codigo}, veio {type(exc).codigo}",
            )
        except Exception as exc:
            raise AssertionError(
                f"contrato do adaptador violado: erro não tipado ({type(exc).__name__}) "
                f"onde se esperava {ex.erro.codigo}"
            ) from exc
        else:
            raise AssertionError(
                f"contrato do adaptador violado: esperava erro {ex.erro.codigo}, não houve erro"
            )
