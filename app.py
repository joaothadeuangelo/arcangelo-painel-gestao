import os
import logging
import time
from datetime import timedelta, datetime, timezone
from dotenv import load_dotenv

# Flask e Extensões
from flask import Flask, redirect, request, g, session, flash, url_for
from flask_session import Session
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_wtf.csrf import CSRFProtect
from flask_cors import CORS
from flask_login import LoginManager, logout_user, current_user
from werkzeug.middleware.proxy_fix import ProxyFix
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker
from flask import render_template

# Imports Locais
import cloudinary
from database import engine
from models import Base, Usuario, LogAuditoria, BuscaSemResultado

# Blueprints
from routes.auth import auth_bp
from routes.main import main_bp
from routes.admin import admin_bp
from routes.consultas import consultas_bp
from routes.veiculos import veiculos_bp

# Utilitários
from utils import formatar_horario_br, inject_now, verificar_criar_admin

# ==============================================================================
# INICIALIZAÇÃO
# ==============================================================================
load_dotenv()
app = Flask(__name__)

# Configurações de Log
logging.basicConfig(level=logging.INFO)
app.logger.info("🔥 Aplicação Flask iniciando...")

# ------------------------------------------------------------------------------
# 1. CORREÇÃO DE PROXY (CRUCIAL PARA RAILWAY)
# ------------------------------------------------------------------------------
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)

# Registro de Blueprints
app.register_blueprint(auth_bp)
app.register_blueprint(main_bp)
app.register_blueprint(admin_bp)
app.register_blueprint(consultas_bp)
app.register_blueprint(veiculos_bp)

# Filtros e Context Processors
app.template_filter('brtime')(formatar_horario_br)
app.context_processor(inject_now)

# Configurações
app.debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
app.config['SECRET_KEY'] = os.getenv('FLASK_SECRET_KEY') or os.urandom(24).hex()
app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=30)
app.config['SESSION_TYPE'] = 'filesystem' 
if not app.debug:
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

# Extensões
CORS(app)
csrf = CSRFProtect(app)
csrf.exempt('routes.consultas.api_consultar_placa')
csrf.exempt('routes.consultas.api_consultar_cpf')

Session(app)

# ------------------------------------------------------------------------------
# 2. CONFIGURAÇÃO DO LIMITER (TOLERANTE)
# ------------------------------------------------------------------------------
limiter = Limiter(
    get_remote_address, 
    app=app, 
    default_limits=["5000 per day", "100 per minute"], 
    storage_uri="memory://"
)

# Filtro para não contar arquivos estáticos no Limite (Evita bloqueio falso)
@limiter.request_filter
def exempt_static():
    return request.endpoint and (
        'static' in request.endpoint or 
        'get_resource' in request.endpoint
    )

# ==========================================
# BANCO DE DADOS
# ==========================================
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

try:
    Base.metadata.create_all(bind=engine)
    print("✅ Tabelas do banco verificadas.")
except Exception as e:
    app.logger.error(f"❌ Erro ao criar tabelas: {e}")

# ==========================================
# LOGIN MANAGER
# ==========================================
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'auth.login'
login_manager.login_message = "Faça login para acessar."
login_manager.login_message_category = "warning"

@login_manager.user_loader
def load_user(user_id):
    session_db = SessionLocal()
    try:
        return session_db.get(Usuario, int(user_id))
    except Exception:
        return None
    finally:
        session_db.close()

# ==========================================
# CLOUDINARY
# ==========================================
cloudinary.config(
    cloud_name=os.getenv("CLOUD_NAME"),
    api_key=os.getenv("API_KEY"),
    api_secret=os.getenv("API_SECRET")
)

# ==========================================
# HOOKS E SEGURANÇA GLOBAL
# ==========================================
@app.after_request
def aplicar_cabecalhos_de_seguranca(response):
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    return response

@app.before_request
def check_security_and_global_auth():
    # ==========================================================
    # 1. ESCUDO ANTI-GARGALO (Ignora arquivos estáticos NA HORA)
    # ==========================================================
    # Se o navegador estiver apenas pedindo CSS, JS, ou imagens, devolve e sai!
    if request.endpoint and ('static' in request.endpoint or 'favicon' in request.endpoint):
        return

    # A partir daqui, só rotas reais de HTML e API passam. Abre o banco:
    g.db = SessionLocal()
    g.demandas_pendentes_count = 0
    g.notificacao_usuarios_pendentes = False
    g.notificacao_novos_logs = False

    rotas_publicas = [
        'auth.login', 
        'auth.logout',
        'routes.consultas.api_consultar_placa',
        'routes.consultas.api_consultar_cpf'
    ]

    # ==========================================================
    # 2. ROTAS DE AUTENTICAÇÃO E APIs PÚBLICAS (Ignora verificações pesadas)
    # ==========================================================
    if request.endpoint in rotas_publicas:
        return # Deixa o auth.py (ou a API) fazer o trabalho sem pesar o banco

    # ==========================================================
    # 3. BLINDAGEM DE ROTAS INTERNAS E SESSÃO ZUMBI
    # ==========================================================
    if not current_user.is_authenticated:
        return redirect(url_for('auth.login'))

    try:
        user_db = g.db.get(Usuario, int(current_user.id))
        token_navegador = session.get('user_token')
        
        # Se token inválido -> Logout e Redireciona
        if user_db and user_db.session_token and user_db.session_token != token_navegador:
            logout_user()
            session.clear()
            flash("⚠️ Sessão expirada ou aberta em outro local.", "error")
            return redirect(url_for('auth.login'))
            
    except Exception as e:
        app.logger.error(f"Erro na verificação de sessão: {e}")

    # ==========================================================
    # 4. LÓGICA DE NOTIFICAÇÕES (Só roda em páginas internas e para Admin)
    # ==========================================================
    if session.get('admin') and 'usuario_id' in session:
        try:
            count = g.db.query(func.count(BuscaSemResultado.id)).filter(BuscaSemResultado.status == 'pendente').scalar()
            if count: g.demandas_pendentes_count = count
            
            if g.db.query(Usuario.id).filter(Usuario.status == 'pendente').first():
                g.notificacao_usuarios_pendentes = True
        except:
            pass

@app.teardown_request
def close_db_connection(exception=None):
    db = g.pop('db', None)
    if db is not None:
        db.close()

# ==========================================
# STARTUP
# ==========================================
if __name__ == '__main__':
    print("--- INICIALIZANDO SISTEMA ARCANGELO ---")
    verificar_criar_admin()
    print("--> Servidor Online em http://localhost:5000")
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)