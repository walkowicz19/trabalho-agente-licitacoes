"""
Rotas da API FastAPI.
Define todos os endpoints que o frontend consome.
"""

import asyncio
import json
from dataclasses import asdict
from typing import Optional

from fastapi import APIRouter, Query
from fastapi.responses import StreamingResponse, Response

from modelos.schemas import FiltrosBusca
from agente.analisador import executar_analise, carregar_perfil_empresa
from utils import banco, exportador

roteador = APIRouter()

# Armazena os resultados da última busca em memória (simples, sem cache externo)
_ultima_analise: list = []


@roteador.post("/buscar")
async def buscar(
    palavra_chave: str,
    valor_minimo: Optional[float] = None,
    valor_maximo: Optional[float] = None,
    score_minimo: int = 0,
    pagina: int = 1,
):
    """
    Inicia uma nova busca e análise de licitações.
    Retorna o stream de progresso via SSE — use GET /progresso para acompanhar.
    """
    global _ultima_analise

    filtros = FiltrosBusca(
        palavra_chave=palavra_chave,
        valor_minimo=valor_minimo,
        valor_maximo=valor_maximo,
        score_minimo=score_minimo,
        pagina=pagina,
    )

    # Fila de progresso compartilhada com o endpoint SSE
    fila_progresso = asyncio.Queue()
    _filas_ativas[palavra_chave] = fila_progresso

    # Executa a análise em background (não bloqueia o endpoint)
    async def rodar_analise():
        global _ultima_analise
        try:
            resultados = await executar_analise(filtros, fila_progresso)
            _ultima_analise = resultados
        except Exception as erro:
            print(f"Erro ao executar analise: {erro}")
            await fila_progresso.put({
                "etapa": 5,
                "status": "concluido",
                "mensagem": f"Processamento concluído com avisos.",
                "total": len(_ultima_analise),
            })

    asyncio.create_task(rodar_analise())

    return {"status": "iniciado", "palavra_chave": palavra_chave}


@roteador.get("/resultados")
def resultados(score_minimo: int = Query(default=0, ge=0, le=100)):
    """
    Retorna as licitações analisadas da última busca ou do banco SQLite,
    filtradas pelo score mínimo informado.
    """
    dados = _obter_dados_analise()

    filtrados = [
        r for r in dados
        if r["analise"]["score"] >= score_minimo
    ]

    return {
        "resultados": filtrados,
        "total": len(filtrados),
    }


@roteador.get("/progresso")
async def progresso(palavra_chave: str):
    """
    Stream de progresso do agente via Server-Sent Events (SSE).
    O frontend escuta este endpoint para animar o diagrama de fluxo.
    """
    fila = _filas_ativas.get(palavra_chave)

    if fila is None:
        # Sem busca ativa, retorna fim imediato
        async def sem_atividade():
            yield "data: {\"etapa\": 0, \"status\": \"inativo\"}\n\n"
        return StreamingResponse(sem_atividade(), media_type="text/event-stream")

    async def gerador_sse():
        """Lê da fila e envia eventos SSE ao browser."""
        while True:
            try:
                evento = await asyncio.wait_for(fila.get(), timeout=60.0)
                yield f"data: {json.dumps(evento, ensure_ascii=False)}\n\n"

                # Encerra o stream quando a etapa 5 for concluída
                if evento.get("etapa") == 5 and evento.get("status") == "concluido":
                    _filas_ativas.pop(palavra_chave, None)
                    break

            except asyncio.TimeoutError:
                # Keepalive para o browser não fechar a conexão
                yield ": keepalive\n\n"

    return StreamingResponse(gerador_sse(), media_type="text/event-stream")


@roteador.get("/historico")
def historico():
    """Retorna o histórico das últimas buscas salvas no banco."""
    banco.criar_tabelas()
    return {"historico": banco.buscar_historico(limite=20)}


@roteador.delete("/historico")
@roteador.post("/historico/limpar")
def limpar_historico():
    """Limpa todo o histórico de buscas e licitações salvas."""
    global _ultima_analise
    _ultima_analise = []
    banco.limpar_historico()
    return {"sucesso": True, "mensagem": "Histórico limpo com sucesso."}



@roteador.get("/exportar/csv")
def exportar_csv():
    """Gera e retorna um arquivo CSV com os resultados da última busca ou salvos no banco."""
    dados = _obter_dados_analise()
    if not dados:
        return Response(content="Nenhum resultado para exportar.", status_code=404)

    conteudo_csv = exportador.gerar_csv(dados)

    return Response(
        content=conteudo_csv,
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": "attachment; filename=licitacoes-techbridge.csv"},
    )


@roteador.get("/exportar/pdf")
def exportar_pdf():
    """Gera e retorna um relatório PDF com os resultados da última busca ou salvos no banco."""
    dados = _obter_dados_analise()
    if not dados:
        return Response(content="Nenhum resultado para exportar.", status_code=404)

    perfil = carregar_perfil_empresa()
    conteudo_pdf = exportador.gerar_pdf(dados, nome_empresa=perfil["nome"])

    return Response(
        content=conteudo_pdf,
        media_type="application/pdf",
        headers={"Content-Disposition": "attachment; filename=relatorio-licitacoes.pdf"},
    )


# ── Helpers ────────────────────────────────────────────────────────────────

# Dicionário de filas ativas: chave = palavra_chave da busca
_filas_ativas: dict[str, asyncio.Queue] = {}


def _obter_dados_analise() -> list[dict]:
    """Retorna os dados da última análise em memória ou recupera do banco SQLite."""
    global _ultima_analise
    if _ultima_analise:
        return [_serializar(r) for r in _ultima_analise]

    # Fallback para banco SQLite
    return banco.buscar_licitacoes_salvas(limite=50)


def _serializar(licitacao_analisada) -> dict:
    """Converte LicitacaoAnalisada para dict serializável (JSON-safe)."""
    return {
        "licitacao": asdict(licitacao_analisada.licitacao),
        "analise": asdict(licitacao_analisada.analise),
        "relevancia_pre_filtro": licitacao_analisada.relevancia_pre_filtro,
        "analisada_em": licitacao_analisada.analisada_em,
    }

