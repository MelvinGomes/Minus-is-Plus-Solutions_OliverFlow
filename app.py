"""
OliverFlow - Sistema interno (backoffice) do Pet Shop Oliver's.

Ponto de entrada da aplicacao Flask: configuracao, seguranca, rotas e regras
de negocio (RF01 a RF19).
"""
import secrets
from datetime import date, datetime, time, timedelta
from decimal import Decimal, InvalidOperation
from functools import wraps
from urllib.parse import quote

from flask import (Flask, abort, flash, g, jsonify, redirect, render_template,
                   request, session, url_for)
from sqlalchemy import func, or_

from config import Config
from models import (FORMAS_PAGAMENTO, PERFIS, PORTES, STATUS_AGENDADO,
                    STATUS_ATIVOS, STATUS_CANCELADO, STATUS_CONCLUIDO,
                    STATUS_EM_ATENDIMENTO, STATUS_PRONTO, Agendamento,
                    Pagamento, Pet, Servico, Tutor, Usuario, db)

app = Flask(__name__)
app.config.from_object(Config)
db.init_app(app)

# ---------------------------------------------------------------------------
# Rotulos de exibicao (o banco guarda os valores sem acento, conforme o DD)
# ---------------------------------------------------------------------------
ROTULO_PORTE = {"Pequeno": "Pequeno", "Medio": "Médio", "Grande": "Grande"}
ROTULO_FORMA = {"PIX": "PIX", "Debito": "Débito", "Credito": "Crédito", "Dinheiro": "Dinheiro"}
# Status: cor (classe CSS) + icone + texto por extenso (NBR 17225 - 5.11.1)
STATUS_UI = {
    STATUS_AGENDADO: {"texto": "Agendado", "icone": "bi-clock", "classe": "status-agendado"},
    STATUS_EM_ATENDIMENTO: {"texto": "Em Atendimento", "icone": "bi-scissors", "classe": "status-atendimento"},
    STATUS_PRONTO: {"texto": "Pronto para Retirada", "icone": "bi-check-lg", "classe": "status-pronto"},
    STATUS_CONCLUIDO: {"texto": "Concluído", "icone": "bi-patch-check-fill", "classe": "status-concluido"},
    STATUS_CANCELADO: {"texto": "Cancelado", "icone": "bi-x-circle", "classe": "status-cancelado"},
}
# Fluxo da fila diaria (RF14). 'Concluido' so e atingido pela baixa de pagamento.
PROXIMO_STATUS = {
    STATUS_AGENDADO: STATUS_EM_ATENDIMENTO,
    STATUS_EM_ATENDIMENTO: STATUS_PRONTO,
}
DIAS_SEMANA = ["Segunda-feira", "Terça-feira", "Quarta-feira", "Quinta-feira", "Sexta-feira", "Sábado", "Domingo"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]


# ---------------------------------------------------------------------------
# Utilitarios
# ---------------------------------------------------------------------------
def moeda(valor) -> str:
    """Formata numero no padrao brasileiro: R$ 1.234,56."""
    valor = Decimal(valor or 0)
    texto = f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"R$ {texto}"


def data_extenso(d: date) -> str:
    return f"{DIAS_SEMANA[d.weekday()]}, {d.day} de {MESES[d.month - 1]} de {d.year}"


def duracao_texto(minutos: int) -> str:
    h, m = divmod(int(minutos), 60)
    if h and m:
        return f"{h}h{m:02d}"
    return f"{h}h" if h else f"{m}min"


def so_digitos(texto: str) -> str:
    return "".join(c for c in (texto or "") if c.isdigit())


def formatar_telefone(texto: str) -> str:
    d = so_digitos(texto)
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return d


def parse_decimal(texto, padrao=None):
    """Aceita '55', '55.5', '55,50' ou '1.234,56'. Retorna None se invalido."""
    if texto is None or str(texto).strip() == "":
        return padrao
    s = str(texto).strip().replace("R$", "").replace(" ", "")
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        valor = Decimal(s)
    except InvalidOperation:
        return None
    if not valor.is_finite() or valor > Decimal("99999999.99"):
        return None
    return valor.quantize(Decimal("0.01"))


def parse_data(texto, padrao=None):
    try:
        return datetime.strptime(texto, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return padrao


def parse_hora(texto):
    for fmt in ("%H:%M", "%H:%M:%S"):
        try:
            return datetime.strptime(texto, fmt).time()
        except (TypeError, ValueError):
            continue
    return None


def iniciais(nome: str) -> str:
    return (nome or "?").strip()[:1].upper()


def link_whatsapp(agendamento: Agendamento) -> str:
    """RF15 - link dinamico wa.me com a mensagem de 'pronto para retirada'."""
    tutor = agendamento.pet.tutor
    mensagem = (
        f"Olá, {tutor.nome}! O atendimento de {agendamento.servico.nome} do(a) "
        f"{agendamento.pet.nome} foi finalizado e ele(a) já está pronto(a) para "
        f"retirada no Pet Shop Oliver's."
    )
    return f"https://wa.me/55{tutor.telefone_limpo}?text={quote(mensagem)}"


def link_whatsapp_tutor(tutor: Tutor) -> str:
    return f"https://wa.me/55{tutor.telefone_limpo}?text={quote(f'Olá, {tutor.nome}! Aqui é do Pet Shop Oliver' + chr(39) + 's.')}"


def destino_seguro(padrao_endpoint="dashboard"):
    """Retorna para a pagina de origem apenas se for um caminho interno."""
    destino = request.form.get("next") or request.args.get("next")
    if destino and destino.startswith("/") and not destino.startswith("//"):
        return destino
    return url_for(padrao_endpoint)


app.jinja_env.globals.update(
    moeda=moeda, data_extenso=data_extenso, duracao_texto=duracao_texto,
    link_whatsapp=link_whatsapp, link_whatsapp_tutor=link_whatsapp_tutor,
    iniciais=iniciais, STATUS_UI=STATUS_UI, ROTULO_PORTE=ROTULO_PORTE,
    ROTULO_FORMA=ROTULO_FORMA, PORTES=PORTES, FORMAS_PAGAMENTO=FORMAS_PAGAMENTO,
    PERFIS=PERFIS, PROXIMO_STATUS=PROXIMO_STATUS,
)


# ---------------------------------------------------------------------------
# Seguranca: sessao, CSRF e decorators (RF01/RF02 + ISO 27002)
# ---------------------------------------------------------------------------
def csrf_token() -> str:
    if "_csrf" not in session:
        session["_csrf"] = secrets.token_urlsafe(32)
    return session["_csrf"]


app.jinja_env.globals["csrf_token"] = csrf_token


@app.before_request
def carregar_usuario_e_validar_csrf():
    g.usuario = None
    uid = session.get("usuario_id")
    if uid is not None:
        usuario = db.session.get(Usuario, uid)
        if usuario and usuario.ativo:
            g.usuario = usuario
        else:
            session.clear()

    if request.method == "POST":
        token = request.form.get("_csrf") or request.headers.get("X-CSRF-Token")
        if not token or not secrets.compare_digest(token, session.get("_csrf", "")):
            abort(400, description="Token de segurança inválido. Recarregue a página e tente novamente.")


@app.after_request
def cabecalhos_seguranca(resp):
    resp.headers.setdefault("X-Content-Type-Options", "nosniff")
    resp.headers.setdefault("X-Frame-Options", "DENY")
    resp.headers.setdefault("Referrer-Policy", "same-origin")
    return resp


def login_required(view):
    @wraps(view)
    def wrapper(*args, **kwargs):
        if g.usuario is None:
            flash("Faça login para acessar o sistema.", "warning")
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapper


def admin_required(view):
    @wraps(view)
    @login_required
    def wrapper(*args, **kwargs):
        if not g.usuario.is_admin:
            flash("Acesso restrito ao administrador.", "danger")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# Autenticacao (RF01, RF02)
# ---------------------------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if g.usuario:
        return redirect(url_for("dashboard"))

    login_digitado = ""
    if request.method == "POST":
        login_digitado = request.form.get("login", "").strip()
        senha = request.form.get("senha", "")
        usuario = Usuario.query.filter_by(login=login_digitado).first()
        falhas = session.get("falhas_login", {})

        if usuario and usuario.esta_bloqueado:
            restante = int((usuario.bloqueado_ate - datetime.now()).total_seconds() // 60) + 1
            flash(f"Usuário bloqueado temporariamente por excesso de tentativas. "
                  f"Tente novamente em {restante} minuto(s).", "danger")
        elif usuario and usuario.ativo and usuario.verificar_senha(senha):
            csrf = session.get("_csrf")
            session.clear()  # evita fixacao de sessao
            session["_csrf"] = csrf or secrets.token_urlsafe(32)
            session["usuario_id"] = usuario.id_usuario
            session.permanent = True
            usuario.bloqueado_ate = None
            db.session.commit()
            destino = request.args.get("next")
            if destino and destino.startswith("/") and not destino.startswith("//"):
                return redirect(destino)
            return redirect(url_for("dashboard"))
        else:
            if usuario and usuario.ativo:
                falhas[usuario.login] = falhas.get(usuario.login, 0) + 1
                restantes = app.config["MAX_TENTATIVAS_LOGIN"] - falhas[usuario.login]
                if restantes <= 0:
                    usuario.bloqueado_ate = datetime.now() + timedelta(minutes=app.config["MINUTOS_BLOQUEIO"])
                    db.session.commit()
                    falhas.pop(usuario.login, None)
                    flash(f"5 tentativas incorretas. Acesso bloqueado por "
                          f"{app.config['MINUTOS_BLOQUEIO']} minutos.", "danger")
                else:
                    flash(f"Login ou senha incorretos. Restam {restantes} tentativa(s) antes do bloqueio.", "danger")
            else:
                flash("Login ou senha incorretos.", "danger")
            session["falhas_login"] = falhas

    return render_template("login.html", login_digitado=login_digitado)


@app.route("/logout")
def logout():
    session.clear()
    flash("Sessão encerrada com segurança.", "success")
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Regras de grade de horarios e anti-choque (RF05, RF10, RF11, RF12)
# ---------------------------------------------------------------------------
def agendamentos_ativos_do_dia(dia: date, ignorar_id=None):
    q = Agendamento.query.filter(Agendamento.data == dia, Agendamento.status != STATUS_CANCELADO)
    if ignorar_id:
        q = q.filter(Agendamento.id_agendamento != ignorar_id)
    return q.order_by(Agendamento.hora_inicio).all()


def encontrar_conflito(dia: date, inicio: time, duracao_min: int, ignorar_id=None):
    """Retorna o agendamento ativo que se sobrepoe a [inicio, inicio+duracao) ou None."""
    novo_ini = datetime.combine(dia, inicio)
    novo_fim = novo_ini + timedelta(minutes=duracao_min)
    for ag in agendamentos_ativos_do_dia(dia, ignorar_id):
        if ag.inicio_dt < novo_fim and ag.fim_dt > novo_ini:
            return ag
    return None


def gerar_grade(dia: date):
    """Grade do dia em blocos de 30 min, indicando lacunas livres e ocupadas."""
    cfg = app.config
    agendamentos = agendamentos_ativos_do_dia(dia)
    slots = []
    atual = datetime.combine(dia, time(cfg["HORA_ABERTURA"]))
    fim = datetime.combine(dia, time(cfg["HORA_FECHAMENTO"]))
    passo = timedelta(minutes=cfg["INTERVALO_GRADE_MIN"])
    while atual < fim:
        ocupante = next((a for a in agendamentos if a.inicio_dt < atual + passo and a.fim_dt > atual), None)
        slots.append({
            "hora": atual.strftime("%H:%M"),
            "agendamento": ocupante,
            "inicio_bloco": ocupante is not None and ocupante.inicio_dt >= atual and ocupante.inicio_dt < atual + passo,
        })
        atual += passo
    return slots


def horarios_disponiveis(dia: date, duracao_min: int, ignorar_id=None):
    cfg = app.config
    resultado = []
    atual = datetime.combine(dia, time(cfg["HORA_ABERTURA"]))
    fechamento = datetime.combine(dia, time(cfg["HORA_FECHAMENTO"]))
    agora = datetime.now()
    while atual + timedelta(minutes=duracao_min) <= fechamento:
        conflito = encontrar_conflito(dia, atual.time(), duracao_min, ignorar_id)
        passado = atual < agora
        resultado.append({
            "hora": atual.strftime("%H:%M"),
            "livre": conflito is None and not passado,
            "motivo": ("Horário já passou" if passado else
                       f"Ocupado: {conflito.pet.nome} · {conflito.servico.nome}" if conflito else ""),
        })
        atual += timedelta(minutes=cfg["INTERVALO_GRADE_MIN"])
    return resultado


# ---------------------------------------------------------------------------
# Inicio: grade diaria + fila (RF10, RF13, RF14, RF15, RF16)
# ---------------------------------------------------------------------------
@app.route("/")
@login_required
def dashboard():
    dia = parse_data(request.args.get("data"), date.today())
    agendamentos = (Agendamento.query.filter(Agendamento.data == dia)
                    .order_by(Agendamento.hora_inicio).all())
    busca = request.args.get("q", "").strip().lower()
    if busca:
        agendamentos = [a for a in agendamentos
                        if busca in a.pet.nome.lower() or busca in a.pet.tutor.nome.lower()]

    colunas = {s: [a for a in agendamentos if a.status == s]
               for s in (STATUS_AGENDADO, STATUS_EM_ATENDIMENTO, STATUS_PRONTO, STATUS_CONCLUIDO)}
    cancelados = [a for a in agendamentos if a.status == STATUS_CANCELADO]

    faturamento_dia = (db.session.query(func.coalesce(func.sum(Pagamento.valor_pago), 0))
                       .filter(func.date(Pagamento.data_hora) == dia).scalar())

    hora = datetime.now().hour
    saudacao = "Bom dia" if hora < 12 else "Boa tarde" if hora < 18 else "Boa noite"

    return render_template(
        "dashboard.html",
        dia=dia, hoje=date.today(), saudacao=saudacao,
        dia_anterior=dia - timedelta(days=1), dia_seguinte=dia + timedelta(days=1),
        agendamentos=agendamentos, colunas=colunas, cancelados=cancelados,
        grade=gerar_grade(dia), faturamento_dia=faturamento_dia, busca=request.args.get("q", ""),
        tutores=Tutor.query.order_by(Tutor.nome).all(),
        servicos=Servico.query.filter_by(ativo=True).order_by(Servico.nome).all(),
    )


@app.route("/agendamentos", methods=["POST"])
@login_required
def criar_agendamento():
    f = request.form
    pet = db.session.get(Pet, f.get("pet_id", type=int) or 0)
    servico = db.session.get(Servico, f.get("servico_id", type=int) or 0)
    dia = parse_data(f.get("data"))
    hora = parse_hora(f.get("hora_inicio"))
    destino = destino_seguro()

    erros = []
    if not pet:
        erros.append("Selecione o tutor e o pet.")
    if not servico or not servico.ativo:
        erros.append("Selecione um serviço ativo.")
    if not dia:
        erros.append("Informe uma data válida.")
    elif dia < date.today():
        erros.append("Não é possível agendar em uma data passada.")
    if not hora:
        erros.append("Selecione o horário de início.")
    if erros:
        for e in erros:
            flash(e, "danger")
        return redirect(destino)

    inicio = datetime.combine(dia, hora)
    fim = inicio + timedelta(minutes=servico.duracao_min)
    if inicio.time() < time(app.config["HORA_ABERTURA"]) or fim > datetime.combine(dia, time(app.config["HORA_FECHAMENTO"])):
        flash(f"O atendimento precisa caber no expediente "
              f"({app.config['HORA_ABERTURA']:02d}:00 às {app.config['HORA_FECHAMENTO']:02d}:00).", "danger")
        return redirect(destino)

    # Regra Anti-Choque de Horario (RF12)
    conflito = encontrar_conflito(dia, hora, servico.duracao_min)
    if conflito:
        flash(f"Conflito de horário! Já existe {conflito.servico.nome} para {conflito.pet.nome} "
              f"das {conflito.inicio_dt:%H:%M} às {conflito.fim_dt:%H:%M}. "
              f"O novo atendimento ({inicio:%H:%M}–{fim:%H:%M}) não foi gravado.", "danger")
        return redirect(destino)

    valor = parse_decimal(f.get("valor_cobrado"), servico.valor)
    if valor is None or valor < 0:
        flash("Valor cobrado inválido.", "danger")
        return redirect(destino)

    ag = Agendamento(data=dia, hora_inicio=hora, status=STATUS_AGENDADO, valor_cobrado=valor,
                     FK_PET_id_pet=pet.id_pet, FK_SERVICO_id_servico=servico.id_servico)
    db.session.add(ag)
    db.session.commit()
    flash(f"Agendamento confirmado: {pet.nome} · {servico.nome} em "
          f"{dia:%d/%m/%Y} das {inicio:%H:%M} às {fim:%H:%M}.", "success")
    if request.form.get("voltar") == "agenda":
        return redirect(url_for("agenda_semanal", semana=dia.isoformat()))
    return redirect(url_for("dashboard", data=dia.isoformat()))


@app.route("/agendamentos/<int:id_agendamento>/status", methods=["POST"])
@login_required
def alterar_status(id_agendamento):
    ag = db.get_or_404(Agendamento, id_agendamento)
    acao = request.form.get("acao", "avancar")
    if acao == "cancelar":
        if ag.status not in (STATUS_AGENDADO, STATUS_EM_ATENDIMENTO):
            flash("Só é possível cancelar atendimentos agendados ou em andamento.", "warning")
        else:
            ag.status = STATUS_CANCELADO
            db.session.commit()
            flash(f"Agendamento de {ag.pet.nome} às {ag.hora_inicio:%H:%M} cancelado. O horário foi liberado.", "info")
    else:
        proximo = PROXIMO_STATUS.get(ag.status)
        if not proximo:
            flash("Este atendimento não pode avançar de status por aqui.", "warning")
        else:
            ag.status = proximo
            db.session.commit()
            flash(f"{ag.pet.nome}: status alterado para “{STATUS_UI[proximo]['texto']}”.", "success")
    return redirect(destino_seguro())


@app.route("/agendamentos/<int:id_agendamento>/pagamento", methods=["POST"])
@login_required
def registrar_pagamento(id_agendamento):
    """RF16/RF17 - entrega do pet + baixa do pagamento."""
    ag = db.get_or_404(Agendamento, id_agendamento)
    destino = destino_seguro()
    if ag.status != STATUS_PRONTO:
        flash("A baixa só pode ser feita para pets com status “Pronto para Retirada”.", "warning")
        return redirect(destino)

    forma = request.form.get("forma_pagamento")
    valor = parse_decimal(request.form.get("valor_pago"), ag.valor_cobrado)
    if forma not in FORMAS_PAGAMENTO:
        flash("Selecione a forma de pagamento.", "danger")
        return redirect(destino)
    if valor is None or valor <= 0:
        flash("Informe um valor pago válido.", "danger")
        return redirect(destino)

    agora = datetime.now()
    ag.data_hora_entrega = agora
    ag.status = STATUS_CONCLUIDO
    db.session.add(Pagamento(forma_pagamento=forma, valor_pago=valor, data_hora=agora,
                             FK_AGENDAMENTO_id_agendamento=ag.id_agendamento,
                             FK_USUARIO_id_usuario=g.usuario.id_usuario))
    db.session.commit()
    flash(f"Pagamento de {moeda(valor)} ({ROTULO_FORMA[forma]}) registrado. "
          f"{ag.pet.nome} entregue às {agora:%H:%M}.", "success")
    return redirect(destino)


# ---------------------------------------------------------------------------
# APIs JSON usadas pelos modais
# ---------------------------------------------------------------------------
@app.route("/api/horarios")
@login_required
def api_horarios():
    dia = parse_data(request.args.get("data"))
    servico = db.session.get(Servico, request.args.get("servico_id", type=int) or 0)
    if not dia or not servico:
        return jsonify({"horarios": []})
    return jsonify({"horarios": horarios_disponiveis(dia, servico.duracao_min),
                    "duracao_min": servico.duracao_min})


@app.route("/api/tutores/<int:id_tutor>/pets")
@login_required
def api_pets_tutor(id_tutor):
    tutor = db.get_or_404(Tutor, id_tutor)
    return jsonify({"pets": [{"id": p.id_pet, "nome": p.nome, "porte": ROTULO_PORTE.get(p.porte, p.porte),
                              "raca": p.raca or "", "observacoes": p.observacoes or ""} for p in tutor.pets]})


@app.route("/api/pets/<int:id_pet>/historico")
@login_required
def api_historico_pet(id_pet):
    """RF18 - historico de atendimentos de cada pet."""
    pet = db.get_or_404(Pet, id_pet)
    ags = (Agendamento.query.filter_by(FK_PET_id_pet=pet.id_pet)
           .order_by(Agendamento.data.desc(), Agendamento.hora_inicio.desc()).all())
    concluidos = [a for a in ags if a.status == STATUS_CONCLUIDO]
    total = sum((a.pagamento.valor_pago for a in concluidos if a.pagamento), Decimal("0"))
    return jsonify({
        "pet": {"nome": pet.nome, "porte": ROTULO_PORTE.get(pet.porte, pet.porte), "raca": pet.raca or "—",
                "observacoes": pet.observacoes or "", "tutor": pet.tutor.nome},
        "estatisticas": {"atendimentos": len(concluidos), "total": moeda(total)},
        "historico": [{
            "data": a.data.strftime("%d/%m/%Y"), "hora": a.hora_inicio.strftime("%H:%M"),
            "servico": a.servico.nome, "valor": moeda(a.pagamento.valor_pago if a.pagamento else a.valor_cobrado),
            "status": a.status, "status_texto": STATUS_UI[a.status]["texto"],
            "status_icone": STATUS_UI[a.status]["icone"], "status_classe": STATUS_UI[a.status]["classe"],
            "forma": ROTULO_FORMA.get(a.pagamento.forma_pagamento, "") if a.pagamento else "",
        } for a in ags],
    })


# ---------------------------------------------------------------------------
# Agenda semanal (RF11)
# ---------------------------------------------------------------------------
@app.route("/agenda")
@login_required
def agenda_semanal():
    ref = parse_data(request.args.get("semana"), date.today())
    inicio_semana = ref - timedelta(days=ref.weekday())
    dias = [inicio_semana + timedelta(days=i) for i in range(6)]  # Seg a Sab
    ags = (Agendamento.query.filter(Agendamento.data >= dias[0], Agendamento.data <= dias[-1],
                                    Agendamento.status != STATUS_CANCELADO)
           .order_by(Agendamento.data, Agendamento.hora_inicio).all())
    por_dia = {d: [] for d in dias}
    abertura = app.config["HORA_ABERTURA"]
    for a in ags:
        inicio_min = a.hora_inicio.hour * 60 + a.hora_inicio.minute - abertura * 60
        por_dia[a.data].append({"ag": a, "topo": inicio_min, "altura": a.servico.duracao_min})
    horas = list(range(abertura, app.config["HORA_FECHAMENTO"]))
    return render_template(
        "agenda_semanal.html", dias=dias, por_dia=por_dia, horas=horas, hoje=date.today(),
        semana_anterior=inicio_semana - timedelta(days=7), semana_seguinte=inicio_semana + timedelta(days=7),
        total_semana=len(ags),
        tutores=Tutor.query.order_by(Tutor.nome).all(),
        servicos=Servico.query.filter_by(ativo=True).order_by(Servico.nome).all(),
    )


# ---------------------------------------------------------------------------
# Tutores e Pets (RF07, RF08, RF09 + LGPD)
# ---------------------------------------------------------------------------
def validar_tutor(form):
    nome = form.get("nome", "").strip()
    telefone = so_digitos(form.get("telefone", ""))
    erros = []
    if len(nome) < 3 or len(nome) > 100:
        erros.append("Informe o nome completo do tutor (3 a 100 caracteres).")
    if len(telefone) not in (10, 11):
        erros.append("Informe um telefone/WhatsApp válido com DDD.")
    return nome, formatar_telefone(telefone), erros


def validar_pet(form, prefixo="pet_"):
    nome = form.get(f"{prefixo}nome", "").strip()
    porte = form.get(f"{prefixo}porte", "")
    raca = form.get(f"{prefixo}raca", "").strip() or None
    obs = form.get(f"{prefixo}observacoes", "").strip() or None
    erros = []
    if not nome or len(nome) > 60:
        erros.append("Informe o nome do pet (até 60 caracteres).")
    if porte not in PORTES:
        erros.append("Selecione o porte do pet.")
    if raca and len(raca) > 60:
        erros.append("A raça deve ter até 60 caracteres.")
    return {"nome": nome, "porte": porte, "raca": raca, "observacoes": obs}, erros


@app.route("/tutores")
@login_required
def tutores_pets():
    busca = request.args.get("q", "").strip()
    q = Tutor.query
    if busca:
        like = f"%{busca}%"
        digitos = so_digitos(busca)
        filtros = [Tutor.nome.ilike(like), Tutor.pets.any(Pet.nome.ilike(like))]
        if digitos:
            filtros.append(func.replace(func.replace(func.replace(func.replace(
                Tutor.telefone, "(", ""), ")", ""), "-", ""), " ", "").like(f"%{digitos}%"))
        q = q.filter(or_(*filtros))
    tutores = q.order_by(Tutor.nome).all()

    # Resumo por tutor: ultimo atendimento e total gasto
    resumo = {}
    for t in tutores:
        ids = [p.id_pet for p in t.pets]
        ultimo = total = None
        if ids:
            ultimo = (db.session.query(func.max(Agendamento.data))
                      .filter(Agendamento.FK_PET_id_pet.in_(ids), Agendamento.status == STATUS_CONCLUIDO).scalar())
            total = (db.session.query(func.coalesce(func.sum(Pagamento.valor_pago), 0))
                     .join(Agendamento).filter(Agendamento.FK_PET_id_pet.in_(ids)).scalar())
        resumo[t.id_tutor] = {"ultimo": ultimo, "total": total or 0}

    selecionado = None
    historico_tutor = []
    tutor_id = request.args.get("tutor", type=int)
    if tutor_id:
        selecionado = db.session.get(Tutor, tutor_id)
        if selecionado and selecionado.pets:
            historico_tutor = (Agendamento.query
                               .filter(Agendamento.FK_PET_id_pet.in_([p.id_pet for p in selecionado.pets]))
                               .order_by(Agendamento.data.desc(), Agendamento.hora_inicio.desc()).limit(30).all())

    return render_template("tutores_pets.html", tutores=tutores, resumo=resumo, busca=busca,
                           selecionado=selecionado, historico_tutor=historico_tutor,
                           todos_tutores=Tutor.query.order_by(Tutor.nome).all(),
                           servicos=Servico.query.filter_by(ativo=True).order_by(Servico.nome).all(),
                           hoje=date.today())


@app.route("/tutores", methods=["POST"])
@login_required
def criar_tutor():
    nome, telefone, erros = validar_tutor(request.form)
    dados_pet, erros_pet = None, []
    if request.form.get("pet_nome", "").strip():
        dados_pet, erros_pet = validar_pet(request.form)
    if erros or erros_pet:
        for e in erros + erros_pet:
            flash(e, "danger")
        return redirect(url_for("tutores_pets"))
    tutor = Tutor(nome=nome, telefone=telefone)
    db.session.add(tutor)
    db.session.flush()
    if dados_pet:
        db.session.add(Pet(FK_TUTOR_id_tutor=tutor.id_tutor, **dados_pet))
    db.session.commit()
    flash(f"Tutor {nome} cadastrado com sucesso" + (f" com o pet {dados_pet['nome']}." if dados_pet else "."), "success")
    return redirect(url_for("tutores_pets", tutor=tutor.id_tutor))


@app.route("/tutores/<int:id_tutor>/editar", methods=["POST"])
@login_required
def editar_tutor(id_tutor):
    tutor = db.get_or_404(Tutor, id_tutor)
    nome, telefone, erros = validar_tutor(request.form)
    if erros:
        for e in erros:
            flash(e, "danger")
    else:
        tutor.nome, tutor.telefone = nome, telefone
        db.session.commit()
        flash("Dados do tutor atualizados.", "success")
    return redirect(url_for("tutores_pets", tutor=tutor.id_tutor))


def _pet_tem_pendencia(pet: Pet) -> bool:
    return any(a.status in STATUS_ATIVOS for a in pet.agendamentos)


def _pet_tem_historico_financeiro(pet: Pet) -> bool:
    return any(a.pagamentos for a in pet.agendamentos)


def _anonimizar_pet(pet: Pet):
    pet.nome = f"Pet anonimizado #{pet.id_pet}"
    pet.raca = None
    pet.observacoes = None


def _remover_pet(pet: Pet):
    for a in list(pet.agendamentos):  # apenas cancelados/sem pagamento chegam aqui
        db.session.delete(a)
    db.session.delete(pet)


@app.route("/tutores/<int:id_tutor>/excluir", methods=["POST"])
@login_required
def excluir_tutor(id_tutor):
    """LGPD - exclui o tutor ou anonimiza, preservando registros financeiros."""
    tutor = db.get_or_404(Tutor, id_tutor)
    if any(_pet_tem_pendencia(p) for p in tutor.pets):
        flash("Este tutor possui atendimentos em aberto (agendados, em atendimento ou aguardando retirada). "
              "Conclua ou cancele-os antes de excluir.", "danger")
        return redirect(url_for("tutores_pets", tutor=tutor.id_tutor))

    if any(_pet_tem_historico_financeiro(p) for p in tutor.pets):
        tutor.nome = f"Tutor anonimizado #{tutor.id_tutor}"
        tutor.telefone = "00000000000"
        for p in tutor.pets:
            if _pet_tem_historico_financeiro(p):
                _anonimizar_pet(p)
            else:
                _remover_pet(p)
        db.session.commit()
        flash("Dados pessoais anonimizados (LGPD). Os registros financeiros já cobrados foram preservados.", "info")
    else:
        for p in list(tutor.pets):
            _remover_pet(p)
        db.session.delete(tutor)
        db.session.commit()
        flash("Tutor e pets excluídos definitivamente.", "info")
    return redirect(url_for("tutores_pets"))


@app.route("/tutores/<int:id_tutor>/pets", methods=["POST"])
@login_required
def criar_pet(id_tutor):
    tutor = db.get_or_404(Tutor, id_tutor)
    dados, erros = validar_pet(request.form)
    if erros:
        for e in erros:
            flash(e, "danger")
    else:
        db.session.add(Pet(FK_TUTOR_id_tutor=tutor.id_tutor, **dados))
        db.session.commit()
        flash(f"Pet {dados['nome']} vinculado a {tutor.nome}.", "success")
    return redirect(url_for("tutores_pets", tutor=tutor.id_tutor))


@app.route("/pets/<int:id_pet>/editar", methods=["POST"])
@login_required
def editar_pet(id_pet):
    pet = db.get_or_404(Pet, id_pet)
    dados, erros = validar_pet(request.form)
    if erros:
        for e in erros:
            flash(e, "danger")
    else:
        for k, v in dados.items():
            setattr(pet, k, v)
        db.session.commit()
        flash(f"Dados de {pet.nome} atualizados.", "success")
    return redirect(url_for("tutores_pets", tutor=pet.FK_TUTOR_id_tutor))


@app.route("/pets/<int:id_pet>/excluir", methods=["POST"])
@login_required
def excluir_pet(id_pet):
    pet = db.get_or_404(Pet, id_pet)
    tutor_id = pet.FK_TUTOR_id_tutor
    if _pet_tem_pendencia(pet):
        flash(f"{pet.nome} possui atendimentos em aberto. Conclua ou cancele-os antes de excluir.", "danger")
    elif _pet_tem_historico_financeiro(pet):
        _anonimizar_pet(pet)
        db.session.commit()
        flash("Pet anonimizado (LGPD). O histórico financeiro foi preservado.", "info")
    else:
        _remover_pet(pet)
        db.session.commit()
        flash("Pet excluído definitivamente.", "info")
    return redirect(url_for("tutores_pets", tutor=tutor_id))


# ---------------------------------------------------------------------------
# Historico / Faturamento (RF06, RF19) - exclusivo Admin
# ---------------------------------------------------------------------------
@app.route("/historico")
@admin_required
def historico():
    hoje = date.today()
    inicio = parse_data(request.args.get("inicio"), hoje.replace(day=1))
    fim = parse_data(request.args.get("fim"), hoje)
    if inicio > fim:
        inicio, fim = fim, inicio
    forma = request.args.get("forma", "")

    q = (Agendamento.query.join(Pagamento)
         .filter(Agendamento.status == STATUS_CONCLUIDO, Agendamento.data >= inicio, Agendamento.data <= fim))
    if forma in FORMAS_PAGAMENTO:
        q = q.filter(Pagamento.forma_pagamento == forma)
    atendimentos = q.order_by(Agendamento.data.desc(), Agendamento.hora_inicio.desc()).all()

    total = sum((a.pagamento.valor_pago for a in atendimentos), Decimal("0"))
    por_forma = {f: Decimal("0") for f in FORMAS_PAGAMENTO}
    for a in atendimentos:
        por_forma[a.pagamento.forma_pagamento] += a.pagamento.valor_pago
    ticket = (total / len(atendimentos)) if atendimentos else Decimal("0")

    return render_template("historico.html", atendimentos=atendimentos, inicio=inicio, fim=fim, forma=forma,
                           total=total, por_forma=por_forma, ticket=ticket)


# ---------------------------------------------------------------------------
# Servicos (RF03, RF04) e Usuarios - exclusivo Admin
# ---------------------------------------------------------------------------
def validar_servico(form):
    nome = form.get("nome", "").strip()
    duracao = form.get("duracao_min", type=int)
    valor = parse_decimal(form.get("valor"))
    erros = []
    if not nome or len(nome) > 60:
        erros.append("Informe o nome do serviço (até 60 caracteres).")
    if not duracao or duracao <= 0 or duracao > 600:
        erros.append("Informe a duração em minutos (ex.: 30, 45, 60, 90).")
    if valor is None or valor < 0:
        erros.append("Informe um valor válido (ex.: 55,00).")
    return nome, duracao, valor, erros


@app.route("/servicos")
@admin_required
def servicos():
    return render_template("servicos.html",
                           servicos=Servico.query.order_by(Servico.ativo.desc(), Servico.nome).all(),
                           usuarios=Usuario.query.order_by(Usuario.nome).all(), agora=datetime.now())


@app.route("/servicos", methods=["POST"])
@admin_required
def criar_servico():
    nome, duracao, valor, erros = validar_servico(request.form)
    if erros:
        for e in erros:
            flash(e, "danger")
    else:
        db.session.add(Servico(nome=nome, duracao_min=duracao, valor=valor, ativo=True))
        db.session.commit()
        flash(f"Serviço “{nome}” cadastrado.", "success")
    return redirect(url_for("servicos"))


@app.route("/servicos/<int:id_servico>/editar", methods=["POST"])
@admin_required
def editar_servico(id_servico):
    s = db.get_or_404(Servico, id_servico)
    nome, duracao, valor, erros = validar_servico(request.form)
    if erros:
        for e in erros:
            flash(e, "danger")
    else:
        s.nome, s.duracao_min, s.valor = nome, duracao, valor
        db.session.commit()
        flash(f"Serviço “{nome}” atualizado.", "success")
    return redirect(url_for("servicos"))


@app.route("/servicos/<int:id_servico>/status", methods=["POST"])
@admin_required
def alternar_servico(id_servico):
    s = db.get_or_404(Servico, id_servico)
    s.ativo = not s.ativo
    db.session.commit()
    flash(f"Serviço “{s.nome}” {'ativado' if s.ativo else 'inativado'}.", "success")
    return redirect(url_for("servicos"))


def validar_usuario(form, novo=True, usuario=None):
    nome = form.get("nome", "").strip()
    login_ = form.get("login", "").strip().lower()
    senha = form.get("senha", "")
    perfil = form.get("perfil", "")
    erros = []
    if len(nome) < 3 or len(nome) > 100:
        erros.append("Informe o nome completo do colaborador.")
    if not login_ or len(login_) > 50 or " " in login_:
        erros.append("Informe um login sem espaços (até 50 caracteres).")
    else:
        existente = Usuario.query.filter_by(login=login_).first()
        if existente and (novo or existente.id_usuario != usuario.id_usuario):
            erros.append("Este login já está em uso.")
    if perfil not in PERFIS:
        erros.append("Selecione o perfil de acesso.")
    if novo or senha:
        if len(senha) < 8 or senha.isdigit() or senha.isalpha():
            erros.append("A senha deve ter pelo menos 8 caracteres, com letras e números.")
    return nome, login_, senha, perfil, erros


@app.route("/usuarios", methods=["POST"])
@admin_required
def criar_usuario():
    nome, login_, senha, perfil, erros = validar_usuario(request.form)
    if erros:
        for e in erros:
            flash(e, "danger")
    else:
        u = Usuario(nome=nome, login=login_, perfil=perfil, ativo=True)
        u.set_senha(senha)
        db.session.add(u)
        db.session.commit()
        flash(f"Colaborador {nome} cadastrado com perfil {perfil}.", "success")
    return redirect(url_for("servicos") + "#equipe")


@app.route("/usuarios/<int:id_usuario>/editar", methods=["POST"])
@admin_required
def editar_usuario(id_usuario):
    u = db.get_or_404(Usuario, id_usuario)
    nome, login_, senha, perfil, erros = validar_usuario(request.form, novo=False, usuario=u)
    if u.id_usuario == g.usuario.id_usuario and perfil != "Admin":
        erros.append("Você não pode remover o seu próprio perfil de administrador.")
    if erros:
        for e in erros:
            flash(e, "danger")
    else:
        u.nome, u.login, u.perfil = nome, login_, perfil
        if senha:
            u.set_senha(senha)
        db.session.commit()
        flash(f"Dados de {nome} atualizados.", "success")
    return redirect(url_for("servicos") + "#equipe")


@app.route("/usuarios/<int:id_usuario>/status", methods=["POST"])
@admin_required
def alternar_usuario(id_usuario):
    u = db.get_or_404(Usuario, id_usuario)
    if u.id_usuario == g.usuario.id_usuario:
        flash("Você não pode inativar o seu próprio usuário.", "warning")
    else:
        u.ativo = not u.ativo
        db.session.commit()
        flash(f"Usuário {u.nome} {'ativado' if u.ativo else 'inativado'}.", "success")
    return redirect(url_for("servicos") + "#equipe")


@app.route("/usuarios/<int:id_usuario>/desbloquear", methods=["POST"])
@admin_required
def desbloquear_usuario(id_usuario):
    u = db.get_or_404(Usuario, id_usuario)
    u.bloqueado_ate = None
    db.session.commit()
    flash(f"Usuário {u.nome} desbloqueado.", "success")
    return redirect(url_for("servicos") + "#equipe")


# ---------------------------------------------------------------------------
# Erros
# ---------------------------------------------------------------------------
@app.errorhandler(400)
def erro_400(e):
    flash(getattr(e, "description", "Requisição inválida."), "danger")
    return redirect(request.referrer or url_for("dashboard"))


@app.errorhandler(404)
def erro_404(e):
    flash("Registro não encontrado.", "warning")
    return redirect(url_for("dashboard") if g.get("usuario") else url_for("login"))


if __name__ == "__main__":
    app.run(debug=True)
