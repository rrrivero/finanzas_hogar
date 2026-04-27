import streamlit as st
import pandas as pd
import psycopg
from psycopg_pool import ConnectionPool
import bcrypt
import os
import io
from datetime import datetime
from dotenv import load_dotenv

# =========================
# CONFIG
# =========================
st.set_page_config(page_title="Finanzas Pro", layout="wide")
load_dotenv()

DATABASE_URL = st.secrets.get("DATABASE_URL") or os.getenv("DATABASE_URL")

if not DATABASE_URL:
    st.error("❌ DATABASE_URL no configurada")
    st.stop()

# =========================
# POOL
# =========================
@st.cache_resource
def get_pool():
    return ConnectionPool(DATABASE_URL)

pool = get_pool()

def query(q, params=None, fetch=False):
    with pool.connection() as conn:
        with conn.cursor() as cur:
            cur.execute(q, params or ())
            if fetch:
                return cur.fetchall()
            conn.commit()

# =========================
# TABLAS
# =========================
query("""
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    usuario TEXT UNIQUE,
    password TEXT
)
""")

query("""
CREATE TABLE IF NOT EXISTS categorias (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER,
    nombre TEXT
)
""")

query("""
CREATE TABLE IF NOT EXISTS movimientos (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER,
    fecha DATE,
    tipo TEXT,
    categoria TEXT,
    monto REAL
)
""")

query("""
CREATE TABLE IF NOT EXISTS presupuestos (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER,
    categoria TEXT,
    monto REAL
)
""")

# =========================
# LOGIN
# =========================
if "user" not in st.session_state:
    st.session_state.user = None

if not st.session_state.user:
    menu = st.selectbox("Acceso", ["Login", "Registro"])

    if menu == "Registro":
        u = st.text_input("Usuario")
        p = st.text_input("Password", type="password")

        if st.button("Crear cuenta"):
            hashed = bcrypt.hashpw(p.encode(), bcrypt.gensalt()).decode()
            try:
                query("INSERT INTO usuarios (usuario,password) VALUES (%s,%s)", (u, hashed))
                st.success("Cuenta creada")
            except:
                st.error("Usuario ya existe")

    else:
        u = st.text_input("Usuario")
        p = st.text_input("Password", type="password")

        if st.button("Entrar"):
            res = query("SELECT id,password FROM usuarios WHERE usuario=%s", (u,), True)
            if res:
                uid, hp = res[0]
                if bcrypt.checkpw(p.encode(), hp.encode()):
                    st.session_state.user = uid
                    st.rerun()
                else:
                    st.error("Password incorrecto")

# =========================
# APP
# =========================
else:
    user_id = st.session_state.user

    if st.sidebar.button("Cerrar sesión"):
        st.session_state.user = None
        st.rerun()

    menu = st.sidebar.radio("Menú", ["Dashboard", "Movimientos", "Categorías", "Presupuesto"])

    # =========================
    # CATEGORIAS
    # =========================
    if menu == "Categorías":
        st.title("Categorías")

        nueva = st.text_input("Nueva categoría")

        if st.button("Agregar"):
            query("INSERT INTO categorias (usuario_id,nombre) VALUES (%s,%s)", (user_id, nueva))
            st.success("Agregado")

        cats = query("SELECT nombre FROM categorias WHERE usuario_id=%s", (user_id,), True)
        st.write([c[0] for c in cats])

    # =========================
    # MOVIMIENTOS
    # =========================
    if menu == "Movimientos":
        st.title("Movimientos")

        tipo = st.selectbox("Tipo", ["Ingreso", "Gasto"])
        monto = st.number_input("Monto", 0.0)
        fecha = st.date_input("Fecha")

        cats = query("SELECT nombre FROM categorias WHERE usuario_id=%s", (user_id,), True)
        lista = [c[0] for c in cats] or ["General"]

        categoria = st.selectbox("Categoría", lista)

        if st.button("Guardar"):
            query("""INSERT INTO movimientos 
            (usuario_id,fecha,tipo,categoria,monto) 
            VALUES (%s,%s,%s,%s,%s)""",
                  (user_id, fecha, tipo, categoria, monto))
            st.success("Guardado")
            st.rerun()

        df = pd.DataFrame(query(
            "SELECT id,fecha,tipo,categoria,monto FROM movimientos WHERE usuario_id=%s",
            (user_id,), True),
            columns=["id","fecha","tipo","categoria","monto"]
        )

        st.dataframe(df)

        # EDITAR
        st.subheader("Editar")
        eid = st.number_input("ID", 0)
        nuevo = st.number_input("Nuevo monto", 0.0)

        if st.button("Actualizar"):
            query("UPDATE movimientos SET monto=%s WHERE id=%s", (nuevo, eid))
            st.rerun()

        # ELIMINAR
        did = st.number_input("ID eliminar", 0)
        if st.button("Eliminar"):
            query("DELETE FROM movimientos WHERE id=%s", (did,))
            st.rerun()

        # EXPORTAR
        if not df.empty:
            buffer = io.BytesIO()
            df.to_excel(buffer, index=False, engine="xlsxwriter")
            st.download_button("Descargar Excel", buffer.getvalue(), "datos.xlsx")

    # =========================
    # PRESUPUESTO
    # =========================
    if menu == "Presupuesto":
        st.title("Presupuesto")

        cat = st.text_input("Categoría")
        monto = st.number_input("Monto mensual", 0.0)

        if st.button("Guardar"):
            query("INSERT INTO presupuestos (usuario_id,categoria,monto) VALUES (%s,%s,%s)",
                  (user_id, cat, monto))

        df = pd.DataFrame(query(
            "SELECT categoria,monto FROM presupuestos WHERE usuario_id=%s",
            (user_id,), True),
            columns=["categoria","monto"]
        )

        st.dataframe(df)

    # =========================
    # DASHBOARD
    # =========================
    if menu == "Dashboard":
        st.title("Dashboard")

        df = pd.DataFrame(query(
            "SELECT fecha,tipo,categoria,monto FROM movimientos WHERE usuario_id=%s",
            (user_id,), True),
            columns=["fecha","tipo","categoria","monto"]
        )

        if df.empty:
            st.warning("Sin datos")
        else:
            ingresos = df[df.tipo=="Ingreso"].monto.sum()
            gastos = df[df.tipo=="Gasto"].monto.sum()

            col1,col2,col3 = st.columns(3)
            col1.metric("Ingresos", ingresos)
            col2.metric("Gastos", gastos)
            col3.metric("Balance", ingresos-gastos)

            st.bar_chart(df.groupby("categoria")["monto"].sum())

            # PREDICCIÓN SIMPLE
            st.subheader("Predicción por categoría")

            df["fecha"] = pd.to_datetime(df["fecha"])
            df["mes"] = df["fecha"].dt.month

            pred = df.groupby(["categoria","mes"])["monto"].mean().reset_index()

            st.line_chart(pred, x="mes", y="monto", color="categoria")
