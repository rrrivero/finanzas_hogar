import streamlit as st
import pandas as pd
import psycopg
from psycopg_pool import ConnectionPool
import bcrypt
import os
import io
import calendar
from datetime import datetime
from dotenv import load_dotenv

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Finanzas Pro", layout="wide")
load_dotenv()

# =========================
# DATABASE URL (FIX FINAL)
# =========================
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    try:
        DATABASE_URL = st.secrets["DATABASE_URL"]
    except Exception:
        pass

if not DATABASE_URL:
    st.error("❌ DATABASE_URL no configurada")
    st.stop()

# =========================
# CONNECTION POOL
# =========================
@st.cache_resource
def get_pool():
    return ConnectionPool(DATABASE_URL)

pool = get_pool()

def run_query(query, params=None, fetch=False):
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(query, params or ())
                if fetch:
                    return cur.fetchall()
                conn.commit()
    except Exception as e:
        st.error(f"DB Error: {e}")

# =========================
# CREATE TABLES
# =========================
run_query("""
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    usuario TEXT UNIQUE,
    password TEXT
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
CREATE TABLE IF NOT EXISTS movimientos (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER,
    fecha DATE,
    tipo TEXT,
    categoria TEXT,
    monto NUMERIC
)
""")

run_query("""
CREATE TABLE IF NOT EXISTS presupuestos (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER,
    categoria TEXT,
    monto NUMERIC
)
""")

# =========================
# SESSION
# =========================
if "user_id" not in st.session_state:
    st.session_state.user_id = None

# =========================
# LOGIN / REGISTER
# =========================
if not st.session_state.user_id:

    st.title("🔐 Finanzas del Hogar")

    opcion = st.selectbox("Acceso", ["Login", "Registro"])

    usuario = st.text_input("Usuario")
    password = st.text_input("Contraseña", type="password")

    if opcion == "Registro":
        if st.button("Crear cuenta"):
            if usuario and password:
                hashed = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
                try:
                    run_query(
                        "INSERT INTO usuarios (usuario,password) VALUES (%s,%s)",
                        (usuario, hashed)
                    )
                    st.success("Cuenta creada")
                except:
                    st.error("Usuario ya existe")

    else:
        if st.button("Entrar"):
            data = run_query(
                "SELECT id,password FROM usuarios WHERE usuario=%s",
                (usuario,),
                True
            )

            if data:
                uid, pw = data[0]
                if pw.startswith("$2b$") and bcrypt.checkpw(password.encode(), pw.encode()):
                    st.session_state.user_id = uid
                    st.rerun()
                else:
                    st.error("Contraseña incorrecta")
            else:
                st.error("Usuario no existe")

# =========================
# MAIN APP
# =========================
else:

    user_id = st.session_state.user_id

    st.sidebar.title("📌 Menú")
    menu = st.sidebar.radio("Ir a", ["Dashboard", "Movimientos", "Categorías", "Presupuesto"])

    if st.sidebar.button("Cerrar sesión"):
        st.session_state.user_id = None
        st.rerun()

    # =========================
    # LOAD DATA
    # =========================
    data = run_query(
        "SELECT id,fecha,tipo,categoria,monto FROM movimientos WHERE usuario_id=%s",
        (user_id,),
        True
    )

    df = pd.DataFrame(data, columns=["id","fecha","tipo","categoria","monto"]) if data else pd.DataFrame()

    if not df.empty:
        df["fecha"] = pd.to_datetime(df["fecha"])
        df["mes"] = df["fecha"].dt.to_period("M")

    # =========================
    # DASHBOARD
    # =========================
    if menu == "Dashboard":

        st.title("📊 Dashboard")

        if df.empty:
            st.warning("No hay datos")
        else:
            ingresos = df[df.tipo=="Ingreso"].monto.sum()
            gastos = df[df.tipo=="Gasto"].monto.sum()

            col1,col2,col3 = st.columns(3)
            col1.metric("Ingresos", ingresos)
            col2.metric("Gastos", gastos)
            col3.metric("Ahorro", ingresos-gastos)

            st.bar_chart(df.groupby("categoria")["monto"].sum())

            # 🔮 Predicción
            hoy = datetime.now()
            gastos_mes = df[(df.tipo=="Gasto") & (df.mes==pd.Period(hoy.strftime("%Y-%m")))]

            if not gastos_mes.empty:
                gasto_actual = gastos_mes.monto.sum()
                dias_mes = calendar.monthrange(hoy.year, hoy.month)[1]

                estimado = (gasto_actual / hoy.day) * dias_mes if hoy.day>0 else 0

                st.subheader("🔮 Predicción mensual")
                st.metric("Estimado fin de mes", round(estimado,2))

    # =========================
    # MOVIMIENTOS
    # =========================
    elif menu == "Movimientos":

        st.title("📜 Movimientos")

        tipo = st.selectbox("Tipo", ["Ingreso","Gasto"])
        monto = st.number_input("Monto", 0.0)
        categoria = st.text_input("Categoría")
        fecha = st.date_input("Fecha")

        if st.button("Guardar"):
            run_query("""
            INSERT INTO movimientos(usuario_id,fecha,tipo,categoria,monto)
            VALUES (%s,%s,%s,%s,%s)
            """,(user_id,fecha,tipo,categoria,monto))
            st.rerun()

        st.subheader("Historial")
        st.dataframe(df)

        # EDITAR
        st.subheader("Editar")
        eid = st.number_input("ID editar", 0)
        nuevo = st.number_input("Nuevo monto", 0.0)

        if st.button("Actualizar"):
            run_query("UPDATE movimientos SET monto=%s WHERE id=%s AND usuario_id=%s",
                      (nuevo,eid,user_id))
            st.rerun()

        # ELIMINAR
        did = st.number_input("ID eliminar", 0)
        if st.button("Eliminar"):
            run_query("DELETE FROM movimientos WHERE id=%s AND usuario_id=%s",
                      (did,user_id))
            st.rerun()

        # EXPORTAR
        if not df.empty:
            buffer = io.BytesIO()
            with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
                df.to_excel(writer, index=False)

            st.download_button("📥 Descargar Excel", buffer.getvalue(), "movimientos.xlsx")

    # =========================
    # CATEGORIAS
    # =========================
    elif menu == "Categorías":

        st.title("🏷 Categorías")

        nueva = st.text_input("Nueva categoría")

        if st.button("Agregar"):
            run_query("INSERT INTO categorias(usuario_id,nombre) VALUES (%s,%s)",
                      (user_id,nueva))
            st.rerun()

        cats = run_query("SELECT nombre FROM categorias WHERE usuario_id=%s",
                         (user_id,),True)

        if cats:
            st.write([c[0] for c in cats])

    # =========================
    # PRESUPUESTO
    # =========================
    elif menu == "Presupuesto":

        st.title("💰 Presupuesto")

        cat = st.text_input("Categoría")
        monto = st.number_input("Monto mensual", 0.0)

        if st.button("Guardar"):
            run_query("INSERT INTO presupuestos(usuario_id,categoria,monto) VALUES (%s,%s,%s)",
                      (user_id,cat,monto))
            st.rerun()

        pres = run_query("SELECT categoria,monto FROM presupuestos WHERE usuario_id=%s",
                         (user_id,),True)

        if pres and not df.empty:
            st.subheader("🚨 Alertas")

            gastos = df[df.tipo=="Gasto"]

            for c,p in pres:
                g = gastos[gastos.categoria==c].monto.sum()

                if g>=p:
                    st.error(f"{c}: EXCEDIDO {g}/{p}")
                elif g>=p*0.8:
                    st.warning(f"{c}: cerca {g}/{p}")
                else:
                    st.success(f"{c}: OK {g}/{p}")
