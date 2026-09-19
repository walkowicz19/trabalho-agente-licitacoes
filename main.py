"""
Ponto de entrada do Agente de Licitações — TechBridge Brasil.
Inicia o servidor FastAPI e serve o frontend estático.
"""

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from api.rotas import roteador

# Inicializa o aplicativo FastAPI
app = FastAPI(
    title="Agente de Licitações — TechBridge Brasil",
    description="Busca, filtra e analisa licitações públicas do PNCP usando IA.",
    version="1.0.0",
)

# Registra as rotas da API
app.include_router(roteador, prefix="/api")

# Serve os arquivos estáticos do frontend (HTML, CSS, JS)
app.mount("/static", StaticFiles(directory="frontend"), name="static")


@app.get("/", include_in_schema=False)
def pagina_inicial():
    """Retorna a página principal do dashboard."""
    return FileResponse("frontend/index.html")
