"""
Configuracoes do OliverFlow.

Todos os valores podem ser sobrescritos por variaveis de ambiente, o que evita
deixar credenciais fixas no codigo em producao (ISO 27002 - controle de acesso
e gestao de segredos).
"""
import os
from datetime import timedelta

# --- Conexao MySQL (XAMPP / MySQL Server local, porta 3306) ---------------
MYSQL_USER = os.environ.get("MYSQL_USER", "root")
MYSQL_PASSWORD = os.environ.get("MYSQL_PASSWORD", "")  # XAMPP: root sem senha
MYSQL_HOST = os.environ.get("MYSQL_HOST", "localhost")
MYSQL_PORT = int(os.environ.get("MYSQL_PORT", "3306"))
MYSQL_DB = os.environ.get("MYSQL_DB", "oliverflow_db")


class Config:
    # Chave usada para assinar o cookie de sessao. Em producao defina a
    # variavel de ambiente SECRET_KEY com um valor longo e aleatorio.
    SECRET_KEY = os.environ.get("SECRET_KEY", "oliverflow-dev-troque-esta-chave")

    SQLALCHEMY_DATABASE_URI = os.environ.get(
        "DATABASE_URL",
        f"mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}?charset=utf8mb4",
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    # Sessao segura
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    PERMANENT_SESSION_LIFETIME = timedelta(hours=10)  # um turno de trabalho

    # Politica de bloqueio de login (RF02 / ISO 27002)
    MAX_TENTATIVAS_LOGIN = 5
    MINUTOS_BLOQUEIO = 15

    # Expediente usado na grade de horarios (RF10/RF11)
    HORA_ABERTURA = 8   # 08:00
    HORA_FECHAMENTO = 18  # 18:00
    INTERVALO_GRADE_MIN = 30
