import streamlit as st
import pandas as pd
import psycopg2
import time
from datetime import date
from supabase import create_client, Client

# Config. da pagina
st.set_page_config(
    page_title="Starbank Vendas",
    page_icon="💠",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- CSS CYBER ---
st.markdown("""
    <style>
        @import url('https://fonts.googleapis.com/css2?family=Rajdhani:wght@400;600;700&family=Inter:wght@300;400;600&display=swap');
        .stAppDeployButton { display: none; }
        header[data-testid="stHeader"] { background-color: transparent !important; }
        html, body, [class*="css"] { font-family: 'Rajdhani', sans-serif; }
        
        /* TICKER */
        .ticker-wrap { width: 100%; overflow: hidden; background-color: rgba(0, 0, 0, 0.6); border-y: 1px solid #00d4ff; padding: 10px 0; margin-bottom: 20px; }
        .ticker { display: inline-block; padding-left: 100%; animation: ticker-anim 30s linear infinite; } 
        .ticker__item { display: inline-block; padding: 0 2rem; font-size: 1.2rem; color: #FFFFFF; font-weight: bold; text-shadow: 0 0 5px #00ff41; }
        @keyframes ticker-anim { 0% { transform: translate3d(0, 0, 0); } 100% { transform: translate3d(-100%, 0, 0); } }

        /* CARDS E BANNER */
        .cyber-banner { padding: 20px; border-radius: 12px; background: rgba(10, 10, 30, 0.8); border: 1px solid; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        div[data-testid="stMetric"] { background: rgba(5, 15, 30, 0.7); border: 1px solid rgba(0, 212, 255, 0.2); border-radius: 12px; padding: 20px; }
        div[data-testid="stMetricLabel"] { color: #00d4ff !important; }
        
        /* LOGIN ESTILIZADO */
        .holo-container { background: rgba(255, 255, 255, 0.05); border-radius: 20px; padding: 40px; border: 1px solid rgba(0, 212, 255, 0.3); text-align: center; }
    </style>
""", unsafe_allow_html=True)

# --- CONEXÃO DUPLA (SUPABASE AUTH + POSTGRES DATA) ---

# 1. Cliente Supabase (Para Login/Auth e Criação de Usuários)
@st.cache_resource
def init_supabase():
    url = st.secrets["supabase"]["url"]
    key = st.secrets["supabase"]["key"]
    return create_client(url, key)

supabase = init_supabase()

# 2. Conexão Postgres (Para Banco de Dados de Vendas - Mantemos pela performance de analytics)
def init_connection():
    try: return psycopg2.connect(**st.secrets["connections"]["postgresql"])
    except: return None

def run_query(query, params=None):
    conn = init_connection()
    if conn:
        try:
            with conn.cursor() as cur:
                cur.execute(query, params)
                conn.commit()
                if query.strip().upper().startswith("SELECT"): return cur.fetchall()
        except Exception as e: st.error(f"Erro DB: {e}")
        finally: conn.close()
    return None

def init_db():
    # Garante que a tabela de vendas existe
    run_query("""
        CREATE TABLE IF NOT EXISTS vendas (
            id SERIAL PRIMARY KEY,
            username TEXT,
            data DATE,
            cliente TEXT,
            convenio TEXT,
            produto TEXT,
            valor NUMERIC(10,2)
        );
    """)

# --- LÓGICA DE AUTENTICAÇÃO INTELIGENTE ---
def formatar_login(input_user):
    """
    Se o usuário digitar 'Christian', vira 'christian@starbank.com.br'
    Se digitar 'christian@gmail.com', bloqueia.
    """
    input_user = input_user.strip().lower()
    if "@" in input_user:
        if "@starbank" in input_user: # Aceita variações como .com ou .com.br
            return input_user
        else:
            return None # Email inválido
    else:
        # Se digitou só nome, cria o email fake institucional
        return f"{input_user.replace(' ', '.')}@starbank.com.br"

def login_supabase(email_input, password):
    email_real = formatar_login(email_input)
    if not email_real:
        return None, "❌ Use um email @starbank ou apenas seu Nome."
    
    try:
        # Tenta logar usando a API de Auth do Supabase
        response = supabase.auth.sign_in_with_password({"email": email_real, "password": password})
        return response.user, None
    except Exception as e:
        return None, "Usuário ou senha incorretos."

def create_user_supabase(email_input, password):
    email_real = formatar_login(email_input)
    if not email_real:
        return "❌ Permitido apenas para equipe Starbank (@starbank)."
    
    try:
        # Cria usuário no painel Authentication
        supabase.auth.sign_up({"email": email_real, "password": password})
        return "✅ Usuário criado! Pode fazer login."
    except Exception as e:
        return f"Erro ao criar: {str(e)}"

# --- LÓGICA DE METAS E COMISSÃO ---
def calcular_comissao_tier(total):
    if total >= 150000: return total * 0.0150 
    elif total >= 101000: return total * 0.0125 
    elif total >= 80000: return total * 0.0100 
    elif total >= 50000: return total * 0.0050 
    else: return 0.0

def definir_meta_atual(total):
    if total < 50000: return 50000.00
    elif total < 80000: return 80000.00
    elif total < 101000: return 101000.00
    elif total < 150000: return 150000.00
    else: return 200000.00

def get_motivational_data(total):
    if total >= 150000: return "DIAMANTE (MAX)", "#b9f2ff", "LENDÁRIO! COMISSÃO MÁXIMA DE 1.5%", "💎"
    elif total >= 101000: return "PLATINA", "#E5E4E2", "EXCELENTE! COMISSÃO DE 1.25%", "💠"
    elif total >= 80000: return "OURO", "#FFD700", "MUITO BEM! COMISSÃO DE 1.00%", "🥇"
    elif total >= 50000: return "PRATA", "#C0C0C0", "COMISSÃO ATIVADA (0.50%)!", "⛓️"
    else: return "BRONZE", "#cd7f32", "Acelere para ativar a comissão nos 50k!", "🥉"

def get_streak(username):
    # Extrai o nome do email para buscar no banco de dados antigo
    nome_busca = username.split('@')[0].replace('.', ' ')
    res = run_query(f"SELECT DISTINCT data FROM vendas WHERE username ILIKE '{nome_busca}%' ORDER BY data DESC")
    if not res: return 0
    return len(res)

def get_global_ticker_data():
    res = run_query("SELECT username, SUM(valor) as total FROM vendas GROUP BY username HAVING SUM(valor) >= 50000 ORDER BY total DESC")
    if not res: return ["🚀 A CORRIDA PELOS 50K ESTÁ ON! BORA VENDER!"]
    msgs = []
    for row in res:
        # Limpa o nome (remove email se houver)
        user_nome = row[0].split('@')[0].replace('.', ' ').upper()
        total_user = float(row[1]) 
        if total_user >= 150000: msgs.append(f"💎 {user_nome} BATEU A META DE 150 MIL!")
        elif total_user >= 101000: msgs.append(f"💠 {user_nome} BATEU A META DE 101 MIL!")
        elif total_user >= 80000: msgs.append(f"🥇 {user_nome} BATEU A META DE 80 MIL!")
        elif total_user >= 50000: msgs.append(f"🥈 {user_nome} BATEU A META DE 50 MIL!")
    return msgs

def add_venda(username, data, cliente, convenio, produto, valor):
    # Salva usando o nome limpo (Ex: christian.serello) para ficar bonito no banco
    nome_banco = username.split('@')[0].replace('.', ' ').title()
    run_query("INSERT INTO vendas(username, data, cliente, convenio, produto, valor) VALUES (%s, %s, %s, %s, %s, %s)", 
              (nome_banco, str(data), cliente, convenio, produto, valor))

def delete_venda(venda_id):
    run_query("DELETE FROM vendas WHERE id = %s", (venda_id,))

def get_all_users():
    # Busca usuários que já venderam alguma vez
    res = run_query("SELECT DISTINCT username FROM vendas")
    return [r[0] for r in res] if res else []

def get_vendas_df(target_user=None):
    conn = init_connection()
    if conn:
        query = "SELECT id, username, data, cliente, convenio, produto, valor FROM vendas"
        if target_user and target_user != "Todos":
            # Filtro ILIKE para pegar variações de nome
            nome_filtro = target_user.split('@')[0].replace('.', ' ')
            df = pd.read_sql(query + f" WHERE username ILIKE '%%{nome_filtro}%%'", conn)
        else:
            df = pd.read_sql(query, conn)
        conn.close()
        return df
    return pd.DataFrame()

# --- INICIALIZAÇÃO ---
init_db()

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
    st.session_state['user_email'] = ''

if 'ultimo_nivel_comemorado' not in st.session_state:
    st.session_state['ultimo_nivel_comemorado'] = 0

# --- TELA DE LOGIN ---
if not st.session_state['logged_in']:
    c1, c2, c3 = st.columns([1, 2, 1])
    with c2:
        st.markdown("<br><br>", unsafe_allow_html=True)
        st.markdown('<div class="holo-container">', unsafe_allow_html=True)
        st.markdown('<h1 style="color:white; font-family: Rajdhani; letter-spacing: 3px;">STARBANK</h1>', unsafe_allow_html=True)
        st.markdown('<p style="color:#00d4ff;">/// Acesso Seguro v14.0 ///</p>', unsafe_allow_html=True)
        
        tab1, tab2 = st.tabs(["ENTRAR", "REGISTRAR"])
        with tab1:
            u = st.text_input("Usuário ou Email Starbank", key="l_u", placeholder="Ex: christian ou christian@starbank...")
            p = st.text_input("Senha", type="password", key="l_p")
            if st.button("CONECTAR >>>", type="primary"):
                user, error = login_supabase(u, p)
                if user:
                    st.session_state['logged_in'] = True
                    st.session_state['user_email'] = user.email
                    # Define cargo básico (no futuro pode vir do metadata do supabase)
                    st.session_state['role'] = 'admin' if 'admin' in user.email else 'operador'
                    st.rerun()
                else: st.error(error)
        with tab2:
            st.info("Crie seu acesso. Use seu nome (Ex: 'Ana Silva') ou email corporativo.")
            nu = st.text_input("Seu Nome ou Email", key="n_u")
            np = st.text_input("Crie uma Senha", type="password", key="n_p")
            if st.button("CRIAR CONTA"):
                msg = create_user_supabase(nu, np)
                if "✅" in msg: st.success(msg)
                else: st.error(msg)
        st.markdown('</div>', unsafe_allow_html=True)

else:
    # --- DASHBOARD ---
    user_email = st.session_state['user_email']
    user_display = user_email.split('@')[0].replace('.', ' ').title() # Nome Bonito
    role = st.session_state['role']

    # TICKER
    ticker_msgs = get_global_ticker_data()
    st.markdown(f"""<div class="ticker-wrap"><div class="ticker">{' &nbsp;&nbsp;&nbsp;&nbsp; /// &nbsp;&nbsp;&nbsp;&nbsp; '.join([f'<div class="ticker__item">{m}</div>' for m in ticker_msgs])}</div></div>""", unsafe_allow_html=True)

    with st.sidebar:
        st.markdown(f"<h2 style='color: #00d4ff;'>👤 {user_display}</h2>", unsafe_allow_html=True)
        st.caption(f"ID: {user_email}")
        
        streak_count = get_streak(user_email)
        st.markdown(f"""<div style="background: rgba(255,255,255,0.05); padding: 10px; border-radius: 8px; border: 1px solid #FF4500; margin-bottom: 20px;"><h3 style="margin:0; color: #FF4500; text-align: center;">🔥 DIAS ATIVOS: {streak_count}</h3></div>""", unsafe_allow_html=True)
        
        st.divider()
        st.markdown("### 💠 NOVA TRANSAÇÃO")
        with st.form("venda"):
            d = st.date_input("DATA", date.today())
            c = st.text_input("CLIENTE")
            co = st.text_input("CONVÊNIO")
            p = st.selectbox("PRODUTO", ["EMPRÉSTIMO", "CARTÃO RMC", "BENEFICIO"])
            v = st.number_input("VALOR (R$)", min_value=0.0, value=None, placeholder="0.00")
            
            if st.form_submit_button("PROCESSAR DADOS 🚀"):
                val_final = v if v is not None else 0.0
                if val_final > 0:
                    add_venda(user_email, d, c, co, p, val_final)
                    st.toast("Salvo!", icon="💾")
                    time.sleep(0.5)
                    st.rerun()
                else: st.warning("Digite um valor válido!")
        
        if st.button("SAIR"):
            supabase.auth.sign_out()
            st.session_state['logged_in'] = False
            st.rerun()

    # ÁREA PRINCIPAL
    filtro = user_email
    # Lógica simples de admin: se email contiver 'admin' ou for um dos chefes conhecidos
    admins = ["maicon", "brunno", "fernanda", "nair"]
    is_admin = any(x in user_email for x in admins)
    
    if is_admin:
        col_admin, _ = st.columns([1, 3])
        with col_admin:
            op = ["Todos"] + get_all_users()
            sel = st.selectbox("VISÃO SUPERVISOR:", op)
            filtro = "Todos" if sel == "Todos" else sel

    df = get_vendas_df(filtro)
    
    total = df['valor'].sum() if not df.empty else 0.0
    META_ATUAL = definir_meta_atual(total)
    comissao = calcular_comissao_tier(total)
    nivel, cor_nivel, msg, icone = get_motivational_data(total)

    st.markdown(f"""
        <div class="cyber-banner" style="border-color: {cor_nivel}; box-shadow: 0 0 20px {cor_nivel}40;">
            <h2 style="margin:0; color: white; letter-spacing: 2px;">{icone} STATUS: {filtro.split('@')[0].upper()}</h2>
            <p style="margin:10px 0 0 0; color: {cor_nivel}; font-size: 1.3em; font-weight: bold; text-shadow: 0 0 10px {cor_nivel};">
                NÍVEL: {nivel}
            </p>
            <p style="margin:0; color: #a0a0a0; font-style: italic;">/// {msg} ///</p>
        </div>
    """, unsafe_allow_html=True)

    col_prog, col_meta = st.columns([3, 1])
    with col_prog:
        progresso_pct = min(total / META_ATUAL, 1.0)
        st.markdown(f"<br>Please **PRÓXIMO ALVO: R$ {META_ATUAL:,.2f} ({progresso_pct*100:.1f}%)**", unsafe_allow_html=True)
        st.progress(progresso_pct)

    # Balões (só na visão do dono)
    if filtro == user_email:
        novo_nivel = 0
        if total >= 150000: novo_nivel = 150000
        elif total >= 101000: novo_nivel = 101000
        elif total >= 80000: novo_nivel = 80000
        elif total >= 50000: novo_nivel = 50000
        if novo_nivel > st.session_state['ultimo_nivel_comemorado']:
            st.balloons()
            st.toast(f"PARABÉNS! META DE {novo_nivel/1000:.0f}K BATIDA!", icon="🎉")
            st.session_state['ultimo_nivel_comemorado'] = novo_nivel

    st.markdown("<br>", unsafe_allow_html=True)
    k1, k2, k3, k4 = st.columns(4)
    k1.metric("VOLUME TOTAL", f"R$ {total:,.2f}", delta="Processado")
    k2.metric("COMISSÃO", f"R$ {comissao:,.2f}", delta=f"{(comissao/total*100) if total>0 else 0:.2f}%")
    k3.metric("FALTA", f"R$ {max(META_ATUAL-total, 0):,.2f}", delta_color="inverse")
    k4.metric("META ATUAL", f"R$ {META_ATUAL:,.2f}")

    st.divider()

    if not df.empty:
        c_chart, c_table = st.columns([1.5, 1])
        with c_chart:
            st.markdown("#### 📈 FLUXO")
            df['data'] = pd.to_datetime(df['data'])
            st.area_chart(df.groupby("data")["valor"].sum(), color=cor_nivel)
        with c_table:
            st.markdown("#### ⚡ TOP VENDAS")
            st.dataframe(df[['cliente', 'produto', 'valor']].sort_values(by='valor', ascending=False).head(5).style.format({"valor": "R$ {:,.2f}"}), use_container_width=True, hide_index=True)

        with st.expander("📂 ACESSAR BANCO DE DADOS COMPLETO"):
            st.dataframe(df.style.format({"valor": "R$ {:,.2f}"}), use_container_width=True)
            col_del, _ = st.columns([1, 3])
            with col_del:
                lista = df.apply(lambda x: f"ID {x['id']} - {x['cliente']}", axis=1)
                sel = st.selectbox("EXCLUIR:", lista)
                if st.button("🗑️ CONFIRMAR"):
                    id_real = int(sel.split(" - ")[0].replace("ID ", ""))
                    delete_venda(id_real)
                    st.rerun()
    else:
        st.info("NENHUM DADO REGISTRADO.")