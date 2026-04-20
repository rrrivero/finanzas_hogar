import streamlit as st
import pandas as pd
import psycopg2
from psycopg2 import pool
import bcrypt
import os
import io
import calendar
from dotenv import load_dotenv

# =========================
# CONFIG UI
# =========================
st.set_page_config(page_title="Finanzas", layout="wide")

# =========================
# CARGAR ENV
# =========================
load_dotenv()

# ✅ SOLUCIÓN ERROR SECRETS
try:
    DATABASE_URL = st.secrets["DATABASE_URL"]
except:
    DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    st.error("❌ Falta DATABASE_URL en .env o secrets")
    st.stop()

# =========================
# POOL DB
# =========================
@st.cache_resource
def get_pool():
    return psycopg2.pool.SimpleConnectionPool(1, 5, dsn=DATABASE_URL)

pool_conn = get_pool()

def run_query(query, params=None, fetch=False):
    conn = pool_conn.getconn()
    try:
        cur = conn.cursor()
        cur.execute(query, params)

        if fetch:
            data = cur.fetchall()
        else:
            data = None

        conn.commit()
        cur.close()
        return data

    except Exception as e:
        conn.rollback()
        st.error(f"Error DB: {e}")

    finally:
        pool_conn.putconn(conn)

# =========================
# TABLAS
# =========================
run_query("""
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    usuario TEXT UNIQUE,
    password TEXT
)
""")

run_query("""
CREATE TABLE IF NOT EXISTS movimientos (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER,
    fecha DATE,
    tipo TEXT,
    categoria TEXT,
    monto NUMERIC(10,2)
)
""")

run_query("""
CREATE TABLE IF NOT EXISTS categorias (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER,
    nombre TEXT
)
""")

run_query("""
CREATE TABLE IF NOT EXISTS presupuestos (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER,
    categoria TEXT,
    mes TEXT,
    monto NUMERIC(10,2)
)
""")

# =========================
# SESSION
# =========================
if "usuario_id" not in st.session_state:
    st.session_state.usuario_id = None

# =========================
# LOGIN
# =========================
if not st.session_state.usuario_id:

    st.title("💰 Finanzas - Login")

    usuario = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if st.button("Entrar"):
        data = run_query(
            "SELECT id,password FROM usuarios WHERE usuario=%s",
            (usuario,), True
        )

        if data:
            uid, pw = data[0]

            if pw and pw.startswith("$2b$"):
                if bcrypt.checkpw(password.encode(), pw.encode()):
                    st.session_state.usuario_id = uid
                    st.rerun()

        st.error("Credenciales incorrectas")

    st.divider()

    if st.button("Crear usuario"):
        if usuario and password:
            hashp = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()

            run_query(
                "INSERT INTO usuarios (usuario,password) VALUES (%s,%s)",
                (usuario, hashp)
            )

            st.success("Usuario creado")

# =========================
# APP PRINCIPAL
# =========================
else:

    uid = st.session_state.usuario_id

    st.sidebar.title("📌 Menú")
    menu = st.sidebar.radio(
        "Ir a",
        ["Dashboard","Movimientos","Categorías","Presupuesto"]
    )

    if st.sidebar.button("Cerrar sesión"):
        st.session_state.usuario_id = None
        st.rerun()

    # =========================
    # CARGAR DATA
    # =========================
    data = run_query(
        "SELECT * FROM movimientos WHERE usuario_id=%s",
        (uid,), True
    )

    df = pd.DataFrame(
        data,
        columns=["id","usuario_id","fecha","tipo","categoria","monto"]
    ) if data else pd.DataFrame()

    if not df.empty:
        df["fecha"] = pd.to_datetime(df["fecha"])
        df["mes"] = df["fecha"].dt.to_period("M")

    # =========================
    # DASHBOARD
    # =========================
    if menu == "Dashboard":

        st.title("📊 Dashboard")

        if not df.empty:

            ingresos = df[df.tipo=="Ingreso"].monto.sum()
            gastos = df[df.tipo=="Gasto"].monto.sum()

            col1,col2,col3 = st.columns(3)
            col1.metric("Ingresos", ingresos)
            col2.metric("Gastos", gastos)
            col3.metric("Ahorro", ingresos-gastos)

            # 🔮 Predicción global
            hoy = pd.Timestamp.today()
            gastos_mes = df[
                (df.tipo=="Gasto") &
                (df.mes==hoy.to_period("M"))
            ]

            gasto_actual = gastos_mes.monto.sum()
            dias_mes = calendar.monthrange(hoy.year,hoy.month)[1]

            estimado = (gasto_actual/hoy.day)*dias_mes if hoy.day>0 else 0

            st.subheader("🔮 Predicción mensual")
            st.metric("Estimado fin de mes", round(estimado,2))

            # 🔮 por categoría
            st.subheader("📊 Predicción por categoría")

            gasto_cat = gastos_mes.groupby("categoria")["monto"].sum()

            pred = {
                c:(m/hoy.day)*dias_mes
                for c,m in gasto_cat.items()
            } if hoy.day>0 else {}

            df_pred = pd.DataFrame({
                "Actual": gasto_cat,
                "Estimado": pd.Series(pred)
            }).fillna(0)

            st.dataframe(df_pred.round(2))
            st.bar_chart(df_pred)

    # =========================
    # MOVIMIENTOS
    # =========================
    elif menu == "Movimientos":

        st.title("📜 Movimientos")

        tipo = st.selectbox("Tipo",["Ingreso","Gasto"])
        monto = st.number_input("Monto", min_value=0.0)
        categoria = st.text_input("Categoría")
        fecha = st.date_input("Fecha")

        if st.button("Guardar"):
            run_query("""
                INSERT INTO movimientos
                (usuario_id,fecha,tipo,categoria,monto)
                VALUES (%s,%s,%s,%s,%s)
            """,(uid,str(fecha),tipo,categoria,monto))
            st.rerun()

        st.subheader("Historial")

        f1,f2 = st.columns(2)
        desde = f1.date_input("Desde")
        hasta = f2.date_input("Hasta")

        df_f = df.copy()

        if not df.empty:
            if desde:
                df_f = df_f[df_f.fecha>=pd.to_datetime(desde)]
            if hasta:
                df_f = df_f[df_f.fecha<=pd.to_datetime(hasta)]

        st.dataframe(df_f)

        # eliminar
        id_del = st.number_input("ID eliminar", step=1)
        if st.button("Eliminar"):
            run_query(
                "DELETE FROM movimientos WHERE id=%s AND usuario_id=%s",
                (id_del,uid)
            )
            st.rerun()

        # editar
        id_ed = st.number_input("ID editar", step=1)
        new_m = st.number_input("Nuevo monto", min_value=0.0)

        if st.button("Actualizar"):
            run_query(
                "UPDATE movimientos SET monto=%s WHERE id=%s AND usuario_id=%s",
                (new_m,id_ed,uid)
            )
            st.rerun()

        # exportar
        if not df_f.empty:
            buffer = io.BytesIO()
            df_f.to_excel(buffer, index=False)

            st.download_button(
                "📤 Descargar Excel",
                buffer.getvalue(),
                "finanzas.xlsx"
            )

    # =========================
    # CATEGORIAS
    # =========================
    elif menu == "Categorías":

        st.title("🏷️ Categorías")

        nueva = st.text_input("Nueva categoría")

        if st.button("Agregar"):
            run_query(
                "INSERT INTO categorias (usuario_id,nombre) VALUES (%s,%s)",
                (uid,nueva)
            )
            st.rerun()

        cats = run_query(
            "SELECT nombre FROM categorias WHERE usuario_id=%s",
            (uid,), True
        )

        st.write(cats)

    # =========================
    # PRESUPUESTO + ALERTAS
    # =========================
    elif menu == "Presupuesto":

        st.title("💰 Presupuesto")

        mes = str(pd.Timestamp.today().to_period("M"))

        cat = st.text_input("Categoría")
        monto = st.number_input("Monto", min_value=0.0)

        if st.button("Guardar presupuesto"):
            run_query("""
                INSERT INTO presupuestos
                (usuario_id,categoria,mes,monto)
                VALUES (%s,%s,%s,%s)
            """,(uid,cat,mes,monto))
            st.rerun()

        pres = run_query("""
            SELECT categoria,monto
            FROM presupuestos
            WHERE usuario_id=%s AND mes=%s
        """,(uid,mes),True)

        if pres and not df.empty:

            gastos_mes = df[
                (df.tipo=="Gasto") &
                (df.mes==pd.Timestamp.today().to_period("M"))
            ]

            st.subheader("🚨 Alertas")

            for c,p in pres:
                g = gastos_mes[gastos_mes.categoria==c].monto.sum()

                if g >= p:
                    st.error(f"❌ {c}: {g}/{p}")
                elif g >= p*0.8:
                    st.warning(f"⚠️ {c}: {g}/{p}")
                else:
                    st.success(f"✅ {c}: {g}/{p}")
