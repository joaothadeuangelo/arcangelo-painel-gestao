from database import engine, Base, SessionLocal
from werkzeug.security import generate_password_hash
from models import Usuario, Veiculo, LogAuditoria, CadastroMotorista
import os

print("⏳ Conectando ao Supabase via database.py...")

# 1. Cria as tabelas (Se não existirem)
Base.metadata.create_all(engine)
print("✅ Tabelas verificadas!")

# 2. Gerencia o Admin
session = SessionLocal()
try:
    email_admin = 'admin@admin'
    senha_padrao = os.getenv('ADMIN_DEFAULT_PASSWORD')

    if not senha_padrao:
        raise ValueError("ADMIN_DEFAULT_PASSWORD não definida no ambiente.")
    
    admin = session.query(Usuario).filter_by(email=email_admin).first()
    
    if not admin:
        print("👤 Criando Admin Novo...")
        novo_admin = Usuario(
            nome='Admin Supremo',
            email=email_admin,
            senha_hash=generate_password_hash(senha_padrao),
            admin=True,
            pode_cadastrar=True,
            pode_editar=True,
            pode_excluir=True,
            status='aprovado'
        )
        session.add(novo_admin)
        print(f"✅ Usuário criado: {email_admin} / senha via ADMIN_DEFAULT_PASSWORD")
    else:
        # --- AQUI ESTÁ O PULO DO GATO 🐱 ---
        print("👤 Admin encontrado! Forçando atualização da senha...")
        admin.senha_hash = generate_password_hash(senha_padrao)
        admin.admin = True # Garante que é admin
        admin.status = 'aprovado' # Garante que está aprovado
        print("🔄 Senha atualizada via ADMIN_DEFAULT_PASSWORD")

    session.commit()

except Exception as e:
    print(f"❌ Erro: {e}")
    session.rollback()
finally:
    session.close()