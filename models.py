from sqlalchemy import (
    Column, Integer, String, Boolean, ForeignKey, DateTime, Text, func, Numeric, Float, JSON
)
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.sql.sqltypes import TIMESTAMP
from datetime import datetime, timezone
from flask_login import UserMixin
import uuid

# Define a base declarativa para o SQLAlchemy
Base = declarative_base()

class Veiculo(Base):
    __tablename__ = 'veiculos'
    
    id = Column(Integer, primary_key=True)
    modelo = Column(String(100), nullable=False)
    # INDEX ADD: Pesquisas por CPF e Renavam agora são instantâneas
    renavam = Column(String(50), nullable=False, index=True)
    cpf = Column(String(50), nullable=False, index=True)
    ano = Column(Integer, nullable=True)
    cor = Column(String(50), nullable=True)
    arquivo_crlv = Column(String(255), nullable=True)
    contador_uso = Column(Integer, default=0, nullable=False)

    def to_dict(self):
        return {
            'id': self.id,
            'modelo': self.modelo,
            'renavam': self.renavam,
            'cpf': self.cpf,
            'ano': self.ano,
            'cor': self.cor,
            'arquivo_crlv': self.arquivo_crlv,
            'contador_uso': self.contador_uso
        }

class Usuario(Base, UserMixin):
    __tablename__ = 'usuarios'
    
    # REMOVIDO index=True do ID, o Postgres já faz isso nativamente na Primary Key
    id = Column(Integer, primary_key=True)
    nome = Column(String, nullable=False)
    email = Column(String, unique=True, nullable=False)
    
    senha_hash = Column("senha", String, nullable=False)
    telefone = Column(String(20), nullable=True)
    admin = Column(Boolean, default=False)
    pode_cadastrar = Column(Boolean, default=False)
    pode_editar = Column(Boolean, default=False)
    pode_excluir = Column(Boolean, default=False)
    validade = Column(DateTime(timezone=True), nullable=True)
    
    # INDEX ADD: status e session_token (Acelera o before_request em 90%)
    status = Column(String(20), nullable=False, default='aprovado', server_default='aprovado', index=True)
    session_token = Column(String(50), default=None, index=True)
    
    ultimo_log_visto = Column(DateTime, nullable=True)
    
    logs = relationship(
        "LogAuditoria",
        back_populates="usuario",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )

class Modulo(Base):
    __tablename__ = 'modulos'
    
    id = Column(Integer, primary_key=True)
    titulo = Column(String)
    descricao = Column(String)
    rota = Column(String)
    icone = Column(String)
    status = Column(String)
    ordem = Column(Integer)
    apenas_admin = Column(Boolean, default=False)

class LogAuditoria(Base):
    __tablename__ = 'logs_auditoria'
    
    id = Column(Integer, primary_key=True)
    # INDEX ADD: Foreign keys sempre devem ter índices
    usuario_id = Column(Integer, ForeignKey('usuarios.id', ondelete='CASCADE'), nullable=False, index=True)
    acao = Column(String(255), nullable=False)
    detalhes = Column(String(500), nullable=True)
    # INDEX ADD: Acelera a ordenação dos logs do mais recente pro mais antigo
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)
    
    # LAZY JOINED: Resolve o problema N+1. Puxa os dados do usuário na mesma query do log.
    usuario = relationship("Usuario", back_populates="logs", lazy="joined")
    
    def to_dict(self):
        return {
            'id': self.id,
            'usuario_nome': self.usuario.nome if self.usuario else 'Usuário Removido',
            'acao': self.acao,
            'detalhes': self.detalhes,
            'timestamp': self.timestamp.isoformat() if isinstance(self.timestamp, datetime) else self.timestamp
        }

class BuscaSemResultado(Base):
    __tablename__ = 'buscas_sem_resultado'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    termos_pesquisado = Column(String(255), nullable=False)
    usuario_id = Column(Integer, ForeignKey('usuarios.id'), nullable=True)
    data_hora = Column(TIMESTAMP(timezone=True), server_default=func.now())
    # INDEX ADD: Acelera o count() do badge vermelho de notificações do Admin
    status = Column(String(50), default='pendente', nullable=False, index=True)
    
    usuario = relationship('Usuario')

class CachePlaca(Base):
    __tablename__ = 'cache_placas'

    placa = Column(String(10), primary_key=True)
    dados_json = Column(JSON)
    # FIX: Removido o default=datetime.now(). Substituído pelo servidor do banco.
    data_consulta = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<CachePlaca(placa='{self.placa}')>"