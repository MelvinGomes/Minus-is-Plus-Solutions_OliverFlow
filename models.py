"""
Modelos SQLAlchemy do OliverFlow.

Reflete exatamente as 6 tabelas do Dicionario de Dados do projeto:
USUARIO, TUTOR, PET, SERVICO, AGENDAMENTO e PAGAMENTO.
"""
from datetime import datetime, timedelta

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import CheckConstraint, text
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()

# Valores de dominio (mantidos exatamente como gravados no banco)
PERFIS = ("Admin", "Atendente")
PORTES = ("Pequeno", "Medio", "Grande")
STATUS_AGENDADO = "Agendado"
STATUS_EM_ATENDIMENTO = "Em Atendimento"
STATUS_PRONTO = "Pronto para Retirada"
STATUS_CONCLUIDO = "Concluido"
STATUS_CANCELADO = "Cancelado"
STATUS = (STATUS_AGENDADO, STATUS_EM_ATENDIMENTO, STATUS_PRONTO, STATUS_CONCLUIDO, STATUS_CANCELADO)
STATUS_ATIVOS = (STATUS_AGENDADO, STATUS_EM_ATENDIMENTO, STATUS_PRONTO)
FORMAS_PAGAMENTO = ("PIX", "Debito", "Credito", "Dinheiro")


def _in(col, valores):
    return f"{col} IN (" + ", ".join(f"'{v}'" for v in valores) + ")"


# ---------------------------------------------------------------------------
# 3.1 USUARIO
# ---------------------------------------------------------------------------
class Usuario(db.Model):
    __tablename__ = "USUARIO"
    __table_args__ = (CheckConstraint(_in("perfil", PERFIS), name="ck_usuario_perfil"),)

    id_usuario = db.Column(db.Integer, primary_key=True, autoincrement=True, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    login = db.Column(db.String(50), nullable=False, unique=True)
    senha_hash = db.Column(db.String(255), nullable=False)
    perfil = db.Column(db.String(12), nullable=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True, server_default=text("1"))
    bloqueado_ate = db.Column(db.DateTime, nullable=True)

    pagamentos = db.relationship("Pagamento", back_populates="usuario", lazy="select")

    def set_senha(self, senha: str) -> None:
        self.senha_hash = generate_password_hash(senha)

    def verificar_senha(self, senha: str) -> bool:
        return check_password_hash(self.senha_hash, senha)

    @property
    def is_admin(self) -> bool:
        return self.perfil == "Admin"

    @property
    def esta_bloqueado(self) -> bool:
        return self.bloqueado_ate is not None and self.bloqueado_ate > datetime.now()

    def __repr__(self):
        return f"<Usuario {self.login} ({self.perfil})>"


# ---------------------------------------------------------------------------
# 3.2 TUTOR
# ---------------------------------------------------------------------------
class Tutor(db.Model):
    __tablename__ = "TUTOR"

    id_tutor = db.Column(db.Integer, primary_key=True, autoincrement=True, nullable=False)
    nome = db.Column(db.String(100), nullable=False)
    telefone = db.Column(db.String(15), nullable=False)

    pets = db.relationship("Pet", back_populates="tutor", lazy="select", order_by="Pet.nome")

    @property
    def telefone_limpo(self) -> str:
        return "".join(c for c in (self.telefone or "") if c.isdigit())

    def __repr__(self):
        return f"<Tutor {self.nome}>"


# ---------------------------------------------------------------------------
# 3.3 PET
# ---------------------------------------------------------------------------
class Pet(db.Model):
    __tablename__ = "PET"
    __table_args__ = (CheckConstraint(_in("porte", PORTES), name="ck_pet_porte"),)

    id_pet = db.Column(db.Integer, primary_key=True, autoincrement=True, nullable=False)
    nome = db.Column(db.String(60), nullable=False)
    porte = db.Column(db.String(10), nullable=False)
    raca = db.Column(db.String(60), nullable=True)
    observacoes = db.Column(db.Text, nullable=True)
    FK_TUTOR_id_tutor = db.Column(db.Integer, db.ForeignKey("TUTOR.id_tutor"), nullable=False)

    tutor = db.relationship("Tutor", back_populates="pets")
    agendamentos = db.relationship("Agendamento", back_populates="pet", lazy="select")

    def __repr__(self):
        return f"<Pet {self.nome}>"


# ---------------------------------------------------------------------------
# 3.4 SERVICO
# ---------------------------------------------------------------------------
class Servico(db.Model):
    __tablename__ = "SERVICO"
    __table_args__ = (CheckConstraint("duracao_min > 0", name="ck_servico_duracao"),)

    id_servico = db.Column(db.Integer, primary_key=True, autoincrement=True, nullable=False)
    nome = db.Column(db.String(60), nullable=False)
    duracao_min = db.Column(db.Integer, nullable=False)
    valor = db.Column(db.Numeric(10, 2), nullable=False)
    ativo = db.Column(db.Boolean, nullable=False, default=True, server_default=text("1"))

    agendamentos = db.relationship("Agendamento", back_populates="servico", lazy="select")

    def __repr__(self):
        return f"<Servico {self.nome}>"


# ---------------------------------------------------------------------------
# 3.5 AGENDAMENTO
# ---------------------------------------------------------------------------
class Agendamento(db.Model):
    __tablename__ = "AGENDAMENTO"
    __table_args__ = (CheckConstraint(_in("status", STATUS), name="ck_agendamento_status"),)

    id_agendamento = db.Column(db.Integer, primary_key=True, autoincrement=True, nullable=False)
    data = db.Column(db.Date, nullable=False, index=True)
    hora_inicio = db.Column(db.Time, nullable=False)
    status = db.Column(db.String(20), nullable=False, default=STATUS_AGENDADO,
                       server_default=text(f"'{STATUS_AGENDADO}'"))
    valor_cobrado = db.Column(db.Numeric(10, 2), nullable=False)
    data_hora_entrega = db.Column(db.DateTime, nullable=True)
    FK_PET_id_pet = db.Column(db.Integer, db.ForeignKey("PET.id_pet"), nullable=False)
    FK_SERVICO_id_servico = db.Column(db.Integer, db.ForeignKey("SERVICO.id_servico"), nullable=False)

    pet = db.relationship("Pet", back_populates="agendamentos")
    servico = db.relationship("Servico", back_populates="agendamentos")
    pagamentos = db.relationship("Pagamento", back_populates="agendamento", lazy="select")

    @property
    def inicio_dt(self) -> datetime:
        return datetime.combine(self.data, self.hora_inicio)

    @property
    def fim_dt(self) -> datetime:
        return self.inicio_dt + timedelta(minutes=self.servico.duracao_min)

    @property
    def pagamento(self):
        return self.pagamentos[0] if self.pagamentos else None

    def __repr__(self):
        return f"<Agendamento {self.id_agendamento} {self.data} {self.hora_inicio} {self.status}>"


# ---------------------------------------------------------------------------
# 3.6 PAGAMENTO
# ---------------------------------------------------------------------------
class Pagamento(db.Model):
    __tablename__ = "PAGAMENTO"
    __table_args__ = (CheckConstraint(_in("forma_pagamento", FORMAS_PAGAMENTO), name="ck_pagamento_forma"),)

    id_pagamento = db.Column(db.Integer, primary_key=True, autoincrement=True, nullable=False)
    forma_pagamento = db.Column(db.String(10), nullable=False)
    valor_pago = db.Column(db.Numeric(10, 2), nullable=False)
    data_hora = db.Column(db.DateTime, nullable=False, default=datetime.now,
                          server_default=db.func.current_timestamp())
    FK_AGENDAMENTO_id_agendamento = db.Column(db.Integer, db.ForeignKey("AGENDAMENTO.id_agendamento"), nullable=False)
    FK_USUARIO_id_usuario = db.Column(db.Integer, db.ForeignKey("USUARIO.id_usuario"), nullable=False)

    agendamento = db.relationship("Agendamento", back_populates="pagamentos")
    usuario = db.relationship("Usuario", back_populates="pagamentos")

    def __repr__(self):
        return f"<Pagamento {self.id_pagamento} {self.forma_pagamento} {self.valor_pago}>"
