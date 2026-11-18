"""
Popula o banco oliverflow_db com dados iniciais de teste.

Uso:
    python seed.py           -> cria o banco/tabelas e insere os dados se estiver vazio
    python seed.py --reset   -> APAGA todas as tabelas e recria do zero

Credenciais criadas:
    Admin     -> login: jefferson  | senha: Oliver@2026
    Atendente -> login: atendente  | senha: Atende@2026
"""
import sys
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from sqlalchemy.engine import make_url

from app import app
from models import (STATUS_AGENDADO, STATUS_CONCLUIDO, STATUS_EM_ATENDIMENTO,
                    STATUS_PRONTO, Agendamento, Pagamento, Pet, Servico, Tutor,
                    Usuario, db)


def garantir_banco_mysql():
    """Cria o database oliverflow_db no MySQL caso ainda nao exista."""
    url = make_url(app.config["SQLALCHEMY_DATABASE_URI"])
    if not url.drivername.startswith("mysql"):
        return
    import pymysql
    conn = pymysql.connect(host=url.host or "localhost", port=url.port or 3306,
                           user=url.username or "root", password=url.password or "")
    try:
        with conn.cursor() as cur:
            cur.execute(f"CREATE DATABASE IF NOT EXISTS `{url.database}` "
                        f"CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci")
        conn.commit()
    finally:
        conn.close()
    print(f"[ok] Banco '{url.database}' disponivel em {url.host}:{url.port or 3306}")


def popular():
    hoje = date.today()

    # --- Usuarios ---------------------------------------------------------
    jefferson = Usuario(nome="Jefferson S. Oliveira", login="jefferson", perfil="Admin", ativo=True)
    jefferson.set_senha("Oliver@2026")
    atendente = Usuario(nome="Bruna Martins", login="atendente", perfil="Atendente", ativo=True)
    atendente.set_senha("Atende@2026")
    db.session.add_all([jefferson, atendente])

    # --- Servicos (5 servicos do Pet Shop Oliver's) -------------------------
    banho = Servico(nome="Banho", duracao_min=60, valor=Decimal("55.00"))
    tosa_hig = Servico(nome="Tosa Higiênica", duracao_min=45, valor=Decimal("35.00"))
    tosa_geral = Servico(nome="Tosa Geral", duracao_min=90, valor=Decimal("80.00"))
    terapia = Servico(nome="Terapia", duracao_min=60, valor=Decimal("70.00"))
    # A Diaria de Creche ocupa a grade apenas no horario de recepcao/check-in.
    creche = Servico(nome="Diária de Creche", duracao_min=30, valor=Decimal("90.00"))
    db.session.add_all([banho, tosa_hig, tosa_geral, terapia, creche])

    # --- Tutores e pets ----------------------------------------------------
    dados = [
        ("Mariana Costa", "(11) 99999-1111", [
            ("Thor", "Grande", "Golden Retriever", "Adora água; precisa de hidratação regular na pelagem."),
            ("Luna", "Pequeno", "Shih Tzu", "Sensível ao barulho do secador potente."),
        ]),
        ("Ana Beatriz Rocha", "(11) 99999-2222", [("Pipoca", "Pequeno", "Poodle", None)]),
        ("Lucas Ferraz", "(11) 99999-3333", [("Rex", "Grande", "Pastor Alemão", "Usar focinheira no corte de unhas.")]),
        ("Rafael Lima", "(11) 99999-4444", [("Bolinha", "Medio", "SRD", "Alergia a shampoo com perfume.")]),
        ("Camila Duarte", "(11) 99999-5555", [("Mel", "Medio", "Beagle", None)]),
        ("Paula Nogueira", "(11) 99999-6666", [("Simba", "Medio", "Chow Chow", "Agitado no banho; manejo com calma.")]),
    ]
    pets = {}
    for nome, tel, lista in dados:
        t = Tutor(nome=nome, telefone=tel)
        db.session.add(t)
        db.session.flush()
        for pnome, porte, raca, obs in lista:
            p = Pet(nome=pnome, porte=porte, raca=raca, observacoes=obs, FK_TUTOR_id_tutor=t.id_tutor)
            db.session.add(p)
            pets[pnome] = p
    db.session.flush()

    def agendar(dia, hh, mm, pet, servico, status=STATUS_AGENDADO, forma=None, operador=None):
        ag = Agendamento(data=dia, hora_inicio=time(hh, mm), status=status, valor_cobrado=servico.valor,
                         FK_PET_id_pet=pet.id_pet, FK_SERVICO_id_servico=servico.id_servico)
        db.session.add(ag)
        db.session.flush()
        if status == STATUS_CONCLUIDO:
            entrega = datetime.combine(dia, time(hh, mm)) + timedelta(minutes=servico.duracao_min + 15)
            ag.data_hora_entrega = entrega
            db.session.add(Pagamento(forma_pagamento=forma or "PIX", valor_pago=servico.valor, data_hora=entrega,
                                     FK_AGENDAMENTO_id_agendamento=ag.id_agendamento,
                                     FK_USUARIO_id_usuario=(operador or atendente).id_usuario))
        return ag

    # --- Agendamentos de HOJE (sem choque de horario) -----------------------
    agendar(hoje, 8, 0, pets["Bolinha"], banho, STATUS_CONCLUIDO, "Dinheiro")
    agendar(hoje, 9, 0, pets["Pipoca"], tosa_hig, STATUS_PRONTO)
    agendar(hoje, 10, 0, pets["Thor"], banho, STATUS_EM_ATENDIMENTO)
    agendar(hoje, 11, 0, pets["Mel"], tosa_geral)
    agendar(hoje, 13, 0, pets["Luna"], terapia)
    agendar(hoje, 14, 30, pets["Simba"], banho)
    agendar(hoje, 16, 0, pets["Rex"], creche)

    # --- Proximos dias da semana -------------------------------------------
    for delta, itens in {1: [(9, 0, "Rex", banho), (10, 30, "Luna", tosa_hig)],
                         2: [(9, 30, "Thor", tosa_geral), (14, 0, "Pipoca", banho)],
                         3: [(8, 30, "Simba", terapia)]}.items():
        for hh, mm, pnome, serv in itens:
            agendar(hoje + timedelta(days=delta), hh, mm, pets[pnome], serv)

    # --- Historico concluido (dias anteriores) -------------------------------
    historico = [
        (1, 9, 0, "Thor", banho, "PIX"), (1, 11, 0, "Luna", tosa_geral, "Credito"),
        (2, 10, 0, "Rex", banho, "Debito"), (3, 14, 0, "Pipoca", tosa_hig, "PIX"),
        (5, 9, 0, "Mel", banho, "Dinheiro"), (7, 15, 0, "Simba", terapia, "Credito"),
        (9, 8, 30, "Thor", tosa_hig, "PIX"), (12, 10, 0, "Bolinha", tosa_geral, "Debito"),
        (16, 13, 0, "Luna", banho, "PIX"), (21, 9, 30, "Rex", creche, "Dinheiro"),
    ]
    for delta, hh, mm, pnome, serv, forma in historico:
        agendar(hoje - timedelta(days=delta), hh, mm, pets[pnome], serv, STATUS_CONCLUIDO, forma,
                jefferson if delta % 2 else atendente)

    db.session.commit()


def main():
    reset = "--reset" in sys.argv
    garantir_banco_mysql()
    with app.app_context():
        if reset:
            db.drop_all()
            print("[ok] Tabelas antigas removidas")
        db.create_all()
        print("[ok] Tabelas USUARIO, TUTOR, PET, SERVICO, AGENDAMENTO e PAGAMENTO verificadas/criadas")
        if Usuario.query.first():
            print("[i] O banco ja possui dados. Use 'python seed.py --reset' para recriar do zero.")
            return
        popular()
        print("[ok] Dados iniciais inseridos.")
        print("     Admin     -> login: jefferson | senha: Oliver@2026")
        print("     Atendente -> login: atendente | senha: Atende@2026")


if __name__ == "__main__":
    main()
