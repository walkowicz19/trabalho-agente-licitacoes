"""
Pré-filtro de relevância baseado em sobreposição de palavras-chave.

Inspirado no conceito TF (Term Frequency), mas sem a complexidade do IDF.
Descarta licitações completamente fora do portfólio da empresa ANTES de
chamar o Gemini, economizando quota da API gratuita.

Por que não TF-IDF completo?
- Exigiria scikit-learn ou implementação complexa (quebraria KISS)
- A parte IDF requer um corpus de referência que não temos
- Falsos negativos por sinônimos são mais graves do que falsos positivos aqui
  (o Gemini dará score baixo para os que passarem sem fit real)
"""

import re


def _normalizar_texto(texto: str) -> str:
    """
    Converte o texto para minúsculas e remove pontuação.
    Mantém letras acentuadas do português.
    """
    texto_lower = texto.lower()
    texto_limpo = re.sub(r"[^a-záéíóúâêîôûãõàèìòùç\s]", " ", texto_lower)
    return texto_limpo


def calcular_relevancia(titulo: str, objeto: str, palavras_empresa: list[str]) -> int:
    """
    Conta quantas palavras-chave do portfólio da empresa
    aparecem no título ou no objeto da licitação.

    Retorna o número de correspondências encontradas (0 ou mais).
    """
    texto_completo = _normalizar_texto(f"{titulo} {objeto}")

    correspondencias = 0
    for palavra in palavras_empresa:
        if palavra.lower() in texto_completo:
            correspondencias += 1

    return correspondencias


def passou_no_filtro(titulo: str, objeto: str, palavras_empresa: list[str]) -> bool:
    """
    Retorna True se ao menos 1 palavra-chave do portfólio
    for encontrada no título ou objeto da licitação.

    Limiar 1 (não maior) é intencional:
    - Limiar alto cria falsos negativos ("suíte de produtividade" != "Microsoft 365")
    - O Gemini com temperature=0.1 faz a classificação refinada
    - Este filtro só descarta o óbvio: obras, fardamentos, merenda, etc.
    """
    return calcular_relevancia(titulo, objeto, palavras_empresa) >= 1
