import cloudinary.uploader
from datetime import datetime
from flask import Blueprint, render_template, request, redirect, url_for, flash, session, g, current_app, jsonify
from werkzeug.utils import secure_filename

# Imports do Projeto
from models import Veiculo
from decorators import cadastro_required, edicao_required, exclusao_required
from utils import registrar_log

# Define o Blueprint para veículos
veiculos_bp = Blueprint('veiculos', __name__)

# -----------------------------------------------------
# Rota para EXIBIR o formulário de cadastro de veículos
# -----------------------------------------------------
@veiculos_bp.route('/cadastro')
@cadastro_required
def cadastro():
    return render_template('cadastro.html')


# -----------------------------------------------------
# ROTA para CADASTRAR UM NOVO VEÍCULO
# -----------------------------------------------------
@veiculos_bp.route('/cadastrar', methods=['POST'])
@cadastro_required
def cadastrar():
    # Captura os dados do formulário
    modelo = request.form['modelo'].strip()
    renavam = request.form['renavam'].strip()
    cpf = request.form['cpf'].strip()
    ano = request.form.get('ano', '').strip()
    cor = request.form.get('cor', '').strip().upper()
    arquivo = request.files.get('arquivo')

    # Validação para RENAVAM
    if not renavam.isdigit() or len(renavam) != 11:
        flash('❌ RENAVAM inválido. Deve conter exatamente 11 números.')
        return redirect(url_for('veiculos.cadastro'))

    # Validação para CPF/CNPJ
    if not cpf.isdigit() or len(cpf) not in [11, 14]:
        flash('❌ CPF/CNPJ inválido. O CPF deve conter 11 números e o CNPJ, 14.')
        return redirect(url_for('veiculos.cadastro'))

    url_arquivo = None

    # Processamento de Upload (Cloudinary)
    if arquivo and arquivo.filename:
        filename = secure_filename(arquivo.filename)
        extensao = filename.rsplit('.', 1)[-1].lower()

        if extensao not in ['pdf', 'txt']:
            flash('Formato de arquivo não permitido. Use PDF ou TXT.')
            return redirect(url_for('veiculos.cadastro'))

        try:
            # Gerando Public ID único
            public_id = f"{modelo}_{int(datetime.now().timestamp())}"
            
            upload_result = cloudinary.uploader.upload(
                arquivo,
                resource_type="auto",
                folder="crlv_veiculos",
                public_id=public_id
            )
            url_arquivo = upload_result.get('secure_url')

        except Exception as e:
            flash(f'Erro ao enviar arquivo: {str(e)}')
            return redirect(url_for('veiculos.cadastro'))

    # Insere o novo veículo no banco de dados
    try:
        veiculo_existente = g.db.query(Veiculo).filter_by(renavam=renavam).first()
        if veiculo_existente:
            flash('❌ Já existe um veículo cadastrado com esse RENAVAM.')
            return redirect(url_for('veiculos.cadastro'))

        novo_veiculo = Veiculo(
            modelo=modelo,
            renavam=renavam,
            cpf=cpf,
            ano=int(ano) if ano.isdigit() else None,
            cor=cor if cor else None,
            arquivo_crlv=url_arquivo
        )
        g.db.add(novo_veiculo)
        g.db.commit()

        # REGISTRO DE AUDITORIA
        registrar_log(
            session['usuario_id'],
            "Cadastro de veículo",
            f"Modelo: {modelo}, RENAVAM: {renavam}"
        )

        flash('Veículo cadastrado com sucesso!')
        modelo_veiculo = novo_veiculo.modelo

    except Exception as e:
        g.db.rollback()
        flash(f'Erro ao cadastrar veículo: {str(e)}')
        return redirect(url_for('veiculos.cadastro'))

    # Redireciona para a busca no blueprint de CONSULTAS
    return redirect(url_for('consultas.buscar', modelo=modelo_veiculo))


# ------------------------------------------------------------------
# ROTA PARA EDITAR UM VEÍCULO (COM LÓGICA CLOUDINARY)
# ------------------------------------------------------------------
@veiculos_bp.route('/veiculos/editar/<int:id>', methods=['GET', 'POST'])
@edicao_required
def editar_veiculo(id):
    veiculo = g.db.query(Veiculo).filter_by(id=id).first()
    if not veiculo:
        flash('Veículo não encontrado!', 'error')
        return redirect(url_for('main.home'))

    if request.method == 'POST':
        try:
            # --- Atualização dos dados de texto ---
            veiculo.modelo = request.form['modelo'].strip()
            veiculo.renavam = request.form['renavam'].strip()
            veiculo.cpf = request.form['cpf'].strip()
            ano_str = request.form.get('ano', '').strip()
            veiculo.ano = int(ano_str) if ano_str.isdigit() else None
            cor_str = request.form.get('cor', '').strip().upper()
            veiculo.cor = cor_str if cor_str else None

            # --- LÓGICA DE GERENCIAMENTO DE ARQUIVO CLOUDINARY ---

            # 1. Lógica para REMOVER o arquivo
            if 'remover_arquivo' in request.form and veiculo.arquivo_crlv:
                try:
                    # Extrai o public_id para deleção
                    public_id_com_pasta = "crlv_veiculos/" + veiculo.arquivo_crlv.split('/')[-1].rsplit('.', 1)[0]
                    cloudinary.uploader.destroy(public_id_com_pasta, resource_type="raw")
                    veiculo.arquivo_crlv = None
                    flash('Anexo removido com sucesso.', 'info')
                except Exception as e:
                    current_app.logger.error(f"Erro ao remover arquivo do Cloudinary: {e}")

            # 2. Lógica para ADICIONAR ou SUBSTITUIR o arquivo
            novo_arquivo = request.files.get('arquivo_crlv')
            if novo_arquivo and novo_arquivo.filename != '':
                # Apaga o arquivo antigo, se existir, antes de subir o novo
                if veiculo.arquivo_crlv:
                    try:
                        public_id_com_pasta = "crlv_veiculos/" + veiculo.arquivo_crlv.split('/')[-1].rsplit('.', 1)[0]
                        cloudinary.uploader.destroy(public_id_com_pasta, resource_type="raw")
                    except Exception as e:
                        current_app.logger.error(f"Erro ao substituir arquivo antigo no Cloudinary: {e}")

                # Processamento do novo upload
                try:
                    filename = secure_filename(novo_arquivo.filename)
                    timestamp = int(datetime.now().timestamp())
                    public_id = f"{filename.rsplit('.', 1)[0]}_{timestamp}"
                    
                    upload_result = cloudinary.uploader.upload(
                        novo_arquivo,
                        resource_type="raw",
                        folder="crlv_veiculos",
                        public_id=public_id
                    )
                    veiculo.arquivo_crlv = upload_result.get('secure_url')
                    flash('Novo anexo salvo com sucesso.', 'info')
                except Exception as e:
                    flash(f'Erro ao enviar novo arquivo para o Cloudinary: {str(e)}', 'error')
                    return redirect(url_for('veiculos.editar_veiculo', id=id))
            
            g.db.commit()

            # REGISTRO DE AUDITORIA
            registrar_log(
                usuario_id=session['usuario_id'],
                acao="Edição de veículo",
                detalhes=f"Modelo: {veiculo.modelo}, RENAVAM: {veiculo.renavam}"
            )

            flash('✅ Veículo atualizado com sucesso!')
            modelo_anterior = request.form.get('modelo_anterior', '')
            # Redireciona para a busca no blueprint de consultas
            return redirect(url_for('consultas.buscar', modelo=modelo_anterior))

        except Exception as e:
            g.db.rollback()
            flash(f'Ocorreu um erro ao atualizar o veículo: {e}', 'error')
            return redirect(url_for('veiculos.editar_veiculo', id=id))

    modelo_anterior = request.args.get('modelo_anterior', '')
    return render_template('editar_veiculo.html', veiculo=veiculo, modelo_anterior=modelo_anterior)


# -----------------------------------------------------
# ROTA PARA EXCLUIR UM VEÍCULO (RETORNA JSON)
# -----------------------------------------------------
@veiculos_bp.route('/veiculos/excluir/<int:id>', methods=['POST'])
@exclusao_required
def excluir_veiculo(id):
    veiculo = g.db.query(Veiculo).filter_by(id=id).first()
    
    if veiculo:
        # 1. Remove arquivo do Cloudinary, se existir
        if veiculo.arquivo_crlv:
            try:
                # Extrai o public_id da URL para poder apagar no Cloudinary
                # Ex: https://.../crlv_veiculos/arquivo.pdf -> crlv_veiculos/arquivo
                public_id_com_pasta = "crlv_veiculos/" + veiculo.arquivo_crlv.split('/')[-1].rsplit('.', 1)[0]
                cloudinary.uploader.destroy(public_id_com_pasta, resource_type="raw")
            except Exception as e:
                current_app.logger.error(f"Erro ao excluir arquivo do Cloudinary: {e}")

        # Armazena dados para o log de auditoria antes de apagar
        modelo = veiculo.modelo
        renavam = veiculo.renavam
        
        # 2. Remove do Banco de Dados
        g.db.delete(veiculo)
        g.db.commit()

        # 3. Log de exclusão
        registrar_log(
            usuario_id=session['usuario_id'],
            acao="Exclusão de veículo",
            detalhes=f"Modelo: {modelo}, RENAVAM: {renavam}"
        )
        
        # Retorna sucesso em JSON para o Frontend atualizar a tela sem recarregar
        return jsonify({'success': True, 'message': 'Veículo excluído com sucesso!'})
    
    else:
        return jsonify({'success': False, 'message': 'Veículo não encontrado.'}), 404


# --------------------------------------------
# Rota AJAX verificação de RENAVAM em tempo real
# --------------------------------------------
@veiculos_bp.route('/verificar-renavam', methods=['POST'])
def verificar_renavam():
    # Obtém dados do JSON enviado pelo JavaScript
    renavam = request.json.get('renavam', '').strip()

    if not renavam:
        return jsonify({'existe': False}), 400

    # Verifica no banco se já existe
    veiculo = g.db.query(Veiculo).filter_by(renavam=renavam).first()

    return jsonify({'existe': bool(veiculo)})

# -----------------------------------------------------
# ROTA PARA CONTADOR DE CLIQUES EM VEÍCULOS
# -----------------------------------------------------
@veiculos_bp.route('/incrementar_uso/<int:veiculo_id>', methods=['POST'])
# @login_required <-- Se quiser proteger, descomente
def incrementar_uso(veiculo_id):
    try:
        veiculo = g.db.query(Veiculo).get(veiculo_id)
        if not veiculo:
            return jsonify({'success': False, 'error': 'Veículo não encontrado'}), 404
        
        # Incrementa o contador
        veiculo.contador_uso += 1
        g.db.commit()
        
        return jsonify({
            'success': True, 
            'novo_contador': veiculo.contador_uso,
            'veiculo_id': veiculo.id
        })
    except Exception as e:
        g.db.rollback()
        return jsonify({'success': False, 'error': str(e)}), 500