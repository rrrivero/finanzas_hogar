import streamlit as st
import pandas as pd
import bcrypt
import psycopg2
import os

# ========================
# CONEXIÓN SUPABASE
# ========================

DATABASE_URL = os.getenv("DATABASE_URL")

conn = psycopg2.connect(DATABASE_URL)
cursor = conn.cursor()

# ========================
# CREAR TABLAS
# ========================

cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    id SERIAL PRIMARY KEY,
    usuario TEXT UNIQUE,
    password BYTEA
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

cursor.execute("""
CREATE TABLE IF NOT EXISTS inversiones (
    id SERIAL PRIMARY KEY,
    usuario_id INTEGER,
    nombre TEXT,
    tipo TEXT,
    monto REAL,
    fecha DATE
)
""")

conn.commit()

# ========================
# UI
# ========================

st.title("Finanzas del Hogar")

# ========================
# LOGIN
# ========================

if "usuario_id" not in st.session_state:
    st.session_state.usuario_id = None

if st.session_state.usuario_id is None:

    opcion = st.selectbox("Opciones", ["Login", "Registrarse"])

    if opcion == "Registrarse":
        st.subheader("Crear cuenta")

        user = st.text_input("Usuario")
        pwd = st.text_input("Contraseña", type="password")

        if st.button("Registrar"):
            try:
                hash_pwd = bcrypt.hashpw(pwd.encode(), bcrypt.gensalt())

                cursor.execute(
                    "INSERT INTO usuarios (usuario, password) VALUES (%s, %s)",
                    (user, hash_pwd)
                )
                conn.commit()
                st.success("Usuario creado")

            except:
                st.error("Usuario ya existe")

    if opcion == "Login":
        st.subheader("Iniciar sesión")

        user = st.text_input("Usuario")
        pwd = st.text_input("Contraseña", type="password")

        if st.button("Entrar"):

            cursor.execute(
                "SELECT id, password FROM usuarios WHERE usuario=%s",
                (user,)
            )

            res = cursor.fetchone()

            if res:
                user_id, pwd_db = res

                if bcrypt.checkpw(pwd.encode(), pwd_db):
                    st.session_state.usuario_id = user_id
                    st.success("Login correcto")
                    st.rerun()
                else:
                    st.error("Contraseña incorrecta")
            else:
                st.error("Usuario no existe")

# ========================
# APP PRINCIPAL
# ========================

else:

    usuario_id = st.session_state.usuario_id

    if st.button("Cerrar sesión"):
        st.session_state.usuario_id = None
        st.rerun()

    # ========================
    # CARGAR DATOS
    # ========================

    df = pd.read_sql(
        f"SELECT * FROM movimientos WHERE usuario_id={usuario_id}",
        conn
    )

    df_inv = pd.read_sql(
        f"SELECT * FROM inversiones WHERE usuario_id={usuario_id}",
        conn
    )

    # ========================
    # RESUMEN GENERAL
    # ========================

    ingresos = df[df["tipo"] == "Ingreso"]["monto"].sum() if not df.empty else 0
    gastos = df[df["tipo"] == "Gasto"]["monto"].sum() if not df.empty else 0
    ahorro = ingresos - gastos
    inversiones = df_inv["monto"].sum() if not df_inv.empty else 0

    st.subheader("Resumen financiero")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Ingresos", ingresos)
    c2.metric("Gastos", gastos)
    c3.metric("Ahorro", ahorro)
    c4.metric("Inversiones", inversiones)

    st.metric("Patrimonio total", ahorro + inversiones)

    # ========================
    # AGREGAR MOVIMIENTO
    # ========================

    st.subheader("Agregar movimiento")

    tipo = st.selectbox("Tipo", ["Ingreso", "Gasto"])
    monto = st.number_input("Monto", min_value=0.0)
    categoria = st.text_input("Categoría")
    fecha = st.date_input("Fecha")

    if st.button("Guardar movimiento"):

        cursor.execute("""
        INSERT INTO movimientos (usuario_id, fecha, tipo, categoria, monto)
        VALUES (%s, %s, %s, %s, %s)
        """, (usuario_id, fecha, tipo, categoria, monto))

        conn.commit()
        st.success("Guardado")
        st.rerun()

    # ========================
    # HISTORIAL
    # ========================

    st.subheader("Historial")

    df = pd.read_sql(
        f"SELECT * FROM movimientos WHERE usuario_id={usuario_id} ORDER BY fecha",
        conn
    )

    st.dataframe(df)

    if df.empty:
        st.warning("No hay datos")
        st.stop()

    # ========================
    # RESUMEN MENSUAL (CORREGIDO)
    # ========================

    df["fecha"] = pd.to_datetime(df["fecha"])
    df["mes"] = df["fecha"].dt.to_period("M")

    resumen = df.groupby(["mes", "tipo"])["monto"].sum().unstack().fillna(0)

    if "Ingreso" not in resumen:
        resumen["Ingreso"] = 0

    if "Gasto" not in resumen:
        resumen["Gasto"] = 0

    resumen["ahorro"] = resumen["Ingreso"] - resumen["Gasto"]

    resumen = resumen.sort_index()

    st.subheader("Resumen mensual")
    st.dataframe(resumen)

    # ========================
    # GRAFICOS
    # ========================

    st.subheader("Evolución del ahorro")
    st.line_chart(resumen["ahorro"])

    st.subheader("Gastos por categoría")

    gastos_cat = df[df["tipo"] == "Gasto"].groupby("categoria")["monto"].sum()

    if not gastos_cat.empty:
        st.bar_chart(gastos_cat)
    else:
        st.info("Sin gastos aún")

    # ========================
    # INVERSIONES
    # ========================

    st.subheader("Agregar inversión")

    nombre = st.text_input("Nombre")
    tipo_inv = st.selectbox("Tipo", ["Acción", "ETF", "Cripto", "Otro"])
    monto_inv = st.number_input("Monto inversión", min_value=0.0)

    if st.button("Guardar inversión"):

        cursor.execute("""
        INSERT INTO inversiones (usuario_id, nombre, tipo, monto, fecha)
        VALUES (%s, %s, %s, %s, CURRENT_DATE)
        """, (usuario_id, nombre, tipo_inv, monto_inv))

        conn.commit()
        st.success("Inversión guardada")
        st.rerun()

    st.subheader("Inversiones")

    df_inv = pd.read_sql(
        f"SELECT * FROM inversiones WHERE usuario_id={usuario_id}",
        conn
    )

    st.dataframe(df_inv)
