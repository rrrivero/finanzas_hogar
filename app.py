import bcrypt
import streamlit as st
import pandas as pd
import sqlite3

st.write("VERSION LIMPIA FUNCIONANDO ✅")

conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

# TABLAS
cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT UNIQUE,
    password TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS movimientos (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER,
    fecha TEXT,
    tipo TEXT,
    categoria TEXT,
    cuenta TEXT,
    forma_pago TEXT,
    descripcion TEXT,
    monto REAL
)
""")

conn.commit()

st.title("Finanzas del Hogar")

# LOGIN
if "usuario_id" not in st.session_state:
    st.session_state.usuario_id = None

if st.session_state.usuario_id is None:

    menu = st.selectbox("Opciones", ["Login", "Registrarse"])

    if menu == "Registrarse":
        usuario = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")

        if st.button("Registrar"):
            try:
                hash_pw = bcrypt.hashpw(password.encode(), bcrypt.gensalt())
                cursor.execute(
                    "INSERT INTO usuarios (usuario,password) VALUES (?,?)",
                    (usuario, hash_pw)
                )
                conn.commit()
                st.success("Usuario creado")
            except:
                st.error("Usuario ya existe")

    if menu == "Login":
        usuario = st.text_input("Usuario")
        password = st.text_input("Contraseña", type="password")

        if st.button("Entrar"):
            cursor.execute(
                "SELECT id,password FROM usuarios WHERE usuario=?",
                (usuario,)
            )
            result = cursor.fetchone()

            if result:
                user_id, pw = result
                if bcrypt.checkpw(password.encode(), pw):
                    st.session_state.usuario_id = user_id
                    st.rerun()
                else:
                    st.error("Contraseña incorrecta")
            else:
                st.error("Usuario no existe")

# APP
else:
    usuario_id = st.session_state.usuario_id

    if st.button("Cerrar sesión"):
        st.session_state.usuario_id = None
        st.rerun()

    df = pd.read_sql(
        f"SELECT * FROM movimientos WHERE usuario_id={usuario_id}",
        conn
    )

    st.subheader("Agregar movimiento")

    tipo = st.selectbox("Tipo", ["Ingreso", "Gasto"])
    monto = st.number_input("Monto", min_value=0.0)
    categoria = st.text_input("Categoría")
    fecha = st.date_input("Fecha")

    if st.button("Guardar"):
        cursor.execute(
            """INSERT INTO movimientos (usuario_id,fecha,tipo,categoria,monto)
            VALUES (?,?,?,?,?)""",
            (usuario_id, str(fecha), tipo, categoria, monto)
        )
        conn.commit()
        st.success("Guardado")
        st.rerun()

    st.subheader("Historial")

    df = pd.read_sql(
        f"SELECT * FROM movimientos WHERE usuario_id={usuario_id}",
        conn
    )

    st.dataframe(df)

    if df.empty:
        st.warning("No hay datos")
        st.stop()

    # PROCESAMIENTO
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["mes"] = df["fecha"].dt.to_period("M")

    resumen = df.groupby(["mes","tipo"])["monto"].sum().unstack().fillna(0)

    if "Ingreso" not in resumen.columns:
        resumen["Ingreso"] = 0
    if "Gasto" not in resumen.columns:
        resumen["Gasto"] = 0

    resumen["ahorro"] = resumen["Ingreso"] - resumen["Gasto"]

    resumen = resumen.sort_index()

    st.subheader("Resumen mensual")
    st.dataframe(resumen)

    st.line_chart(resumen["ahorro"])



