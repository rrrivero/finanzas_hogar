import streamlit as st
import pandas as pd
import psycopg2
import os
from dotenv import load_dotenv
import bcrypt

# =========================
# CONFIG
# =========================
load_dotenv()

import streamlit as st
import os

try:
    DATABASE_URL = st.secrets["DATABASE_URL"]  # nube
except:
    DATABASE_URL = os.getenv("DATABASE_URL")   # local

if not DATABASE_URL:
    st.error("❌ DATABASE_URL no configurada")
    st.stop()
    
# =========================
# CONEXION DB
# =========================
@st.cache_resource
def conectar():
    return psycopg2.connect(DATABASE_URL)

conn = conectar()
cursor = conn.cursor()

# =========================
# CREAR TABLAS
# =========================
cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    usuario TEXT UNIQUE,
    password TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS movimientos (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER,
    fecha DATE,
    tipo TEXT,
    categoria TEXT,
    monto REAL
)
""")

conn.commit()

# =========================
# UI
# =========================
st.title("💰 Finanzas del Hogar")

# SESSION
if "usuario_id" not in st.session_state:
    st.session_state.usuario_id = None

# =========================
# LOGIN / REGISTRO
# =========================
if st.session_state.usuario_id is None:

    menu = st.selectbox("Opciones", ["Login", "Registrarse"])

    if menu == "Registrarse":

        st.subheader("Crear cuenta")

        nuevo_usuario = st.text_input("Usuario")
        nueva_password = st.text_input("Contraseña", type="password")

        if st.button("Registrar"):

            if nuevo_usuario and nueva_password:

                hash_password = bcrypt.hashpw(
                    nueva_password.encode("utf-8"),
                    bcrypt.gensalt()
                )

                try:
                    cursor.execute(
                        "INSERT INTO usuarios (usuario,password) VALUES (%s,%s)",
                        (nuevo_usuario, hash_password)
                    )
                    conn.commit()
                    st.success("Usuario creado")
                except:
                    st.error("Ese usuario ya existe")

    if menu == "Login":

        st.subheader("Iniciar sesión")

        usuario = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")

        if st.button("Entrar"):

            cursor.execute(
                "SELECT id,password FROM usuarios WHERE usuario=%s",
                (usuario,)
            )

            resultado = cursor.fetchone()

            if resultado:

                user_id, password_guardado = resultado

                if bcrypt.checkpw(password.encode("utf-8"), password_guardado):
                    st.session_state.usuario_id = user_id
                    st.success("Login correcto")
                    st.rerun()
                else:
                    st.error("Contraseña incorrecta")
            else:
                st.error("Usuario no existe")

# =========================
# APP PRINCIPAL
# =========================
else:

    usuario_id = st.session_state.usuario_id

    if st.button("Cerrar sesión"):
        st.session_state.usuario_id = None
        st.rerun()

    # =========================
    # CARGAR DATOS
    # =========================
    df = pd.read_sql(
        "SELECT * FROM movimientos WHERE usuario_id=%s",
        conn,
        params=(usuario_id,)
    )

    st.subheader("📊 Resumen")

    if df.empty:
        st.warning("No hay datos aún")
    else:

        ingresos = df[df["tipo"] == "Ingreso"]["monto"].sum()
        gastos = df[df["tipo"] == "Gasto"]["monto"].sum()
        ahorro = ingresos - gastos

        col1, col2, col3 = st.columns(3)
        col1.metric("Ingresos", ingresos)
        col2.metric("Gastos", gastos)
        col3.metric("Ahorro", ahorro)

        st.bar_chart({
            "Ingresos": ingresos,
            "Gastos": gastos,
            "Ahorro": ahorro
        })

    # =========================
    # AGREGAR MOVIMIENTO
    # =========================
    st.subheader("➕ Agregar movimiento")

    tipo = st.selectbox("Tipo", ["Ingreso", "Gasto"])
    monto = st.number_input("Monto", min_value=0.0)
    categoria = st.text_input("Categoría")
    fecha = st.date_input("Fecha")

    if st.button("Guardar movimiento"):

        cursor.execute("""
        INSERT INTO movimientos (usuario_id, fecha, tipo, categoria, monto)
        VALUES (%s, %s, %s, %s, %s)
        """, (
            usuario_id,
            fecha,
            tipo,
            categoria,
            monto
        ))

        conn.commit()
        st.success("Guardado")
        st.rerun()

    # =========================
    # HISTORIAL
    # =========================
    st.subheader("📜 Historial")

    df = pd.read_sql(
        "SELECT * FROM movimientos WHERE usuario_id=%s ORDER BY fecha DESC",
        conn,
        params=(usuario_id,)
    )

    st.dataframe(df)

    # =========================
    # RESUMEN MENSUAL
    # =========================
    if not df.empty:

        df["fecha"] = pd.to_datetime(df["fecha"])
        df["mes"] = df["fecha"].dt.to_period("M")

        resumen = df.groupby(["mes", "tipo"])["monto"].sum().unstack().fillna(0)

        if "Ingreso" not in resumen.columns:
            resumen["Ingreso"] = 0
        if "Gasto" not in resumen.columns:
            resumen["Gasto"] = 0

        resumen["ahorro"] = resumen["Ingreso"] - resumen["Gasto"]

        st.subheader("📅 Resumen mensual")
        st.dataframe(resumen)

        st.subheader("📈 Evolución del ahorro")
        st.line_chart(resumen["ahorro"])
