"""
Analisador — orquestra o fluxo completo do agente:
  1. Busca licitações no PNCP
  2. Aplica pré-filtro de palavras-chave
  3. Classifica cada licitação com o Gemini
  4. Salva no banco de dados
  5. Emite eventos de progresso via fila (para SSE no frontend)

A fila de progresso é um asyncio.Queue que a rota SSE consome.
"""

import json
import asyncio
from datetime import datetime

from modelos.schemas import FiltrosBusca, LicitacaoAnalisada
from agente.buscador import buscar_licitacoes
from agente.classificador import classificar_licitacao
from utils.filtro_relevancia import calcular_relevancia, passou_no_filtro
from utils import banco


def carregar_perfil_empresa(caminho: str = "empresa.json") -> dict:
    """Carrega o perfil da empresa a partir do arquivo JSON."""
    with open(caminho, encoding="utf-8") as arquivo:
        return json.load(arquivo)


async def executar_analise(
    filtros: FiltrosBusca,
    fila_progresso: asyncio.Queue,
) -> list[LicitacaoAnalisada]:
    """
    Executa o fluxo completo do agente de forma assíncrona.
    Publica eventos de progresso na fila para o SSE consumir.

    Etapas:
      etapa_1 — Buscando no PNCP
      etapa_2 — Aplicando pré-filtro
      etapa_3 — Analisando com Gemini
      etapa_4 — Calculando scores
      etapa_5 — Salvando e finalizando
    """
    perfil_empresa = carregar_perfil_empresa()
    palavras_chave = perfil_empresa.get("palavras_chave_busca", [])

    # ── Etapa 1: Busca no PNCP ──────────────────────────────────────────────
    await fila_progresso.put({"etapa": 1, "status": "ativo", "mensagem": "Buscando licitações no PNCP..."})

    licitacoes_brutas = await asyncio.to_thread(buscar_licitacoes, filtros)

    await fila_progresso.put({
        "etapa": 1, "status": "concluido",
        "mensagem": f"{len(licitacoes_brutas)} licitações encontradas no PNCP.",
    })

    # ── Etapa 2: Pré-filtro de relevância ──────────────────────────────────
    await fila_progresso.put({"etapa": 2, "status": "ativo", "mensagem": "Aplicando filtro de relevância..."})

    # Calcula a relevância inicial e ordena
    candidatas = []
    for l in licitacoes_brutas:
        rel = calcular_relevancia(l.numero, l.objeto, palavras_chave)
        if rel >= 1:
            candidatas.append((l, rel))

    # Ordena pelo maior número de termos correspondentes e seleciona as top 6
    candidatas.sort(key=lambda x: x[1], reverse=True)
    licitacoes_filtradas = [c[0] for c in candidatas[:6]]

    descartadas = len(licitacoes_brutas) - len(licitacoes_filtradas)
    await fila_progresso.put({
        "etapa": 2, "status": "concluido",
        "mensagem": f"{len(licitacoes_filtradas)} oportunidades selecionadas para análise com IA ({descartadas} descartadas).",
    })

    if not licitacoes_filtradas:
        await fila_progresso.put({"etapa": 5, "status": "concluido", "mensagem": "Nenhuma licitação compatível encontrada.", "total": 0})
        return []

    # ── Etapa 3: Análise com Gemini ─────────────────────────────────────────
    await fila_progresso.put({
        "etapa": 3, "status": "ativo",
        "mensagem": f"Analisando {len(licitacoes_filtradas)} licitações com IA...",
    })

    resultados: list[LicitacaoAnalisada] = []

    for i, licitacao in enumerate(licitacoes_filtradas, start=1):
        nome_curto = licitacao.orgao_nome[:35] if licitacao.orgao_nome else "Órgão"
        mensagem_ia = f"Analisando {i}/{len(licitacoes_filtradas)}: {nome_curto}..."
        await fila_progresso.put({"etapa": 3, "status": "ativo", "mensagem": mensagem_ia})

        try:
            analise = await asyncio.to_thread(classificar_licitacao, licitacao, perfil_empresa)
        except Exception as erro:
            from agente.classificador import _gerar_analise_heuristica, _converter_para_analise
            analise = _converter_para_analise(_gerar_analise_heuristica(licitacao, perfil_empresa))

        relevancia = calcular_relevancia(licitacao.numero, licitacao.objeto, palavras_chave)

        licitacao_analisada = LicitacaoAnalisada(
            licitacao=licitacao,
            analise=analise,
            relevancia_pre_filtro=relevancia,
            analisada_em=datetime.now().isoformat(),
        )
        resultados.append(licitacao_analisada)

    await fila_progresso.put({"etapa": 3, "status": "concluido", "mensagem": f"{len(resultados)} licitações analisadas com sucesso."})

    # ── Etapa 4: Ordenação por score ────────────────────────────────────────
    await fila_progresso.put({"etapa": 4, "status": "ativo", "mensagem": "Ordenando por score de adequação..."})

    resultados.sort(key=lambda r: r.analise.score, reverse=True)

    await fila_progresso.put({"etapa": 4, "status": "concluido", "mensagem": "Resultados ordenados por score."})


    # ── Etapa 5: Salvar no banco ────────────────────────────────────────────
    await fila_progresso.put({"etapa": 5, "status": "ativo", "mensagem": "Salvando resultados no histórico..."})

    banco.criar_tabelas()
    busca_id = await asyncio.to_thread(
        banco.salvar_busca,
        filtros.palavra_chave,
        {"valor_minimo": filtros.valor_minimo, "valor_maximo": filtros.valor_maximo},
        len(licitacoes_brutas),
        len(resultados),
    )
    for item in resultados:
        await asyncio.to_thread(banco.salvar_licitacao_analisada, item, busca_id)

    await fila_progresso.put({
        "etapa": 5, "status": "concluido",
        "mensagem": f"Pronto! {len(resultados)} oportunidades encontradas.",
        "total": len(resultados),
    })

    return resultados
