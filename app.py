import bcrypt
import streamlit as st
import pandas as pd
import sqlite3

st.title("Finanzas del Hogar")

# CONEXIÓN BD
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

# ESTADO LOGIN
if "usuario_id" not in st.session_state:
    st.session_state.usuario_id = None

# LOGIN / REGISTRO
if st.session_state.usuario_id is None:

    menu = st.selectbox("Opciones", ["Login", "Registrarse"])

    if menu == "Registrarse":
        st.subheader("Registro")

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
        st.subheader("Login")

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
                    st.success("Login correcto")
                    st.rerun()
                else:
                    st.error("Contraseña incorrecta")
            else:
                st.error("Usuario no existe")

# APP PRINCIPAL
else:

    usuario_id = st.session_state.usuario_id

    if st.button("Cerrar sesión"):
        st.session_state.usuario_id = None
        st.rerun()

    # =========================
    # CARGAR EXCEL
    # =========================
    st.subheader("Cargar datos desde Excel")

    archivo = st.file_uploader("Sube tu archivo Excel", type=["xlsx"])

    if archivo is not None:
        try:
            df_excel = pd.read_excel(archivo)
            st.dataframe(df_excel.head())

            if st.button("Importar datos"):
                for _, row in df_excel.iterrows():
                    cursor.execute(
                        """INSERT INTO movimientos 
                        (usuario_id, fecha, tipo, categoria, cuenta, forma_pago, descripcion, monto)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                        (
                            usuario_id,
                            str(row.get("fecha", "")),
                            row.get("tipo", ""),
                            row.get("categoria", ""),
                            row.get("cuenta", "Principal"),
                            row.get("forma_pago", "Efectivo"),
                            row.get("descripcion", ""),
                            float(row.get("monto", 0))
                        )
                    )
                conn.commit()
                st.success("Datos importados correctamente")
                st.rerun()

        except Exception as e:
            st.error(f"Error al cargar Excel: {e}")

    # =========================
    # AGREGAR MOVIMIENTO
    # =========================
    st.subheader("Agregar movimiento")

    tipo = st.selectbox("Tipo", ["Ingreso", "Gasto"])
    monto = st.number_input("Monto", min_value=0.0)
    categoria = st.text_input("Categoría")
    cuenta = st.text_input("Cuenta", value="Principal")
    forma_pago = st.text_input("Forma de pago", value="Efectivo")
    descripcion = st.text_input("Descripción")
    fecha = st.date_input("Fecha")

    if st.button("Guardar movimiento"):
        cursor.execute(
            """INSERT INTO movimientos 
            (usuario_id,fecha,tipo,categoria,cuenta,forma_pago,descripcion,monto)
            VALUES (?,?,?,?,?,?,?,?)""",
            (
                usuario_id,
                str(fecha),
                tipo,
                categoria,
                cuenta,
                forma_pago,
                descripcion,
                monto
            )
        )
        conn.commit()
        st.success("Movimiento guardado")
        st.rerun()

    # =========================
    # HISTORIAL
    # =========================
    st.subheader("Historial")

    df = pd.read_sql(
        f"SELECT * FROM movimientos WHERE usuario_id={usuario_id}",
        conn
    )

    st.dataframe(df)

    if df.empty:
        st.warning("No hay datos aún")
        st.stop()

    # =========================
    # PROCESAMIENTO
    # =========================
    df["fecha"] = pd.to_datetime(df["fecha"])
    df["mes"] = df["fecha"].dt.to_period("M")

    resumen = df.groupby(["mes","tipo"])["monto"].sum().unstack().fillna(0)

    if "Ingreso" not in resumen.columns:
        resumen["Ingreso"] = 0
    if "Gasto" not in resumen.columns:
        resumen["Gasto"] = 0

    resumen["ahorro"] = resumen["Ingreso"] - resumen["Gasto"]

    resumen = resumen.sort_index()

    # =========================
    # DASHBOARD
    # =========================
    st.subheader("Resumen mensual")
    st.dataframe(resumen)

    st.subheader("Evolución del ahorro")
    st.line_chart(resumen["ahorro"])

    # =========================
    # GASTOS POR CATEGORIA
    # =========================
    st.subheader("Gastos por categoría")

    gastos_categoria = df[df["tipo"] == "Gasto"].groupby("categoria")["monto"].sum()

    st.bar_chart(gastos_categoria)
