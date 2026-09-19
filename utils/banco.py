"""
Operações com o banco de dados SQLite.
Salva e recupera licitações analisadas e histórico de buscas.
"""

import sqlite3
import json
from datetime import datetime

CAMINHO_BANCO = "banco.db"


def conectar() -> sqlite3.Connection:
    """Abre e retorna uma conexão com o banco SQLite."""
    conexao = sqlite3.connect(CAMINHO_BANCO)
    conexao.row_factory = sqlite3.Row  # Permite acessar colunas por nome
    return conexao


def criar_tabelas():
    """Cria as tabelas necessárias se ainda não existirem."""
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS historico_buscas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            palavra_chave TEXT NOT NULL,
            filtros_json TEXT,
            total_encontrado INTEGER,
            total_analisado INTEGER,
            criado_em TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS licitacoes_analisadas (
            id TEXT PRIMARY KEY,
            licitacao_json TEXT NOT NULL,
            analise_json TEXT NOT NULL,
            relevancia_pre_filtro INTEGER,
            analisada_em TEXT NOT NULL,
            busca_id INTEGER,
            FOREIGN KEY (busca_id) REFERENCES historico_buscas(id)
        )
    """)

    conexao.commit()
    conexao.close()


def salvar_busca(palavra_chave: str, filtros: dict, total_encontrado: int, total_analisado: int) -> int:
    """Salva um registro de busca e retorna o ID gerado."""
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        INSERT INTO historico_buscas (palavra_chave, filtros_json, total_encontrado, total_analisado, criado_em)
        VALUES (?, ?, ?, ?, ?)
    """, (
        palavra_chave,
        json.dumps(filtros, ensure_ascii=False),
        total_encontrado,
        total_analisado,
        datetime.now().isoformat(),
    ))

    busca_id = cursor.lastrowid
    conexao.commit()
    conexao.close()
    return busca_id


def salvar_licitacao_analisada(licitacao_analisada, busca_id: int):
    """Salva uma licitação com sua análise de IA no banco."""
    from dataclasses import asdict

    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        INSERT OR REPLACE INTO licitacoes_analisadas
        (id, licitacao_json, analise_json, relevancia_pre_filtro, analisada_em, busca_id)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        licitacao_analisada.licitacao.id,
        json.dumps(asdict(licitacao_analisada.licitacao), ensure_ascii=False),
        json.dumps(asdict(licitacao_analisada.analise), ensure_ascii=False),
        licitacao_analisada.relevancia_pre_filtro,
        licitacao_analisada.analisada_em,
        busca_id,
    ))

    conexao.commit()
    conexao.close()


def buscar_historico(limite: int = 20) -> list[dict]:
    """Retorna as últimas buscas realizadas com seus totais."""
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT palavra_chave, total_encontrado, total_analisado, criado_em
        FROM historico_buscas
        ORDER BY criado_em DESC
        LIMIT ?
    """, (limite,))

    linhas = cursor.fetchall()
    conexao.close()

    return [dict(linha) for linha in linhas]


def buscar_licitacoes_salvas(limite: int = 50) -> list[dict]:
    """Retorna as licitações analisadas mais recentes."""
    conexao = conectar()
    cursor = conexao.cursor()

    cursor.execute("""
        SELECT licitacao_json, analise_json, relevancia_pre_filtro, analisada_em
        FROM licitacoes_analisadas
        ORDER BY analisada_em DESC
        LIMIT ?
    """, (limite,))

    linhas = cursor.fetchall()
    conexao.close()

    resultado = []
    for linha in linhas:
        resultado.append({
            "licitacao": json.loads(linha["licitacao_json"]),
            "analise": json.loads(linha["analise_json"]),
            "relevancia_pre_filtro": linha["relevancia_pre_filtro"],
            "analisada_em": linha["analisada_em"],
        })

    return resultado


def limpar_historico():
    """Remove todos os registros de buscas e licitações salvas no banco."""
    conexao = conectar()
    cursor = conexao.cursor()
    cursor.execute("DELETE FROM licitacoes_analisadas")
    cursor.execute("DELETE FROM historico_buscas")
    conexao.commit()
    conexao.close()

