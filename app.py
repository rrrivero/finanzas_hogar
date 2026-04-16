import streamlit as st
import pandas as pd
import psycopg2
from psycopg2 import pool
import bcrypt
import os
from dotenv import load_dotenv

# =========================
# CONFIG UI
# =========================
st.set_page_config(
    page_title="Finanzas del Hogar",
    page_icon="💰",
    layout="wide"
)

# =========================
# CARGAR ENV
# =========================
load_dotenv()

DATABASE_URL = None

try:
    DATABASE_URL = st.secrets["DATABASE_URL"]
except:
    pass

if not DATABASE_URL:
    DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    st.error("❌ DATABASE_URL no configurada")
    st.stop()

# =========================
# POOL DE CONEXIONES
# =========================
@st.cache_resource
def get_pool():
    return psycopg2.pool.SimpleConnectionPool(
        minconn=1,
        maxconn=5,
        dsn=DATABASE_URL
    )

pool_conn = get_pool()

# =========================
# FUNCION DB SEGURA
# =========================
def run_query(query, params=None, fetch=False):
    conn = None
    try:
        conn = pool_conn.getconn()
        cursor = conn.cursor()
        cursor.execute(query, params)

        if fetch:
            result = cursor.fetchall()
        else:
            result = None

        conn.commit()
        cursor.close()
        return result

    except Exception as e:
        if conn:
            conn.rollback()
        st.error(f"Error DB: {e}")
        return None

    finally:
        if conn:
            pool_conn.putconn(conn)

# =========================
# CREAR TABLAS
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

# =========================
# SESSION
# =========================
if "usuario_id" not in st.session_state:
    st.session_state.usuario_id = None

# =========================
# LOGIN / REGISTRO
# =========================
if st.session_state.usuario_id is None:

    st.title("💰 Finanzas del Hogar")

    menu = st.selectbox("Opciones", ["Login", "Registrarse"])

    if menu == "Registrarse":

        st.subheader("Crear cuenta")

        usuario = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")

        if st.button("Registrar"):

            if usuario.strip() and password.strip():

                hash_pass = bcrypt.hashpw(
                    password.encode(),
                    bcrypt.gensalt()
                ).decode()

                run_query(
                    "INSERT INTO usuarios (usuario,password) VALUES (%s,%s)",
                    (usuario, hash_pass)
                )

                st.success("Usuario creado")

            else:
                st.warning("Completa todos los campos")

    if menu == "Login":

        st.subheader("Iniciar sesión")

        usuario = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")

        if st.button("Entrar"):

            data = run_query(
                "SELECT id,password FROM usuarios WHERE usuario=%s",
                (usuario,),
                fetch=True
            )

            if data:

                user_id, pass_db = data[0]

                if pass_db and pass_db.startswith("$2b$"):
                    try:
                        if bcrypt.checkpw(password.encode(), pass_db.encode()):
                            st.session_state.usuario_id = user_id
                            st.success("Login correcto")
                            st.rerun()
                        else:
                            st.error("Contraseña incorrecta")
                    except:
                        st.error("Error en contraseña")
                else:
                    st.error("Usuario inválido. Regístralo nuevamente")

            else:
                st.error("Usuario no existe")

# =========================
# APP PRINCIPAL
# =========================
else:

    usuario_id = st.session_state.usuario_id

    # SIDEBAR
    st.sidebar.title("📌 Menú")
    menu = st.sidebar.selectbox(
        "Ir a",
        ["Dashboard", "Agregar", "Historial"]
    )

    st.sidebar.write(f"👤 Usuario: {usuario_id}")

    if st.sidebar.button("Cerrar sesión"):
        st.session_state.usuario_id = None
        st.rerun()

    # CARGAR DATOS
    data = run_query(
        "SELECT * FROM movimientos WHERE usuario_id=%s",
        (usuario_id,),
        fetch=True
    )

    df = pd.DataFrame(data, columns=[
        "id", "usuario_id", "fecha", "tipo", "categoria", "monto"
    ]) if data else pd.DataFrame()

    # =========================
    # DASHBOARD
    # =========================
    if menu == "Dashboard":

        st.title("📊 Dashboard")

        if df.empty:
            st.warning("No hay datos aún")
        else:

            ingresos = df[df["tipo"] == "Ingreso"]["monto"].sum()
            gastos = df[df["tipo"] == "Gasto"]["monto"].sum()
            ahorro = ingresos - gastos

            col1, col2, col3 = st.columns(3)
            col1.metric("💰 Ingresos", ingresos)
            col2.metric("💸 Gastos", gastos)
            col3.metric("📈 Ahorro", ahorro)

            st.subheader("📈 Evolución")
            df["fecha"] = pd.to_datetime(df["fecha"])
            evolucion = df.groupby("fecha")["monto"].sum()
            st.line_chart(evolucion)

    # =========================
    # AGREGAR
    # =========================
    elif menu == "Agregar":

        st.title("➕ Nuevo movimiento")

        tipo = st.selectbox("Tipo", ["Ingreso", "Gasto"])
        monto = st.number_input("Monto", min_value=0.0)
        categoria = st.selectbox(
            "Categoría",
            ["Comida", "Transporte", "Casa", "Ocio", "Otros"]
        )
        fecha = st.date_input("Fecha")

        if st.button("Guardar"):

            run_query("""
                INSERT INTO movimientos (usuario_id, fecha, tipo, categoria, monto)
                VALUES (%s, %s, %s, %s, %s)
            """, (
                usuario_id,
                str(fecha),
                tipo,
                categoria,
                monto
            ))

            st.success("Movimiento guardado")
            st.rerun()

    # =========================
    # HISTORIAL
    # =========================
    elif menu == "Historial":

        st.title("📜 Historial")

        st.dataframe(df)

        if not df.empty:
            st.subheader("📊 Gastos por categoría")

            gastos = df[df["tipo"] == "Gasto"]

            if not gastos.empty:
                grafico = gastos.groupby("categoria")["monto"].sum()
                st.bar_chart(grafico)
