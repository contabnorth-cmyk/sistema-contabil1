import os
import re
import sqlite3
import hashlib
from datetime import date, datetime
from calendar import monthrange
from pathlib import Path
import urllib.parse

import pandas as pd
import streamlit as st
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas
from reportlab.lib.units import cm

APP_DIR = Path(__file__).resolve().parent
DB_PATH = APP_DIR / "contabilidade.db"
DOCS_DIR = APP_DIR / "documentos_clientes"
DOCS_DIR.mkdir(exist_ok=True)

st.set_page_config(page_title="Contab North Consultorias", page_icon="📊", layout="wide")

st.markdown("""
<style>
.block-container {padding-top: 1.2rem; padding-bottom: 2rem;}
[data-testid="stMetricValue"] {font-size: 1.7rem;}
[data-testid="stSidebar"] {background: linear-gradient(180deg,#0f172a 0%, #111827 100%);}
[data-testid="stSidebar"] * {color: #1e3a8a;}
.stTabs [data-baseweb="tab-list"] {gap: 8px;}
.stTabs [data-baseweb="tab"] {
    background: #e5e7eb; color: #1e293b !important; border-radius: 10px; padding: .5rem .9rem; border: 1px solid #cbd5;
}
.stTabs [aria-selected="true"] {background: #2563eb !important;}
.card { 
    border: 3px solid #1d4ed8; border-radius: 16px; padding: 1rem 1.1rem; background: #1e293b;
    box-shadow: 0 4px 18px rgba(15,23,42,.05); margin-bottom: .8rem;
}
.small-muted {color: #64748b; font-size: .92rem;}
</style>
""", unsafe_allow_html=True)

# ----------------- Database -----------------
def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn  
def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS billing (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER,
        competencia TEXT,
        vencimento TEXT,
        valor REAL,
        status TEXT
    )
    """)

    conn.commit()
    conn.close()

conn = get_conn()
init_db()

def execute(query, params=(), fetch=False, many=False):
    cur = conn.cursor()
    if many:
        cur.executemany(query, params)
    else:
        cur.execute(query, params)
    conn.commit()
    if fetch:
        return cur.fetchall()
    return None

def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()

def init_db():
    execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        full_name TEXT,
        role TEXT DEFAULT 'admin'
    )""")
    execute("""
    CREATE TABLE IF NOT EXISTS clients (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        cnpj_cpf TEXT,
        responsavel TEXT,
        telefone TEXT,
        email TEXT,
        regime TEXT,
        honorarios REAL DEFAULT 0,
        vencimento INTEGER DEFAULT 10,
        status TEXT DEFAULT 'Ativo',
        observacoes TEXT,
        portal_senha TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP
    )""")
    execute("""
    CREATE TABLE IF NOT EXISTS billing (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        competencia TEXT NOT NULL,
        vencimento TEXT NOT NULL,
        valor REAL NOT NULL,
        status TEXT DEFAULT 'Pendente',
        pago_em TEXT,
        forma_pagamento TEXT,
        observacoes TEXT,
        created_at TEXT DEFAULT CURRENT_TIMESTAMP,
        UNIQUE(client_id, competencia),
        FOREIGN KEY(client_id) REFERENCES clients(id)
    )""")
    execute("""
    CREATE TABLE IF NOT EXISTS task_templates (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome_tarefa TEXT NOT NULL,
        descricao TEXT,
        obrigacao TEXT,
        setor TEXT,
        dia_vencimento INTEGER DEFAULT 10,
        ativa INTEGER DEFAULT 1
    )""")
    execute("""
    CREATE TABLE IF NOT EXISTS tasks (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        competencia TEXT NOT NULL,
        nome_tarefa TEXT NOT NULL,
        descricao TEXT,
        obrigacao TEXT,
        setor TEXT,
        vencimento TEXT NOT NULL,
        status TEXT DEFAULT 'Pendente',
        concluida_em TEXT,
        observacoes TEXT,
        UNIQUE(client_id, competencia, nome_tarefa),
        FOREIGN KEY(client_id) REFERENCES clients(id)
    )""")
    execute("""
    CREATE TABLE IF NOT EXISTS financial_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        data TEXT NOT NULL,
        tipo TEXT NOT NULL,
        categoria TEXT NOT NULL,
        descricao TEXT NOT NULL,
        valor REAL NOT NULL,
        client_id INTEGER,
        competencia TEXT,
        forma_pagamento TEXT,
        observacoes TEXT,
        FOREIGN KEY(client_id) REFERENCES clients(id)
    )""")
    execute("""
    CREATE TABLE IF NOT EXISTS documents (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        client_id INTEGER NOT NULL,
        nome_arquivo TEXT NOT NULL,
        caminho TEXT NOT NULL,
        categoria TEXT,
        enviado_em TEXT DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY(client_id) REFERENCES clients(id)
    )""")
    execute("""
    CREATE TABLE IF NOT EXISTS app_settings (
        chave TEXT PRIMARY KEY,
        valor TEXT
    )""")

    admin = execute("SELECT * FROM users WHERE username='admin'", fetch=True)
    if not admin:
        execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)",
            ("admin", hash_password("Rba182326*"), "Administrador", "admin"),
        )

    templates = execute("SELECT COUNT(*) AS n FROM task_templates", fetch=True)[0]["n"]
    if templates == 0:
        default_templates = [
            ("Apurar DAS", "Conferir faturamento e gerar guia DAS", "DAS", "Fiscal", 20, 1),
            ("Folha de pagamento", "Processar folha e encargos", "Folha", "Pessoal", 30, 1),
            ("Enviar pró-labore", "Calcular e enviar pró-labore", "Pró-labore", "Pessoal", 28, 1),
            ("Conferir impostos", "Revisar tributos do mês", "Impostos", "Fiscal", 25, 1),
            ("Obrigações acessórias", "Entregar declarações obrigatórias", "Acessórias", "Fiscal", 15, 1),
        ]
        execute(
            "INSERT INTO task_templates (nome_tarefa, descricao, obrigacao, setor, dia_vencimento, ativa) VALUES (?, ?, ?, ?, ?, ?)",
            default_templates,
            many=True,
        )

    defaults = {
        "office_name": "Meu Escritório Contábil",
        "office_whatsapp": "",
        "office_email": "",
        "logo_text": "Contab Office Pro",
    }
    for k, v in defaults.items():
        row = execute("SELECT valor FROM app_settings WHERE chave=?", (k,), fetch=True)
        if not row:
            execute("INSERT INTO app_settings (chave, valor) VALUES (?, ?)", (k, v))

def get_setting(chave, default=""):
    row = execute("SELECT valor FROM app_settings WHERE chave=?", (chave,), fetch=True)
    return row[0]["valor"] if row else default

def set_setting(chave, valor):
    execute(
        "INSERT INTO app_settings (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor=excluded.valor",
        (chave, valor),
    )

init_db()

# ----------------- Helpers -----------------
def to_brl(value):
    try:
        return f"R$ {float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except Exception:
        return "R$ 0,00"

def today_str():
    return date.today().isoformat()

def competencia_atual():
    return date.today().strftime("%Y-%m")

def safe_day(year, month, day):
    return min(day, monthrange(year, month)[1])

def normalize_phone(phone: str) -> str:
    digits = "".join(re.findall(r"\d+", phone or ""))
    if digits and len(digits) <= 11:
        digits = "55" + digits
    return digits

def whatsapp_link(phone, message):
    digits = normalize_phone(phone)
    if not digits:
        return None
    return f"https://wa.me/{digits}?text={urllib.parse.quote(message)}"

def df(query, params=()):
    rows = execute(query, params, fetch=True)
    return pd.DataFrame([dict(r) for r in rows]) if rows else pd.DataFrame()

def login(username, password):
    rows = execute("SELECT * FROM users WHERE username=?", (username,), fetch=True)
    if not rows:
        return None
    user = rows[0]
    if user["password_hash"] == hash_password(password):
        return dict(user)
    return None

def portal_login(cnpj_cpf, senha):
    rows = execute("SELECT * FROM clients WHERE cnpj_cpf=? AND portal_senha=?", (cnpj_cpf, hash_password(senha)), fetch=True)
    return dict(rows[0]) if rows else None

def ensure_month_data(competencia: str):
    generate_monthly_billing(competencia)
    generate_monthly_tasks(competencia)

def generate_monthly_billing(competencia: str):
    ano, mes = map(int, competencia.split("-"))
    clients = execute("SELECT * FROM clients WHERE status='Ativo'", fetch=True)
    created = 0
    for c in clients:
        venc = date(ano, mes, safe_day(ano, mes, int(c["vencimento"] or 10))).isoformat()
        try:
            execute(
                "INSERT INTO billing (client_id, competencia, vencimento, valor, status) VALUES (?, ?, ?, ?, 'Pendente')",
                (c["id"], competencia, venc, float(c["honorarios"] or 0)),
            )
            created += 1
        except sqlite3.IntegrityError:
            pass
    return created

def generate_monthly_tasks(competencia: str):
    ano, mes = map(int, competencia.split("-"))
    clients = execute("SELECT * FROM clients WHERE status='Ativo'", fetch=True)
    templates = execute("SELECT * FROM task_templates WHERE ativa=1", fetch=True)
    created = 0
    for c in clients:
        for t in templates:
            venc = date(ano, mes, safe_day(ano, mes, int(t["dia_vencimento"] or 10))).isoformat()
            try:
                execute(
                    """INSERT INTO tasks (client_id, competencia, nome_tarefa, descricao, obrigacao, setor, vencimento, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'Pendente')""",
                    (c["id"], competencia, t["nome_tarefa"], t["descricao"], t["obrigacao"], t["setor"], venc),
                )
                created += 1
            except sqlite3.IntegrityError:
                pass
    return created

def export_dashboard_pdf(filepath: Path):
    c = canvas.Canvas(str(filepath), pagesize=A4)
    width, height = A4
    y = height - 2 * cm
    office = get_setting("office_name", "Escritório Contábil")
    c.setFont("Helvetica-Bold", 16)
    c.drawString(2 * cm, y, office)
    y -= 1 * cm
    c.setFont("Helvetica", 10)
    c.drawString(2 * cm, y, f"Relatório gerado em: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    y -= 1 * cm

    total_clients = execute("SELECT COUNT(*) n FROM clients WHERE status='Ativo'", fetch=True)[0]["n"]
    inad = execute("SELECT COUNT(*) n FROM billing WHERE status='Atrasado'", fetch=True)[0]["n"]
    pend = execute("SELECT COUNT(*) n FROM tasks WHERE status!='Concluída'", fetch=True)[0]["n"]
    fat = execute("SELECT COALESCE(SUM(valor),0) total FROM billing WHERE competencia=?", (competencia_atual(),), fetch=True)[0]["total"]

    for line in [
        f"Clientes ativos: {total_clients}",
        f"Cobranças atrasadas: {inad}",
        f"Tarefas pendentes: {pend}",
        f"Faturamento previsto ({competencia_atual()}): {to_brl(fat)}",
    ]:
        c.drawString(2 * cm, y, line)
        y -= 0.7 * cm

    c.save()

# ----------------- Sidebar / Auth -----------------
if "user" not in st.session_state:
    st.session_state.user = None
if "portal_client" not in st.session_state:
    st.session_state.portal_client = None

with st.sidebar:
    st.markdown("## 📊 Contab Office Pro")
    st.caption("Sistema para escritório de contabilidade")
    modo = st.radio("Acesso", ["Escritório", "Portal do cliente"], label_visibility="collapsed")
    st.markdown("---")
    if modo == "Escritório" and st.session_state.user:
        st.success(f"Usuário: {st.session_state.user['username']}")
        if st.button("Sair do escritório", use_container_width=True):
            st.session_state.user = None
            st.rerun()
    if modo == "Portal do cliente" and st.session_state.portal_client:
        st.success(f"Cliente: {st.session_state.portal_client['nome']}")
        if st.button("Sair do portal", use_container_width=True):
            st.session_state.portal_client = None
            st.rerun()
    st.markdown("---")
    st.caption("Login inicial do escritório: admin / 123456")

# ----------------- Telas -----------------
def login_screen():
    st.title("📊 Contab Office Pro")
    st.caption("Versão profissional pronta para uso local ou publicação no Streamlit Cloud")
    a, b, c = st.columns([1, 1.2, 1])
    with b:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        st.subheader("Acesso do escritório")
        with st.form("login_form"):
            username = st.text_input("Usuário", value="admin")
            password = st.text_input("Senha", type="password", value="123456")
            submit = st.form_submit_button("Entrar", use_container_width=True)
        if submit:
            user = login(username, password)
            if user:
                st.session_state.user = user
                st.rerun()
            st.error("Usuário ou senha inválidos.")
        st.markdown('</div>', unsafe_allow_html=True)

def portal_login_screen():
    st.title("👤 Portal do cliente")
    st.caption("Área simples para consulta de cobranças, tarefas e documentos")
    a, b, c = st.columns([1, 1.2, 1])
    with b:
        st.markdown('<div class="card">', unsafe_allow_html=True)
        with st.form("portal_form"):
            cnpj_cpf = st.text_input("CNPJ ou CPF")
            senha = st.text_input("Senha do portal", type="password")
            submit = st.form_submit_button("Entrar no portal", use_container_width=True)
        if submit:
            client = portal_login(cnpj_cpf, senha)
            if client:
                st.session_state.portal_client = client
                st.rerun()
            st.error("Dados do portal inválidos.")
        st.markdown("<div class='small-muted'>Dica: defina a senha do portal no cadastro do cliente.</div>", unsafe_allow_html=True)
        st.markdown('</div>', unsafe_allow_html=True)

def dashboard_tab():
    ensure_month_data(competencia_atual())
    total_clients = execute("SELECT COUNT(*) n FROM clients WHERE status='Ativo'", fetch=True)[0]["n"]
    total_inad = execute("SELECT COUNT(*) n FROM billing WHERE status='Atrasado'", fetch=True)[0]["n"]
    total_pend = execute("SELECT COUNT(*) n FROM tasks WHERE status!='Concluída'", fetch=True)[0]["n"]
    fat_prev = execute("SELECT COALESCE(SUM(valor),0) total FROM billing WHERE competencia=?", (competencia_atual(),), fetch=True)[0]["total"]
    recebido_mes = execute("SELECT COALESCE(SUM(valor),0) total FROM financial_entries WHERE tipo='Receita' AND substr(data,1,7)=?", (competencia_atual(),), fetch=True)[0]["total"]

    a, b, c, d = st.columns(4)
    a.metric("Clientes ativos", total_clients)
    b.metric("Cobranças atrasadas", total_inad)
    c.metric("Tarefas pendentes", total_pend)
    d.metric("Recebido no mês", to_brl(recebido_mes))
    st.metric("Faturamento previsto da competência", to_brl(fat_prev))

    x, y = st.columns([1.8, 1])
    with x:
        cobr = df("""
            SELECT c.nome AS cliente, b.competencia, b.vencimento, b.valor, b.status
            FROM billing b JOIN clients c ON c.id=b.client_id
            ORDER BY b.vencimento ASC LIMIT 12
        """)
        st.markdown("#### Próximas cobranças")
        st.dataframe(cobr, use_container_width=True, hide_index=True) if not cobr.empty else st.info("Sem cobranças.")
    with y:
        tarefas = df("SELECT status, COUNT(*) qtd FROM tasks GROUP BY status")
        st.markdown("#### Tarefas por status")
        st.bar_chart(tarefas.set_index("status")) if not tarefas.empty else st.info("Sem tarefas.")

    pdf_path = APP_DIR / "relatorio_dashboard.pdf"
    export_dashboard_pdf(pdf_path)
    with open(pdf_path, "rb") as f:
        st.download_button("⬇️ Baixar relatório do painel em PDF", data=f.read(), file_name="relatorio_dashboard.pdf", mime="application/pdf")

def clients_tab():
    st.subheader("Clientes")
    with st.expander("➕ Novo cliente"):
        with st.form("novo_cliente"):
            c1, c2, c3 = st.columns(3)
            nome = c1.text_input("Nome / Razão social *")
            cnpj = c2.text_input("CNPJ / CPF")
            resp = c3.text_input("Responsável")
            c4, c5, c6 = st.columns(3)
            telefone = c4.text_input("Telefone / WhatsApp")
            email = c5.text_input("E-mail")
            regime = c6.selectbox("Regime tributário", ["", "MEI", "Simples Nacional", "Lucro Presumido", "Lucro Real", "Autônomo"])
            c7, c8, c9 = st.columns(3)
            honor = c7.number_input("Honorários mensais", min_value=0.0, step=50.0)
            venc = c8.number_input("Dia de vencimento", min_value=1, max_value=31, value=10)
            status = c9.selectbox("Status", ["Ativo", "Inativo"])
            portal_senha = st.text_input("Senha do portal do cliente")
            obs = st.text_area("Observações")
            submit = st.form_submit_button("Salvar cliente")
        if submit:
            if not nome.strip():
                st.error("Informe o nome do cliente.")
            else:
                execute(
                    """INSERT INTO clients (nome, cnpj_cpf, responsavel, telefone, email, regime, honorarios, vencimento, status, observacoes, portal_senha)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (nome, cnpj, resp, telefone, email, regime, honor, venc, status, obs, hash_password(portal_senha) if portal_senha else None),
                )
                st.success("Cliente cadastrado.")
                st.rerun()

    clientes = df("SELECT * FROM clients ORDER BY nome")
    if clientes.empty:
        st.info("Nenhum cliente cadastrado.")
        return

    filtro = st.text_input("Pesquisar cliente")
    if filtro:
        mask = clientes.apply(lambda r: filtro.lower() in " ".join([str(v) for v in r.values]).lower(), axis=1)
        clientes = clientes[mask]

    st.dataframe(clientes[["id", "nome", "cnpj_cpf", "telefone", "email", "regime", "honorarios", "vencimento", "status"]], use_container_width=True, hide_index=True)

    selected_id = st.selectbox("Selecionar cliente para editar", clientes["id"].tolist(), format_func=lambda x: f"{x} - {clientes.loc[clientes['id']==x, 'nome'].iloc[0]}")
    row = execute("SELECT * FROM clients WHERE id=?", (int(selected_id),), fetch=True)[0]

    with st.expander("✏️ Editar cliente"):
        with st.form("editar_cliente"):
            c1, c2, c3 = st.columns(3)
            nome = c1.text_input("Nome / Razão social", value=row["nome"])
            cnpj = c2.text_input("CNPJ / CPF", value=row["cnpj_cpf"] or "")
            resp = c3.text_input("Responsável", value=row["responsavel"] or "")
            c4, c5, c6 = st.columns(3)
            telefone = c4.text_input("Telefone / WhatsApp", value=row["telefone"] or "")
            email = c5.text_input("E-mail", value=row["email"] or "")
            regime = c6.text_input("Regime tributário", value=row["regime"] or "")
            c7, c8, c9 = st.columns(3)
            honor = c7.number_input("Honorários mensais", min_value=0.0, value=float(row["honorarios"] or 0))
            venc = c8.number_input("Dia de vencimento", min_value=1, max_value=31, value=int(row["vencimento"] or 10))
            status = c9.selectbox("Status", ["Ativo", "Inativo"], index=0 if row["status"] == "Ativo" else 1)
            nova_senha = st.text_input("Nova senha do portal (deixe em branco para manter)")
            obs = st.text_area("Observações", value=row["observacoes"] or "")
            save = st.form_submit_button("Atualizar")
        if save:
            portal_hash = row["portal_senha"] if not nova_senha else hash_password(nova_senha)
            execute(
                """UPDATE clients SET nome=?, cnpj_cpf=?, responsavel=?, telefone=?, email=?, regime=?, honorarios=?, vencimento=?, status=?, observacoes=?, portal_senha=?
                   WHERE id=?""",
                (nome, cnpj, resp, telefone, email, regime, honor, venc, status, obs, portal_hash, selected_id),
            )
            st.success("Cliente atualizado.")
            st.rerun()

    if st.button("🗑️ Excluir cliente selecionado"):
        execute("DELETE FROM documents WHERE client_id=?", (selected_id,))
        execute("DELETE FROM financial_entries WHERE client_id=?", (selected_id,))
        execute("DELETE FROM tasks WHERE client_id=?", (selected_id,))
        execute("DELETE FROM billing WHERE client_id=?", (selected_id,))
        execute("DELETE FROM clients WHERE id=?", (selected_id,))
        st.success("Cliente excluído.")
        st.rerun()

def billing_tab():
    st.subheader("Cobranças")
    comp = st.text_input("Competência (AAAA-MM)", value=competencia_atual())
    c1, c2 = st.columns([1, 2])
    with c1:
        if st.button("Gerar cobranças da competência", use_container_width=True):
            qtd = generate_monthly_billing(comp)
            st.success(f"{qtd} cobranças criadas.")
            st.rerun()
    with c2:
        st.caption("Cobranças geradas com base nos honorários mensais e dia de vencimento dos clientes ativos.")

    rows = df("""
        SELECT b.id, c.nome AS cliente, c.telefone, c.email, b.client_id, b.competencia, b.vencimento, b.valor, b.status, b.pago_em, b.forma_pagamento, b.observacoes
        FROM billing b JOIN clients c ON c.id=b.client_id
        WHERE b.competencia=?
        ORDER BY b.vencimento, c.nome
    """, (comp,))
    if rows.empty:
        st.info("Nenhuma cobrança encontrada para essa competência.")
        return
    st.dataframe(rows[["id", "cliente", "competencia", "vencimento", "valor", "status", "pago_em", "forma_pagamento"]], use_container_width=True, hide_index=True)

    selected_id = st.selectbox("Selecionar cobrança", rows["id"].tolist(), format_func=lambda x: f"{x} - {rows.loc[rows['id']==x, 'cliente'].iloc[0]}")
    bill = execute("SELECT b.*, c.nome AS cliente, c.telefone, c.email FROM billing b JOIN clients c ON c.id=b.client_id WHERE b.id=?", (int(selected_id),), fetch=True)[0]
    msg = f"Olá, {bill['cliente']}. Sua mensalidade contábil da competência {bill['competencia']} vence em {datetime.strptime(bill['vencimento'], '%Y-%m-%d').strftime('%d/%m/%Y')}, no valor de {to_brl(bill['valor'])}."
    wlink = whatsapp_link(bill["telefone"], msg)

    x, y = st.columns(2)
    with x:
        if wlink:
            st.link_button("Enviar cobrança por WhatsApp", wlink, use_container_width=True)
        else:
            st.warning("Cliente sem telefone válido.")
    with y:
        if bill["email"]:
            subject = f"Cobrança contábil {bill['competencia']}"
            mailto = f"mailto:{bill['email']}?subject={urllib.parse.quote(subject)}&body={urllib.parse.quote(msg)}"
            st.link_button("Enviar cobrança por e-mail", mailto, use_container_width=True)
        else:
            st.warning("Cliente sem e-mail cadastrado.")

    with st.form("atualizar_cobranca"):
        status = st.selectbox("Status", ["Pendente", "Pago", "Atrasado"], index=["Pendente", "Pago", "Atrasado"].index(bill["status"]))
        pago_em = st.text_input("Pago em (AAAA-MM-DD)", value=bill["pago_em"] or "")
        forma = st.text_input("Forma de pagamento", value=bill["forma_pagamento"] or "")
        obs = st.text_area("Observações", value=bill["observacoes"] or "")
        sub = st.form_submit_button("Atualizar cobrança")
    if sub:
        execute("UPDATE billing SET status=?, pago_em=?, forma_pagamento=?, observacoes=? WHERE id=?", (status, pago_em, forma, obs, selected_id))
        if status == "Pago":
            existe = execute("SELECT COUNT(*) n FROM financial_entries WHERE tipo='Receita' AND client_id=? AND competencia=?", (bill["client_id"], bill["competencia"]), fetch=True)[0]["n"]
            if existe == 0:
                execute(
                    "INSERT INTO financial_entries (data, tipo, categoria, descricao, valor, client_id, competencia, forma_pagamento, observacoes) VALUES (?, 'Receita', 'Honorários', ?, ?, ?, ?, ?, ?)",
                    (pago_em or today_str(), f"Recebimento de honorários - {bill['cliente']}", bill["valor"], bill["client_id"], bill["competencia"], forma, obs),
                )
        st.success("Cobrança atualizada.")
        st.rerun()

def tasks_tab():
    st.subheader("Tarefas mensais")
    comp = st.text_input("Competência das tarefas (AAAA-MM)", value=competencia_atual(), key="comp_tasks")
    a, b = st.columns([1, 2])
    with a:
        if st.button("Gerar tarefas da competência", use_container_width=True):
            qtd = generate_monthly_tasks(comp)
            st.success(f"{qtd} tarefas criadas.")
            st.rerun()
    with b:
        st.caption("Baseado no modelo padrão de obrigações e rotinas mensais.")

    rows = df("""
        SELECT t.id, c.nome AS cliente, t.competencia, t.nome_tarefa, t.obrigacao, t.setor, t.vencimento, t.status, t.concluida_em
        FROM tasks t JOIN clients c ON c.id=t.client_id
        WHERE t.competencia=?
        ORDER BY t.vencimento, c.nome, t.nome_tarefa
    """, (comp,))
    if rows.empty:
        st.info("Nenhuma tarefa encontrada.")
        return
    st.dataframe(rows, use_container_width=True, hide_index=True)

    task_id = st.selectbox("Selecionar tarefa", rows["id"].tolist(), format_func=lambda x: f"{x} - {rows.loc[rows['id']==x, 'cliente'].iloc[0]} - {rows.loc[rows['id']==x, 'nome_tarefa'].iloc[0]}")
    task = execute("SELECT * FROM tasks WHERE id=?", (int(task_id),), fetch=True)[0]
    with st.form("update_task"):
        status = st.selectbox("Status", ["Pendente", "Em andamento", "Concluída"], index=["Pendente", "Em andamento", "Concluída"].index(task["status"]))
        concl = st.text_input("Concluída em (AAAA-MM-DD)", value=task["concluida_em"] or "")
        obs = st.text_area("Observações", value=task["observacoes"] or "")
        submit = st.form_submit_button("Atualizar tarefa")
    if submit:
        execute("UPDATE tasks SET status=?, concluida_em=?, observacoes=? WHERE id=?", (status, concl, obs, task_id))
        st.success("Tarefa atualizada.")
        st.rerun()

    st.markdown("#### Modelos de tarefas")
    templ = df("SELECT * FROM task_templates ORDER BY nome_tarefa")
    st.dataframe(templ, use_container_width=True, hide_index=True)

def financial_tab():
    st.subheader("Financeiro")
    with st.expander("➕ Novo lançamento"):
        clientes = execute("SELECT id, nome FROM clients ORDER BY nome", fetch=True)
        client_options = {0: "Sem cliente"} | {r["id"]: r["nome"] for r in clientes}
        with st.form("novo_lancamento"):
            c1, c2, c3, c4 = st.columns(4)
            data = c1.text_input("Data (AAAA-MM-DD)", value=today_str())
            tipo = c2.selectbox("Tipo", ["Receita", "Despesa"])
            categoria = c3.text_input("Categoria", value="Honorários" if tipo == "Receita" else "")
            valor = c4.number_input("Valor", min_value=0.0, step=50.0)
            c5, c6, c7 = st.columns(3)
            descricao = c5.text_input("Descrição")
            client_id = c6.selectbox("Cliente", list(client_options.keys()), format_func=lambda x: client_options[x])
            comp = c7.text_input("Competência", value=competencia_atual())
            forma = st.text_input("Forma de pagamento")
            obs = st.text_area("Observações")
            save = st.form_submit_button("Salvar lançamento")
        if save:
            execute(
                "INSERT INTO financial_entries (data, tipo, categoria, descricao, valor, client_id, competencia, forma_pagamento, observacoes) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (data, tipo, categoria, descricao, valor, None if client_id == 0 else client_id, comp, forma, obs),
            )
            st.success("Lançamento salvo.")
            st.rerun()

    lanc = df("""
        SELECT f.id, f.data, f.tipo, f.categoria, f.descricao, f.valor, COALESCE(c.nome,'') cliente, f.competencia, f.forma_pagamento
        FROM financial_entries f LEFT JOIN clients c ON c.id=f.client_id
        ORDER BY f.data DESC, f.id DESC
    """)
    if lanc.empty:
        st.info("Nenhum lançamento.")
        return
    st.dataframe(lanc, use_container_width=True, hide_index=True)
    receitas = float(lanc.loc[lanc["tipo"] == "Receita", "valor"].sum())
    despesas = float(lanc.loc[lanc["tipo"] == "Despesa", "valor"].sum())
    saldo = receitas - despesas
    a, b, c = st.columns(3)
    a.metric("Receitas", to_brl(receitas))
    b.metric("Despesas", to_brl(despesas))
    c.metric("Saldo", to_brl(saldo))

def documents_tab():
    st.subheader("Documentos")
    clients = execute("SELECT id, nome FROM clients ORDER BY nome", fetch=True)
    if not clients:
        st.info("Cadastre clientes antes de enviar documentos.")
        return
    options = {r["id"]: r["nome"] for r in clients}

    with st.expander("📎 Enviar documento"):
        with st.form("upload_doc_form"):
            client_id = st.selectbox("Cliente", list(options.keys()), format_func=lambda x: options[x])
            categoria = st.text_input("Categoria", value="Contrato")
            file = st.file_uploader("Arquivo")
            submit = st.form_submit_button("Salvar documento")
        if submit:
            if not file:
                st.error("Selecione um arquivo.")
            else:
                client_folder = DOCS_DIR / f"cliente_{client_id}"
                client_folder.mkdir(exist_ok=True)
                dest = client_folder / file.name
                with open(dest, "wb") as f:
                    f.write(file.read())
                execute("INSERT INTO documents (client_id, nome_arquivo, caminho, categoria) VALUES (?, ?, ?, ?)", (client_id, file.name, str(dest), categoria))
                st.success("Documento salvo.")
                st.rerun()

    docs = df("SELECT d.id, c.nome AS cliente, d.nome_arquivo, d.categoria, d.enviado_em, d.caminho FROM documents d JOIN clients c ON c.id=d.client_id ORDER BY d.enviado_em DESC")
    if docs.empty:
        st.info("Nenhum documento enviado.")
        return
    st.dataframe(docs[["id", "cliente", "nome_arquivo", "categoria", "enviado_em"]], use_container_width=True, hide_index=True)
    doc_id = st.selectbox("Selecionar documento", docs["id"].tolist(), format_func=lambda x: f"{x} - {docs.loc[docs['id']==x,'cliente'].iloc[0]} - {docs.loc[docs['id']==x,'nome_arquivo'].iloc[0]}")
    selected = docs[docs["id"] == doc_id].iloc[0]
    path = Path(selected["caminho"])
    if path.exists():
        with open(path, "rb") as f:
            st.download_button("⬇️ Baixar documento", data=f.read(), file_name=selected["nome_arquivo"])

def reports_tab():
    st.subheader("Relatórios")
    op = st.selectbox("Tipo de relatório", ["Clientes", "Cobranças", "Tarefas", "Financeiro"])
    comp = st.text_input("Competência para filtro (AAAA-MM)", value=competencia_atual(), key="rel_comp")

    if op == "Clientes":
        data = df("SELECT nome, cnpj_cpf, responsavel, telefone, email, regime, honorarios, vencimento, status FROM clients ORDER BY nome")
    elif op == "Cobranças":
        data = df("SELECT c.nome AS cliente, b.competencia, b.vencimento, b.valor, b.status, b.pago_em, b.forma_pagamento FROM billing b JOIN clients c ON c.id=b.client_id WHERE b.competencia=? ORDER BY c.nome", (comp,))
    elif op == "Tarefas":
        data = df("SELECT c.nome AS cliente, t.competencia, t.nome_tarefa, t.obrigacao, t.setor, t.vencimento, t.status, t.concluida_em FROM tasks t JOIN clients c ON c.id=t.client_id WHERE t.competencia=? ORDER BY c.nome, t.nome_tarefa", (comp,))
    else:
        data = df("SELECT f.data, f.tipo, f.categoria, f.descricao, f.valor, COALESCE(c.nome,'') AS cliente, f.competencia, f.forma_pagamento FROM financial_entries f LEFT JOIN clients c ON c.id=f.client_id WHERE f.competencia=? ORDER BY f.data", (comp,))

    if data.empty:
        st.info("Sem dados para esse relatório.")
    else:
        st.dataframe(data, use_container_width=True, hide_index=True)
        csv = data.to_csv(index=False).encode("utf-8-sig")
        st.download_button("⬇️ Exportar CSV", data=csv, file_name=f"relatorio_{op.lower()}_{comp}.csv", mime="text/csv")

def settings_tab():
    st.subheader("Configurações")
    with st.form("settings_form"):
        office_name = st.text_input("Nome do escritório", value=get_setting("office_name"))
        office_whatsapp = st.text_input("WhatsApp do escritório", value=get_setting("office_whatsapp"))
        office_email = st.text_input("E-mail do escritório", value=get_setting("office_email"))
        logo_text = st.text_input("Texto da marca", value=get_setting("logo_text"))
        save = st.form_submit_button("Salvar configurações")
    if save:
        set_setting("office_name", office_name)
        set_setting("office_whatsapp", office_whatsapp)
        set_setting("office_email", office_email)
        set_setting("logo_text", logo_text)
        st.success("Configurações salvas.")

    users = df("SELECT id, username, full_name, role FROM users ORDER BY username")
    st.dataframe(users, use_container_width=True, hide_index=True)
    with st.expander("➕ Novo usuário"):
        with st.form("new_user"):
            username = st.text_input("Usuário")
            full_name = st.text_input("Nome completo")
            pwd = st.text_input("Senha", type="password")
            role = st.selectbox("Perfil", ["admin", "operador"])
            save_user = st.form_submit_button("Criar usuário")
        if save_user:
            try:
                execute("INSERT INTO users (username, password_hash, full_name, role) VALUES (?, ?, ?, ?)", (username, hash_password(pwd), full_name, role))
                st.success("Usuário criado.")
                st.rerun()
            except sqlite3.IntegrityError:
                st.error("Usuário já existe.")

def client_portal():
    client = st.session_state.portal_client
    st.title(f"Portal do cliente — {client['nome']}")
    cobr = df("SELECT competencia, vencimento, valor, status, pago_em FROM billing WHERE client_id=? ORDER BY competencia DESC", (client["id"],))
    tarefas = df("SELECT competencia, nome_tarefa, vencimento, status, concluida_em FROM tasks WHERE client_id=? ORDER BY competencia DESC, nome_tarefa", (client["id"],))
    docs = df("SELECT nome_arquivo, categoria, enviado_em, caminho FROM documents WHERE client_id=? ORDER BY enviado_em DESC", (client["id"],))

    a, b = st.columns(2)
    with a:
        st.markdown("#### Minhas cobranças")
        st.dataframe(cobr, use_container_width=True, hide_index=True) if not cobr.empty else st.info("Sem cobranças.")
    with b:
        st.markdown("#### Minhas tarefas")
        st.dataframe(tarefas, use_container_width=True, hide_index=True) if not tarefas.empty else st.info("Sem tarefas.")

    st.markdown("#### Meus documentos")
    if docs.empty:
        st.info("Sem documentos disponíveis.")
    else:
        for _, row in docs.iterrows():
            p = Path(row["caminho"])
            if p.exists():
                with open(p, "rb") as f:
                    st.download_button(f"Baixar {row['nome_arquivo']}", data=f.read(), file_name=row["nome_arquivo"], key=f"doc_{row['nome_arquivo']}_{row['enviado_em']}")

# ----------------- Main -----------------
if modo == "Escritório":
    if not st.session_state.user:
        login_screen()
    else:
        st.title("📊 Contab North Consultorias")
        st.caption("Cadastro, cobranças, tarefas, financeiro, documentos, relatórios e portal do cliente")
        tabs = st.tabs(["Dashboard", "Clientes", "Cobranças", "Tarefas", "Financeiro", "Documentos", "Relatórios", "Configurações"])
        with tabs[0]:
            dashboard_tab()
        with tabs[1]:
            clients_tab()
        with tabs[2]:
            billing_tab()
        with tabs[3]:
            tasks_tab()
        with tabs[4]:
            financial_tab()
        with tabs[5]:
            documents_tab()
        with tabs[6]:
            reports_tab()
        with tabs[7]:
            settings_tab()
else:
    if not st.session_state.portal_client:
        portal_login_screen()
    else:
        client_portal()
