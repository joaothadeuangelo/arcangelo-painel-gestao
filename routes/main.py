from flask import Blueprint, render_template, session, g, request, jsonify
from flask_login import login_required, current_user
from datetime import datetime, timezone
from models import Usuario
from models import Modulo

# Cria o Blueprint
main_bp = Blueprint('main', __name__)

# ----------------------------------------------------------------
# ROTA PAINEL PRINCIPAL (ATUALIZADA)
# ----------------------------------------------------------------
@main_bp.route('/painel')
@main_bp.route('/')
@login_required
def home():
    # 1. Busca dados do Usuário (Sua lógica original)
    usuario_id = session.get('usuario_id')
    usuario = g.db.query(Usuario).filter_by(id=usuario_id).first()

    # 2. Lógica de Tempo Restante (Sua lógica original preservada)
    tempo_restante = None
    if usuario and usuario.validade:
        agora = datetime.now(timezone.utc)
        
        if usuario.validade.tzinfo:
             validade_aware = usuario.validade
        else:
             validade_aware = usuario.validade.replace(tzinfo=timezone.utc)

        if validade_aware > agora:
            diff = validade_aware - agora
            dias = diff.days
            horas, rem = divmod(diff.seconds, 3600)
            minutos, _ = divmod(rem, 60)
            tempo_restante = f"{dias}d {horas}h {minutos}m"
        else:
            tempo_restante = "Expirado"

    # 3. NOVO: Busca os Módulos no Banco de Dados
    # Ordenamos pelo campo 'ordem' para você controlar a posição no banco
    modulos = g.db.query(Modulo).order_by(Modulo.ordem).all()

    # Retorna tudo para o template
    return render_template(
        'index.html',
        usuario=usuario,
        tempo_restante=tempo_restante,
        modulos=modulos  # <--- Enviando a lista nova para o HTML
    )

# ----------------------------------------------------------------
# NOVA ROTA: ALTERAR STATUS DO MÓDULO (SOMENTE ADMIN)
# ----------------------------------------------------------------
@main_bp.route('/admin/toggle-modulo/<int:modulo_id>', methods=['POST'])
@login_required
def toggle_modulo(modulo_id):
    # Verifica se é admin mesmo
    if not current_user.admin:
        return jsonify({'success': False, 'error': 'Acesso negado.'}), 403
    
    # Busca o módulo
    modulo = g.db.get(Modulo, modulo_id)
    if not modulo:
        return jsonify({'success': False, 'error': 'Módulo não encontrado.'}), 404
        
    # Inverte o status: Se 'online' vira 'manutencao', senão vira 'online'
    novo_status = 'manutencao' if modulo.status == 'online' else 'online'
    modulo.status = novo_status
    
    try:
        g.db.commit()
        return jsonify({'success': True, 'novo_status': novo_status})
    except Exception as e:
        g.db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500
    
# ---- ROTA ERRO 404 ---
@main_bp.app_errorhandler(404)  # <--- USE O NOME DO BLUEPRINT (main_bp)
def page_not_found(e):
    return render_template('404.html'), 404