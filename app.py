import bcrypt
import streamlit as st
import pandas as pd
import sqlite3

conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

# TABLA USUARIOS
cursor.execute("""
CREATE TABLE IF NOT EXISTS usuarios (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario TEXT UNIQUE,
    password TEXT
)
""")

# TABLA MOVIMIENTOS
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

# TABLA INVERSIONES
cursor.execute("""
CREATE TABLE IF NOT EXISTS inversiones (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    usuario_id INTEGER,
    nombre TEXT,
    tipo TEXT,
    monto REAL,
    fecha TEXT
)
""")

conn.commit()

st.title("Finanzas del Hogar")

# ESTADO LOGIN
if "usuario_id" not in st.session_state:
    st.session_state.usuario_id = None


# LOGIN / REGISTRO
if st.session_state.usuario_id is None:

    menu = st.selectbox("Opciones", ["Login", "Registrarse"])

    if menu == "Registrarse":

        st.subheader("Crear cuenta")

        nuevo_usuario = st.text_input("Usuario")
        nueva_password = st.text_input("Contraseña", type="password")

        if st.button("Registrar"):

            try:
                password_bytes = nueva_password.encode("utf-8")
                hash_password = bcrypt.hashpw(password_bytes, bcrypt.gensalt())

                cursor.execute(
                    "INSERT INTO usuarios (usuario,password) VALUES (?,?)",
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
                "SELECT id,password FROM usuarios WHERE usuario=?",
                (usuario,)
            )

            resultado = cursor.fetchone()

            if resultado:
                user_id = resultado[0]
                password_guardado = resultado[1]

                if bcrypt.checkpw(password.encode("utf-8"), password_guardado):
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

    # CARGAR DATOS DEL USUARIO
    df = pd.read_sql(
        f"SELECT * FROM movimientos WHERE usuario_id={usuario_id}",
        conn
    )

    df_inv = pd.read_sql(
        f"SELECT * FROM inversiones WHERE usuario_id={usuario_id}",
        conn
    )

    # CALCULOS
    ingresos = df[df["tipo"] == "Ingreso"]["monto"].sum()
    gastos = df[df["tipo"] == "Gasto"]["monto"].sum()
    ahorro = ingresos - gastos
    total_inversiones = df_inv["monto"].sum()
    patrimonio = ahorro + total_inversiones

    st.subheader("Resumen financiero")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Ingresos", ingresos)
    col2.metric("Gastos", gastos)
    col3.metric("Ahorro", ahorro)
    col4.metric("Inversiones", total_inversiones)

    st.metric("Patrimonio total", patrimonio)

    # GRAFICO
    st.subheader("Distribución del patrimonio")

    datos = {
        "Ahorro": ahorro,
        "Inversiones": total_inversiones
    }

    st.bar_chart(datos)

    # AGREGAR MOVIMIENTO
    st.subheader("Agregar movimiento")

    tipo = st.selectbox("Tipo", ["Ingreso", "Gasto"])
    monto = st.number_input("Monto", min_value=0.0)
    categoria = st.text_input("Categoría")
    cuenta = st.text_input("Cuenta")
    forma_pago = st.text_input("Forma de pago")
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

    # HISTORIAL
    st.subheader("Historial")

    df = pd.read_sql(
        f"SELECT * FROM movimientos WHERE usuario_id={usuario_id} ORDER BY fecha DESC",
        conn
    )

    st.dataframe(df)

    df["fecha"] = pd.to_datetime(df["fecha"])
    df["mes"] = df["fecha"].dt.to_period("M")

    resumen_mensual = df.groupby(["mes","tipo"])["monto"].sum().unstack().fillna(0)

    if "Ingreso" not in resumen_mensual.columns:
        resumen_mensual["Ingreso"] = 0

    if "Gasto" not in resumen_mensual.columns:
        resumen_mensual["Gasto"] = 0

    resumen_mensual["ahorro"] = resumen_mensual["Ingreso"] - resumen_mensual["Gasto"]

    st.subheader("Cierre mensual")

    st.dataframe(resumen_mensual)

    st.subheader("Evolucion del ahorro mensual")

    st.line_chart(resumen_mensual["ahorro"])

    df["fecha"] = pd.to_datetime(df["fecha"])
    df["mes"] = df["fecha"].dt.to_period("M")

    resumen = df.groupby(["mes", "tipo"])["monto"].sum().unstack().fillna(0)

    if "Ingreso" not in resumen.columns:
        resumen["Ingreso"] = 0

    if "Gasto" not in resumen.columns:
        resumen["Gasto"] = 0

    resumen["ahorro"] = resumen["Ingreso"] - resumen["Gasto"]
    resumen["tasa_ahorro"] = resumen["ahorro"] / resumen["Ingreso"]

    # GRAFICO DE GASTOS POR CATEGORIA

    st.subheader("Gastos por categoria")

    gastos_categoria = df[df["tipo"] == "Gasto"].groupby("categoria")["monto"].sum()

    st.bar_chart(gastos_categoria)

    # AGREGAR INVERSIONES
    st.subheader("Agregar inversión")

    nombre = st.text_input("Nombre inversión")
    tipo_inv = st.selectbox(
        "Tipo inversión",
        ["Acción", "ETF", "Cripto", "Fondo", "Cuenta remunerada", "Otro"]
    )

    monto_inv = st.number_input("Monto invertido", min_value=0.0)

    if st.button("Guardar inversión"):

        cursor.execute(
            "INSERT INTO inversiones (usuario_id,nombre,tipo,monto,fecha) VALUES (?,?,?,?,date('now'))",
            (usuario_id, nombre, tipo_inv, monto_inv)
        )

        conn.commit()
        st.success("Inversión guardada")
        st.rerun()

    # HISTORIAL INVERSIONES
    st.subheader("Inversiones")

    df_inv = pd.read_sql(
        f"SELECT * FROM inversiones WHERE usuario_id={usuario_id}",
        conn
    )

    st.dataframe(df_inv)

    #EVOLUCION FINANCIERA

    st.subheader("Evolucion financiera")

    st.line_chart(resumen[["Ingreso", "Gasto", "ahorro"]])

    # MOSTRAR MESES DE ALTO GASTO

    gasto_promedio = resumen["Gasto"].mean()

    meses_exceso = resumen[resumen["Gasto"] > gasto_promedio * 1.3]

    if not meses_exceso.empty:
        st.warning("Meses con gasto superior a lo normal")

        st.dataframe(meses_exceso)

    tasa_promedio = resumen["tasa_ahorro"].mean()

    st.subheader("Analisis de ahorro")

    st.metric("Tasa promedio de ahorro", f"{tasa_promedio*100:.1f}%")

    if tasa_promedio < 0.2:
        st.warning("Tu tasa de ahorro es baja")
    else:
        st.success("Buen nivel de ahorro")

    gastos_categoria = df[df["tipo"]=="Gasto"].groupby("categoria")["monto"].sum()


    def obtener_top_categoria(serie):
        if serie is None or serie.empty or serie.dropna().empty:
            return "Sin datos"
        return serie.idxmax()

    top_categoria = obtener_top_categoria(gastos_categoria)

    st.subheader("Mayor gasto")

    st.write("Tu categoria con mayor gasto es:", top_categoria)

    st.subheader("Gastos por categoria")

    st.bar_chart(gastos_categoria)

# ANALISIS DE DATOS MES A MES

resumen = resumen.sort_index()

st.subheader("Predicción financiera")

if len(resumen) >= 2:

    ahorro_promedio = resumen["ahorro"].mean()

    meses_futuros = 3

    ahorro_actual = resumen["ahorro"].iloc[-1]

    prediccion = []

    valor = ahorro_actual

    for i in range(meses_futuros):
        valor += ahorro_promedio
        prediccion.append(valor)

    st.write(f"Proyección de ahorro en {meses_futuros} meses:")

    st.line_chart(prediccion)

if prediccion[-1] < 0:
    st.error("🚨 Si sigues así, tu ahorro será negativo en los próximos meses")

if ahorro_promedio < 0:
    st.warning("⚠️ Estás gastando más de lo que ganas en promedio")

gastos_categoria = df[df["tipo"]=="Gasto"].groupby("categoria")["monto"].sum()

total_gastos = gastos_categoria.sum()

porcentajes = (gastos_categoria / total_gastos) * 100

categoria_top = porcentajes.idxmax()
porcentaje_top = porcentajes.max()

if porcentaje_top > 30:
    st.warning(f"💡 Estás gastando mucho en {categoria_top} ({porcentaje_top:.1f}%)")

st.subheader("Análisis automático")

if len(resumen) > 1:

    ultimo_mes = resumen.iloc[-1]
    mes_anterior = resumen.iloc[-2]

    gasto_actual = ultimo_mes["Gasto"]
    gasto_anterior = mes_anterior["Gasto"]

    if gasto_anterior > 0:
        variacion = ((gasto_actual - gasto_anterior) / gasto_anterior) * 100

        if variacion > 0:
            st.warning(f"⚠️ Este mes gastaste {variacion:.1f}% más que el mes anterior")
        else:
            st.success(f"✅ Gastaste {abs(variacion):.1f}% menos que el mes anterior")

df_gastos = df[df["tipo"] == "Gasto"]

df_gastos["mes"] = df_gastos["fecha"].dt.to_period("M")

gastos_cat = df_gastos.groupby(["mes","categoria"])["monto"].sum().unstack().fillna(0)

if len(gastos_cat) > 1:

    ultimo = gastos_cat.iloc[-1]
    anterior = gastos_cat.iloc[-2]

    aumentos = ((ultimo - anterior) / anterior.replace(0,1)) * 100

    categoria_top = aumentos.idxmax()
    aumento_top = aumentos.max()

    if aumento_top > 20:
        st.warning(f"📈 Tu gasto en {categoria_top} aumentó {aumento_top:.1f}%")

tasa = ultimo_mes["ahorro"] / ultimo_mes["Ingreso"] if ultimo_mes["Ingreso"] > 0 else 0

if tasa < 0.2:
    st.error("🚨 Tu ahorro este mes es bajo")
else:
    st.success("💰 Buen nivel de ahorro este mes")

if gasto_actual > resumen["Gasto"].mean() * 1.3:
    st.error("⚠️ Estás gastando muy por encima de tu promedio")




