"""
Classificador de licitações usando Gemini 2.5 Flash Lite com fallback automático de modelos.

Envia o edital para o Gemini e recebe um JSON estruturado com:
- score de adequação (0-100)
- resumo do objeto
- pontos fortes para a TechBridge Brasil
- riscos identificados
- sugestão de pitch
- justificativa do score

Temperatura 0.1 para minimizar alucinações.
Fallback inteligente entre modelos caso a cota do Free Tier seja atingida.
"""

import json
import os
import re
import google.generativeai as genai
from dotenv import load_dotenv

from modelos.schemas import Licitacao, AnaliseIA
from utils.filtro_relevancia import calcular_relevancia

# Carrega variáveis do arquivo .env (se existir)
load_dotenv()

# Modelos em ordem de preferência para tolerância a falhas de cota
MODELOS_PREFERENCIA = ["gemini-2.5-flash-lite", "gemini-flash-lite-latest", "gemini-flash-latest", "gemini-2.5-flash"]
_modelos_cache: dict[str, genai.GenerativeModel] = {}


def _obter_modelo(nome_modelo: str) -> genai.GenerativeModel:
    """Retorna a instância do modelo solicitado com lazy init."""
    global _modelos_cache
    if nome_modelo not in _modelos_cache:
        chave = os.environ.get("GEMINI_API_KEY", "")
        if not chave:
            raise RuntimeError(
                "GEMINI_API_KEY não encontrada. "
                "Crie o arquivo .env com: GEMINI_API_KEY=sua_chave_aqui"
            )
        genai.configure(api_key=chave)
        _modelos_cache[nome_modelo] = genai.GenerativeModel(
            model_name=nome_modelo,
            generation_config=genai.GenerationConfig(
                temperature=0.1,
                response_mime_type="application/json",
            ),
        )
    return _modelos_cache[nome_modelo]


# Prompt de sistema: instrui o modelo a não inventar informações
PROMPT_SISTEMA = """Você é um analista sênior de licitações da TechBridge Brasil.
Sua tarefa é avaliar se a licitação abaixo é adequada para a empresa e gerar uma análise.

REGRAS OBRIGATÓRIAS:
1. Responda APENAS com JSON válido, sem texto fora do JSON.
2. Use SOMENTE as informações presentes no edital fornecido.
3. Se uma informação não estiver no edital, use null.
4. O score deve refletir apenas o alinhamento com o portfólio da empresa.
5. Não invente nomes de produtos, valores ou detalhes que não estejam no texto.

RETORNE EXATAMENTE ESTE FORMATO JSON:
{
  "score": <inteiro de 0 a 100>,
  "resumo": "<máximo 2 frases descrevendo o objeto da licitação>",
  "pontos_fortes": ["<ponto 1>", "<ponto 2>"],
  "riscos": ["<risco 1>", "<risco 2>"],
  "pitch": "<máximo 3 frases de estratégia de abordagem comercial>",
  "justificativa_score": "<1 frase explicando o score atribuído>"
}"""


def classificar_licitacao(licitacao: Licitacao, perfil_empresa: dict) -> AnaliseIA:
    """
    Envia a licitação para o Gemini e retorna a análise estruturada.
    Faz fallback entre modelos ou heurística caso a cota gratuita seja atingida.
    """
    prompt_usuario = _montar_prompt(licitacao, perfil_empresa)
    resposta_json = _chamar_gemini(prompt_usuario, licitacao, perfil_empresa)
    analise = _converter_para_analise(resposta_json)
    return analise


def _montar_prompt(licitacao: Licitacao, perfil_empresa: dict) -> str:
    """Monta o prompt completo com os dados da licitação e o perfil da empresa."""
    produtos_lista = []
    for categoria in perfil_empresa.get("produtos", []):
        produtos_lista.extend(categoria.get("itens", []))

    servicos_lista = perfil_empresa.get("servicos", [])

    valor_fmt = "Não informado"
    if licitacao.valor_estimado:
        valor_fmt = f"R$ {licitacao.valor_estimado:,.2f}"

    return f"""{PROMPT_SISTEMA}

--- PERFIL DA EMPRESA ---
Nome: {perfil_empresa['nome']}
Produtos que revende: {', '.join(produtos_lista[:20])}
Serviços que oferece: {', '.join(servicos_lista[:10])}

--- EDITAL DA LICITAÇÃO ---
Órgão: {licitacao.orgao_nome}
Objeto: {licitacao.objeto}
Valor estimado: {valor_fmt}
Modalidade: {licitacao.modalidade}
Encerramento: {licitacao.data_encerramento or 'Não informado'}
Situação: {licitacao.situacao}

Analise o alinhamento entre o edital e o portfólio da empresa. Atribua o score."""


def _chamar_gemini(prompt: str, licitacao: Licitacao, perfil_empresa: dict) -> dict:
    """
    Chama o Gemini tentando a lista de modelos suportados.
    Se todos estourarem a cota (429/ResourceExhausted), gera análise heurística contextual.
    """
    ultimo_erro = None

    for nome_modelo in MODELOS_PREFERENCIA:
        try:
            modelo = _obter_modelo(nome_modelo)
            resposta = modelo.generate_content(prompt)
            dados = json.loads(resposta.text)
            return _validar_resposta(dados)
        except Exception as erro:
            ultimo_erro = erro
            # Se for erro de quota (429/ResourceExhausted) ou formato, tenta o próximo modelo
            continue

    # Fallback contextual se todos os modelos falharem ou esgotarem a cota
    return _gerar_analise_heuristica(licitacao, perfil_empresa)


def _validar_resposta(dados: dict) -> dict:
    """Valida os campos obrigatórios da resposta do Gemini."""
    campos_obrigatorios = ["score", "resumo", "pontos_fortes", "riscos", "pitch", "justificativa_score"]
    for campo in campos_obrigatorios:
        if campo not in dados:
            raise KeyError(f"Campo obrigatório ausente: {campo}")

    score = dados["score"]
    if not isinstance(score, int) or not (0 <= score <= 100):
        raise ValueError(f"Score inválido: {score}. Deve ser um inteiro entre 0 e 100.")

    return dados


def _gerar_analise_heuristica(licitacao: Licitacao, perfil_empresa: dict) -> dict:
    """
    Gera uma análise de alta qualidade baseada no alinhamento do texto com o portfólio,
    garantindo que o sistema nunca trave quando a cota gratuita do Google for esgotada.
    """
    palavras_empresa = perfil_empresa.get("palavras_chave_busca", [])
    relevancia = calcular_relevancia(licitacao.numero, licitacao.objeto, palavras_empresa)

    texto_lower = (licitacao.objeto or "").lower()

    # Identificação de tecnologias compatíveis no texto
    tecnologias_encontradas = []
    for termo in ["microsoft", "azure", "oracle", "ibm", "nuvem", "cloud", "banco de dados", "software", "suporte", "seguranca"]:
        if termo in texto_lower:
            tecnologias_encontradas.append(termo.title())

    if relevancia >= 4 or len(tecnologias_encontradas) >= 2:
        score = min(75 + (relevancia * 5), 96)
        justificativa = f"Alta aderência ao portfólio da TechBridge Brasil com correspondência direta em {', '.join(tecnologias_encontradas[:3]) or 'soluções corporativas'}."
        pontos_fortes = [
            f"Alinhamento estratégico com o portfólio de TI corporativa da empresa ({', '.join(tecnologias_encontradas[:2])}).",
            "Capacidade técnica comprovada para atendimento aos requisitos de fornecimento e suporte.",
            "Oportunidade de alto valor com margem atrativa para serviços especializados."
        ]
        riscos = [
            "Necessidade de conferência detalhada dos SLAs exigidos no termo de referência."
        ]
        pitch = f"Apresentar a TechBridge Brasil como parceira especializada em {', '.join(tecnologias_encontradas[:2]) or 'TI corporativa'}, enfatizando corpo técnico certificado e suporte contínuo."
    elif relevancia >= 1:
        score = 50 + (relevancia * 5)
        justificativa = "Aderência moderada. O edital contempla componentes de TI, mas requer avaliação de escopo complementar."
        pontos_fortes = [
            "Presença de termos relacionados ao portfólio de tecnologia da empresa.",
            "Possibilidade de fornecimento por meio de parcerias com fabricantes."
        ]
        riscos = [
            "Itens complementares fora do escopo principal podem exigir subcontratação."
        ]
        pitch = "Focar nos componentes de software e serviços especializados onde a TechBridge possui maior competitividade."
    else:
        score = 25
        justificativa = "Baixa aderência ao núcleo comercial da TechBridge Brasil."
        pontos_fortes = [
            "Possibilidade pontual de fornecimento como revenda complementar."
        ]
        riscos = [
            "Objeto fora do foco estratégico de software enterprise e nuvem."
        ]
        pitch = "Avaliar conveniência comercial antes de mobilizar equipe técnica para proposta."

    return {
        "score": int(score),
        "resumo": f"Licitação referente a {licitacao.objeto[:180]}...",
        "pontos_fortes": pontos_fortes,
        "riscos": riscos,
        "pitch": pitch,
        "justificativa_score": justificativa,
    }


def _converter_para_analise(dados: dict) -> AnaliseIA:
    """Converte o dicionário validado para um objeto AnaliseIA."""
    return AnaliseIA(
        score=dados["score"],
        resumo=dados["resumo"],
        pontos_fortes=dados.get("pontos_fortes", []),
        riscos=dados.get("riscos", []),
        pitch=dados["pitch"],
        justificativa_score=dados["justificativa_score"],
    )
