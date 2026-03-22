import os
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base
from dotenv import load_dotenv

# Carrega as variáveis de ambiente (do .env local ou do Railway)
load_dotenv()

# 1. URL DO SUPABASE (Buscando do arquivo .env por segurança)
SQLALCHEMY_DATABASE_URL = os.getenv("DATABASE_URL")

if not SQLALCHEMY_DATABASE_URL:
    raise ValueError("⚠️ A variável DATABASE_URL não foi encontrada. Verifique o .env ou o Railway.")

# 2. CONFIGURAÇÃO DA CONEXÃO (ENGINE) OTIMIZADA
engine = create_engine(
    SQLALCHEMY_DATABASE_URL,
    pool_pre_ping=True,      # Verifica se a conexão caiu antes de usar
    pool_size=10,            # Mantém 10 conexões abertas "na agulha" (super rápido)
    max_overflow=20,         # Se as 10 lotarem, permite abrir mais 20 de emergência
    pool_timeout=30,         # Espera no máximo 30s por uma conexão antes de dar erro
    pool_recycle=1800        # Recicla as conexões a cada 30 minutos para evitar timeout do Supabase
)

# 3. FÁBRICA DE SESSÕES
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# 4. BASE PARA OS MODELS
Base = declarative_base()