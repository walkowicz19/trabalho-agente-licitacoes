"""
Schemas (modelos de dados) usados em todo o projeto.
Define as estruturas que circulam entre API, agente e banco de dados.
"""

from dataclasses import dataclass, field
from typing import Optional


@dataclass
class FiltrosBusca:
    """Parâmetros de busca informados pelo usuário na interface."""
    palavra_chave: str
    valor_minimo: Optional[float] = None
    valor_maximo: Optional[float] = None
    score_minimo: int = 0
    orgao: Optional[str] = None
    data_encerramento_ate: Optional[str] = None
    pagina: int = 1
    quantidade: int = 20


@dataclass
class Licitacao:
    """Dados brutos de uma licitação retornada pela API do PNCP."""
    id: str
    numero: str
    orgao_nome: str
    orgao_cnpj: str
    objeto: str
    valor_estimado: Optional[float]
    data_encerramento: Optional[str]
    modalidade: str
    situacao: str
    link_edital: Optional[str]
    data_publicacao: Optional[str]
    uasg: Optional[str] = None


@dataclass
class AnaliseIA:
    """Resultado da análise gerada pelo Gemini para uma licitação."""
    score: int
    resumo: str
    pontos_fortes: list[str]
    riscos: list[str]
    pitch: str
    justificativa_score: str


@dataclass
class LicitacaoAnalisada:
    """Licitação com score e análise de IA — exibida nos cards do dashboard."""
    licitacao: Licitacao
    analise: AnaliseIA
    relevancia_pre_filtro: int   # Quantidade de palavras-chave encontradas antes do Gemini
    analisada_em: str            # Timestamp ISO da análise
