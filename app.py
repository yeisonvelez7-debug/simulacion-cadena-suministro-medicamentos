import streamlit as st
import pandas as pd
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title="PIODM - Farmacéutico EDA", layout="wide")

# =========================
# 1. INICIALIZACIÓN Y ESTADO (In-Memory Event Store)
# =========================
def init_state():
    # Inventario: Inicia VACÍO - Usuario debe parametrizar
    if "inventory" not in st.session_state:
        st.session_state.inventory = pd.DataFrame(columns=[
            "med", "cum", "ium", "registro_sanitario", "farmacia", 
            "stock_total", "stock_reserved", "stock_disponible"
        ])
        
    if "farmacias" not in st.session_state:
        st.session_state.farmacias = [{"nombre":"Principal","ciudad":"Medellín"}, {"nombre":"Norte","ciudad":"Bogotá"}]
    
    # Órdenes médicas (Evento 1)
    if "prescriptions" not in st.session_state:
        st.session_state.prescriptions = []
        
    # Autorizaciones (Evento 2)
    if "autorizaciones" not in st.session_state:
        st.session_state.autorizaciones = []
        
    # Reservas (Evento 3)
    if "reservas" not in st.session_state:
        st.session_state.reservas = []
        
    # Dispensaciones (Evento 4) - Incluye datos de entrega
    if "dispensations" not in st.session_state:
        st.session_state.dispensations = []
        
    # Log de eventos (Sistema de trazabilidad)
    if "event_log" not in st.session_state:
        st.session_state.event_log = []

init_state()

def log_event(event_type, detail):
    """Función para registrar eventos en la 'cola' de trazabilidad"""
    timestamp = datetime.now().strftime("%H:%M:%S")
    st.session_state.event_log.insert(0, {"Hora": timestamp, "Evento": event_type, "Detalle": detail})

def update_inventory_display():
    """Actualiza la columna calculada de stock_disponible"""
    if not st.session_state.inventory.empty:
        df = st.session_state.inventory
        df["stock_disponible"] = df["stock_total"] - df["stock_reserved"]
        st.session_state.inventory = df

def get_stock_status(med, farmacia, cum):
    """Retorna stock_total, reservado, disponible verificando por CUM"""
    inv = st.session_state.inventory
    if inv.empty:
        return 0,0,0
    mask = (inv["med"]==med) & (inv["farmacia"]==farmacia) & (inv["cum"]==cum)
    if mask.any():
        row = inv[mask].iloc[0]
        disponible = row["stock_total"] - row["stock_reserved"]
        return row["stock_total"], row["stock_reserved"], disponible
    return 0,0,0

def crear_reserva(id_orden, med, farmacia, cum, qty):
    """Paso 3: Reserva el inventario (Evento: reserva_creada)"""
    inv = st.session_state.inventory
    _, _, disponible = get_stock_status(med, farmacia, cum)
    
    if qty > disponible:
        st.warning(f"⚠️ Stock insuficiente en {farmacia}. Disponible: {disponible}")
        return False
        
    # Actualizar inventario: Mover a reservado
    mask = (inv["med"]==med) & (inv["farmacia"]==farmacia) & (inv["cum"]==cum)
    inv.loc[mask, "stock_reserved"] += qty
    update_inventory_display()
    
    # Guardar reserva
    st.session_state.reservas.append({
        "id_orden": id_orden,
        "medicamento": med,
        "cum": cum,
        "farmacia": farmacia,
        "cantidad_reservada": qty
    })
    log_event("📦 RESERVA CREADA", f"Orden {id_orden}: {qty} de {med} (CUM:{cum}) reservados en {farmacia}")
    return True

def dispensar_medicamento(id_orden, med, cum, farmacia, qty, nro_entrega, lote, fecha_vencimiento):
    """Paso 4: Dispensación real con datos de entrega"""
    inv = st.session_state.inventory
    # Buscar reserva activa
    reserva_activa = None
    for r in st.session_state.reservas:
        if r["id_orden"] == id_orden and r["cum"] == cum:
            reserva_activa = r
            break
            
    if not reserva_activa:
        st.error("❌ No se encontró una reserva activa para esta orden. Debe reservar primero.")
        return False
        
    if qty > reserva_activa["cantidad_reservada"]:
        st.error(f"❌ No puedes dispensar más de lo reservado. Reservado: {reserva_activa['cantidad_reservada']}")
        return False
        
    # Actualizar inventario: Reducir total y liberar reserva
    mask = (inv["med"]==med) & (inv["farmacia"]==farmacia) & (inv["cum"]==cum)
    if mask.any():
        inv.loc[mask, "stock_total"] -= qty
        inv.loc[mask, "stock_reserved"] -= qty
        update_inventory_display()
    
    # Actualizar la reserva
    if qty == reserva_activa["cantidad_reservada"]:
        st.session_state.reservas.remove(reserva_activa)
    else:
        reserva_activa["cantidad_reservada"] -= qty
        
    # Registrar dispensación con datos de entrega
    st.session_state.dispensations.append({
        "id_orden": id_orden,
        "medicamento": med,
        "cum": cum,
        "nro_entrega": nro_entrega,
        "lote": lote,
        "fecha_vencimiento": fecha_vencimiento,
        "cantidad_dispensada": qty,
        "farmacia": farmacia
    })
    log_event("💊 MEDICAMENTO DISPENSADO", f"Orden {id_orden}: {qty} de {med} (CUM:{cum}) entregados - Lote:{lote}")
    return True

# =========================
# 2. UI PRINCIPAL
# =========================

st.title("🏥 Proceso Integrado de Ordenamiento y Dispensación de Medicamentos")
st.caption("Arquitectura Orientada a Eventos (EDA) | Procesamiento en Tiempo Real | Trazabilidad por CUM/IUM/Registro Sanitario")

# Sidebar con Log de Eventos
with st.sidebar:
    st.header("📡 Log de Eventos (Tiempo Real)")
    if st.button("🗑️ Limpiar Log"):
        st.session_state.event_log = []
        st.rerun()
    
    log_df = pd.DataFrame(st.session_state.event_log)
    if not log_df.empty:
        st.dataframe(log_df, use_container_width=True, height=400)
    else:
        st.info("No hay eventos aún. Inicia el flujo...")
    
    st.divider()
    st.header("🏪 Estado de Inventario")
    if not st.session_state.inventory.empty:
        st.dataframe(st.session_state.inventory[["med", "cum", "ium", "registro_sanitario", "farmacia", "stock_total", "stock_reserved", "stock_disponible"]], use_container_width=True)
    else:
        st.info("Inventario vacío. Parametriza en la pestaña correspondiente.")

# TABS - CORREGIDO: Ahora hay 7 tabs y se desempaquetan en 7 variables
tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
    "⚙️ Parametrizar Inventario",
    "✏️ Editar Inventario",
    "1️⃣ Generar Orden (IPS)",
    "2️⃣ Validar y Autorizar",
    "3️⃣ Reservar Inventario",
    "4️⃣ Dispensar",
    "5️⃣ Trazabilidad y Analítica"
])

# ------------------------------------------------------------
# TAB 0: PARAMETRIZACIÓN DE INVENTARIO (Carga inicial)
# ------------------------------------------------------------
with tab1:
    st.subheader("📥 Carga de Inventario con Datos Regulatorios")
    st.markdown("**Campos obligatorios:** CUM, IUM, Registro Sanitario")
    
    # Carga masiva desde Excel
    file = st.file_uploader("Subir Excel (med, cum, ium, registro_sanitario, farmacia, stock_total)", type=["xlsx"])
    if file:
        df_excel = pd.read_excel(file)
        st.dataframe(df_excel)
        if st.button("Cargar medicamentos al sistema"):
            required = {"med", "cum", "ium", "registro_sanitario", "stock_total"}
            if not required.issubset(df_excel.columns):
                st.error(f"Faltan columnas requeridas: {required - set(df_excel.columns)}")
            else:
                if "farmacia" not in df_excel.columns:
                    df_excel["farmacia"] = "Principal"
                df_excel["stock_reserved"] = 0
                df_excel["stock_disponible"] = df_excel["stock_total"] - df_excel["stock_reserved"]
                st.session_state.inventory = df_excel.copy()
                log_event("📋 INVENTARIO CARGADO", f"Se cargaron {len(df_excel)} medicamentos")
                st.success(f"{len(df_excel)} medicamentos cargados exitosamente")
                st.rerun()
    
    st.divider()
    st.subheader("➕ Agregar Medicamento Manualmente")
    with st.form("add_med_form"):
        col1, col2 = st.columns(2)
        with col1:
            med = st.text_input("Nombre del medicamento*")
            cum = st.text_input("CUM* (Código Único del Medicamento)")
            ium = st.text_input("IUM* (Identificador Único del Medicamento)")
        with col2:
            registro_sanitario = st.text_input("Registro Sanitario*")
            farmacia = st.selectbox("Farmacia", [f["nombre"] for f in st.session_state.farmacias])
            stock_total = st.number_input("Stock Total Inicial*", min_value=0, step=1)
        
        submitted = st.form_submit_button("Agregar al Inventario")
        if submitted:
            if not all([med, cum, ium, registro_sanitario]):
                st.error("Todos los campos marcados con * son obligatorios (CUM, IUM, Registro Sanitario)")
            else:
                new_row = pd.DataFrame([{
                    "med": med, "cum": cum, "ium": ium, "registro_sanitario": registro_sanitario,
                    "farmacia": farmacia, "stock_total": stock_total, "stock_reserved": 0,
                    "stock_disponible": stock_total
                }])
                st.session_state.inventory = pd.concat([st.session_state.inventory, new_row], ignore_index=True)
                log_event("➕ MEDICAMENTO AGREGADO", f"{med} (CUM:{cum}) - Stock: {stock_total}")
                st.success(f"Medicamento {med} agregado correctamente")
                st.rerun()
    
    st.divider()
    st.subheader("🏥 Gestión de Farmacias")
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        nombre_f = st.text_input("Nombre nueva farmacia")
    with col_f2:
        ciudad_f = st.text_input("Ciudad")
    if st.button("Agregar farmacia"):
        if nombre_f:
            st.session_state.farmacias.append({"nombre": nombre_f, "ciudad": ciudad_f})
            log_event("🏪 FARMACIA CREADA", f"{nombre_f} - {ciudad_f}")
            st.success(f"Farmacia {nombre_f} creada")
            st.rerun()
    st.dataframe(pd.DataFrame(st.session_state.farmacias))

# ------------------------------------------------------------
# TAB EDITAR: Edición de inventario existente
# ------------------------------------------------------------
with tab2:
    st.subheader("✏️ Editar Inventario de Medicamentos")
    
    if st.session_state.inventory.empty:
        st.warning("No hay inventario cargado. Por favor, parametrice primero en la pestaña 'Parametrizar Inventario'")
    else:
        # Seleccionar medicamento a editar
        inv_copy = st.session_state.inventory.copy()
        inv_copy["display"] = inv_copy["med"] + " - " + inv_copy["cum"] + " - " + inv_copy["farmacia"]
        
        selected = st.selectbox("Seleccionar medicamento a editar", inv_copy["display"].tolist())
        
        if selected:
            idx = inv_copy[inv_copy["display"] == selected].index[0]
            current = inv_copy.loc[idx]
            
            with st.form("edit_inventory_form"):
                st.markdown(f"**Editando: {current['med']}**")
                col1, col2 = st.columns(2)
                
                with col1:
                    new_med = st.text_input("Medicamento", value=current["med"])
                    new_cum = st.text_input("CUM*", value=current["cum"])
                    new_ium = st.text_input("IUM*", value=current["ium"])
                    new_registro = st.text_input("Registro Sanitario*", value=current["registro_sanitario"])
                
                with col2:
                    # Obtener índice seguro para el selectbox
                    farmacia_lista = [f["nombre"] for f in st.session_state.farmacias]
                    current_farmacia_index = 0
                    if current["farmacia"] in farmacia_lista:
                        current_farmacia_index = farmacia_lista.index(current["farmacia"])
                    
                    new_farmacia = st.selectbox("Farmacia", farmacia_lista, index=current_farmacia_index)
                    new_stock_total = st.number_input("Stock Total", value=int(current["stock_total"]), min_value=0)
                    new_stock_reserved = st.number_input("Stock Reservado", value=int(current["stock_reserved"]), min_value=0, max_value=new_stock_total)
                
                col3, col4 = st.columns(2)
                with col3:
                    submitted = st.form_submit_button("💾 Guardar Cambios")
                with col4:
                    delete = st.form_submit_button("🗑️ Eliminar Medicamento", type="secondary")
                
                if submitted:
                    if not all([new_med, new_cum, new_ium, new_registro]):
                        st.error("CUM, IUM y Registro Sanitario son obligatorios")
                    else:
                        st.session_state.inventory.loc[idx, "med"] = new_med
                        st.session_state.inventory.loc[idx, "cum"] = new_cum
                        st.session_state.inventory.loc[idx, "ium"] = new_ium
                        st.session_state.inventory.loc[idx, "registro_sanitario"] = new_registro
                        st.session_state.inventory.loc[idx, "farmacia"] = new_farmacia
                        st.session_state.inventory.loc[idx, "stock_total"] = new_stock_total
                        st.session_state.inventory.loc[idx, "stock_reserved"] = new_stock_reserved
                        update_inventory_display()
                        log_event("✏️ INVENTARIO EDITADO", f"{new_med} (CUM:{new_cum}) - Stock actualizado")
                        st.success("Cambios guardados correctamente")
                        st.rerun()
                
                if delete:
                    st.session_state.inventory = st.session_state.inventory.drop(idx).reset_index(drop=True)
                    update_inventory_display()
                    log_event("🗑️ MEDICAMENTO ELIMINADO", f"{current['med']} (CUM:{current['cum']})")
                    st.warning(f"Medicamento {current['med']} eliminado del inventario")
                    st.rerun()

# ------------------------------------------------------------
# TAB 1: GENERACIÓN DE ORDEN (Evento: orden_medica_creada)
# ------------------------------------------------------------
with tab3:
    st.subheader("📋 1. Generación de la Orden Médica")
    
    if st.session_state.inventory.empty:
        st.error("⚠️ No hay inventario parametrizado. Por favor, cargue medicamentos en la pestaña 'Parametrizar Inventario'")
    else:
        col1, col2 = st.columns([1,2])
        
        with col1:
            with st.form("form_orden"):
                st.markdown("**Datos de la Prescripción**")
                
                # Selección por CUM
                inv_display = st.session_state.inventory.copy()
                inv_display["display"] = inv_display["med"] + " | CUM: " + inv_display["cum"] + " | IUM: " + inv_display["ium"]
                selected_med = st.selectbox("Medicamento", inv_display["display"].tolist())
                
                if selected_med:
                    idx = inv_display[inv_display["display"] == selected_med].index[0]
                    med_data = inv_display.loc[idx]
                    cum_value = med_data["cum"]
                    ium_value = med_data["ium"]
                    registro_value = med_data["registro_sanitario"]
                    
                    st.text_input("CUM", value=cum_value, disabled=True, key="cum_display")
                    st.text_input("IUM", value=ium_value, disabled=True, key="ium_display")
                    st.text_input("Registro Sanitario", value=registro_value, disabled=True, key="reg_display")
                else:
                    cum_value = ""
                    ium_value = ""
                    registro_value = ""
                    med_data = None
                
                cantidad = st.number_input("Cantidad prescrita", min_value=1, step=10)
                ips = st.text_input("IPS (Institución)", "IPS Salud Total")
                medico = st.text_input("Médico", "Dr. Ejemplo")
                
                submitted = st.form_submit_button("🚀 Emitir Orden Médica")
                if submitted and med_data is not None:
                    new_id = len(st.session_state.prescriptions) + 1
                    st.session_state.prescriptions.append({
                        "id": new_id,
                        "medicamento": med_data["med"],
                        "cum": cum_value,
                        "ium": ium_value,
                        "registro_sanitario": registro_value,
                        "cantidad": cantidad,
                        "ips": ips,
                        "medico": medico,
                        "farmacia": med_data["farmacia"],
                        "estado": "Pendiente de Autorización"
                    })
                    log_event("🟢 ORDEN CREADA", f"Orden #{new_id} - {med_data['med']} (CUM:{cum_value}) x{cantidad}")
                    st.success(f"Orden #{new_id} generada exitosamente.")
                    st.rerun()
        
        with col2:
            st.markdown("**Órdenes Recientes**")
            df_ords = pd.DataFrame(st.session_state.prescriptions)
            if not df_ords.empty:
                st.dataframe(df_ords[["id", "medicamento", "cum", "cantidad", "ips", "estado"]], use_container_width=True)
            else:
                st.info("No hay órdenes generadas aún.")

# ------------------------------------------------------------
# TAB 2: VALIDACIÓN Y AUTORIZACIÓN (Evento: orden_autorizada)
# ------------------------------------------------------------
with tab4:
    st.subheader("✅ 2. Validación y Autorización")
    
    pending_orders = [p for p in st.session_state.prescriptions if p["estado"] == "Pendiente de Autorización"]
    
    if not pending_orders:
        st.info("No hay órdenes pendientes de autorización.")
    else:
        selected_id = st.selectbox("Seleccionar orden a validar", [p["id"] for p in pending_orders])
        order = next((p for p in pending_orders if p["id"] == selected_id), None)
        
        if order:
            col_a, col_b = st.columns(2)
            with col_a:
                st.write("**Detalle de la Orden**")
                st.write(f"Medicamento: {order['medicamento']}")
                st.write(f"CUM: {order['cum']}")
                st.write(f"IUM: {order['ium']}")
                st.write(f"Registro Sanitario: {order['registro_sanitario']}")
                st.write(f"Cantidad: {order['cantidad']}")
            
            with col_b:
                decision = st.radio("Decisión", ["Aprobado", "Rechazado"], horizontal=True)
                num_aut = st.text_input("Número de Autorización", value=f"AUT-{selected_id:04d}")
                
                if st.button("📢 Enviar Decisión"):
                    if decision == "Rechazado":
                        order["estado"] = "Rechazado"
                        log_event("❌ ORDEN RECHAZADA", f"Orden #{selected_id} - {order['medicamento']} (CUM:{order['cum']}) rechazada")
                        st.warning(f"Orden #{selected_id} Rechazada.")
                    else:
                        order["estado"] = "Autorizada"
                        st.session_state.autorizaciones.append({
                            "id_orden": selected_id,
                            "estado": "Aprobado",
                            "num_aut": num_aut,
                            "cum": order["cum"]
                        })
                        log_event("✅ ORDEN AUTORIZADA", f"Orden #{selected_id} autorizada con #{num_aut}")
                        st.success(f"Orden #{selected_id} AUTORIZADA.")
                    st.rerun()
    
    st.divider()
    st.subheader("Historial de Autorizaciones")
    if st.session_state.autorizaciones:
        st.dataframe(pd.DataFrame(st.session_state.autorizaciones))

# ------------------------------------------------------------
# TAB 3: RESERVA DE INVENTARIO (Evento: reserva_creada)
# ------------------------------------------------------------
with tab5:
    st.subheader("📦 3. Reserva de Inventario")
    
    ordenes_autorizadas = [p for p in st.session_state.prescriptions if p["estado"] == "Autorizada"]
    ids_con_reserva = [r["id_orden"] for r in st.session_state.reservas]
    ordenes_para_reservar = [p for p in ordenes_autorizadas if p["id"] not in ids_con_reserva]
    
    if not ordenes_para_reservar:
        st.info("No hay órdenes autorizadas pendientes de reserva.")
    else:
        for order in ordenes_para_reservar:
            with st.container(border=True):
                col1, col2, col3 = st.columns([3,2,2])
                col1.write(f"**Orden #{order['id']}** - {order['medicamento']}")
                col1.write(f"CUM: {order['cum']} | IUM: {order['ium']}")
                col1.write(f"Cantidad: {order['cantidad']}")
                
                _, _, disp = get_stock_status(order['medicamento'], order['farmacia'], order['cum'])
                col3.metric("Stock Disponible", disp)
                
                if col3.button("✅ Confirmar Reserva", key=f"res_{order['id']}"):
                    exito = crear_reserva(order['id'], order['medicamento'], order['farmacia'], order['cum'], order['cantidad'])
                    if exito:
                        order["estado"] = "Reservado"
                        st.rerun()
    
    st.divider()
    st.subheader("Reservas Activas")
    if st.session_state.reservas:
        df_res = pd.DataFrame(st.session_state.reservas)
        st.dataframe(df_res, use_container_width=True)

# ------------------------------------------------------------
# TAB 4: DISPENSACIÓN CON DATOS DE ENTREGA
# ------------------------------------------------------------
with tab6:
    st.subheader("💊 4. Dispensación con Datos de Entrega")
    
    ordenes_con_reserva = [r["id_orden"] for r in st.session_state.reservas]
    ordenes_listas = [p for p in st.session_state.prescriptions if p["id"] in ordenes_con_reserva]
    
    if not ordenes_listas:
        st.info("No hay órdenes con reserva activa lista para dispensar.")
    else:
        for order in ordenes_listas:
            reserva = next((r for r in st.session_state.reservas if r["id_orden"] == order["id"]), None)
            if reserva:
                with st.container(border=True):
                    st.write(f"**Orden #{order['id']}**")
                    st.write(f"Medicamento: {order['medicamento']}")
                    st.write(f"CUM: {order['cum']} | IUM: {order['ium']}")
                    st.write(f"Registro Sanitario: {order['registro_sanitario']}")
                    st.write(f"Cantidad Reservada: {reserva['cantidad_reservada']} | Farmacia: {reserva['farmacia']}")
                    
                    st.markdown("**📦 Datos de la Entrega**")
                    col_a, col_b, col_c = st.columns(3)
                    with col_a:
                        nro_entrega = st.text_input("Número de Entrega", value=f"ENT-{order['id']:04d}", key=f"nro_{order['id']}")
                    with col_b:
                        lote = st.text_input("Lote", value=f"L{order['id']:04d}", key=f"lote_{order['id']}")
                    with col_c:
                        fecha_vencimiento = st.date_input("Fecha de Vencimiento", key=f"fv_{order['id']}")
                    
                    qty_dispensar = st.number_input("Cantidad a dispensar", min_value=1, max_value=reserva['cantidad_reservada'], 
                                                     value=reserva['cantidad_reservada'], key=f"disp_{order['id']}")
                    
                    if st.button("💊 Confirmar Dispensación", key=f"btn_disp_{order['id']}"):
                        exito = dispensar_medicamento(
                            order['id'], order['medicamento'], order['cum'], 
                            reserva['farmacia'], qty_dispensar, nro_entrega, lote, fecha_vencimiento
                        )
                        if exito:
                            if qty_dispensar == reserva['cantidad_reservada']:
                                order["estado"] = "Completado"
                            else:
                                order["estado"] = "Dispensado Parcial"
                            st.success(f"¡Dispensación exitosa! Entrega #{nro_entrega}")
                            st.rerun()
    
    st.divider()
    st.subheader("Historial de Dispensaciones")
    if st.session_state.dispensations:
        df_disp = pd.DataFrame(st.session_state.dispensations)
        st.dataframe(df_disp, use_container_width=True)

# ------------------------------------------------------------
# TAB 5: ANALÍTICA PREDICTIVA Y CONSOLIDACIÓN
# ------------------------------------------------------------
with tab7:
    st.subheader("📊 Módulo Analítico - Toma de Decisiones")
    
    col_a, col_b = st.columns(2)
    
    # Métricas de Rendimiento
    total_ords = len(st.session_state.prescriptions)
    total_disp = sum([d["cantidad_dispensada"] for d in st.session_state.dispensations]) if st.session_state.dispensations else 0
    total_reservado = sum([r["cantidad_reservada"] for r in st.session_state.reservas]) if st.session_state.reservas else 0
    
    col_a.metric("Órdenes Generadas", total_ords)
    col_a.metric("Unidades Dispensadas", total_disp)
    col_b.metric("Unidades Reservadas (Pendientes)", total_reservado)
    if total_ords > 0 and (total_disp + total_reservado) > 0:
        nivel_servicio = (total_disp / (total_disp + total_reservado)) * 100
        col_b.metric("Nivel de Servicio (Fill Rate)", f"{nivel_servicio:.1f}%")
    
    st.divider()
    
    # Gráfico: Demanda vs Stock
    st.subheader("📈 Planificación de Demanda y Abastecimiento")
    inv_df = st.session_state.inventory.copy()
    
    if not inv_df.empty:
        fig = px.bar(inv_df, x="med", y=["stock_total", "stock_reserved"], 
                     title="Comparación: Stock Total vs Reservado (Tiempo Real)",
                     barmode="group", labels={"value": "Unidades", "med": "Medicamento"})
        st.plotly_chart(fig, use_container_width=True)
        
        # Predicción simulada (analítica)
        st.subheader("🔮 Alertas Predictivas")
        for idx, row in inv_df.iterrows():
            disponibilidad = row["stock_disponible"] if "stock_disponible" in row else row["stock_total"] - row["stock_reserved"]
            if disponibilidad < 50:
                st.warning(f"⚠️ **Alerta:** Stock bajo de {row['med']} en {row['farmacia']}. Solo {disponibilidad} unidades disponibles. Reabastecer urgentemente.")
            elif disponibilidad < 200:
                st.info(f"📉 **Monitoreo:** {row['med']} en {row['farmacia']} tiene {disponibilidad} unidades. Considere reabastecimiento próximo.")
    else:
        st.info("Cargue inventario en la pestaña de Parametrización para ver analytics.")
