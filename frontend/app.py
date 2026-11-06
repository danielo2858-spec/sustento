"""Sustento — interfaz de modelo inverso ("tu mercado en un clic").

Ejecutar desde la raíz del proyecto:
    streamlit run frontend/app.py
"""
from __future__ import annotations

import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pandas as pd
import streamlit as st

from backend import config, evidencia
from backend.canal_asistido import enlace_whatsapp, mensaje_whatsapp, pesos
from backend.etl import ErrorDatos, cargar_fuentes, simular_boletin_sipsa
from backend.optimizador import (NOMBRE_CATEGORIA, ORDEN_CATEGORIAS, PerfilHogar,
                                 PresupuestoInsuficiente, optimizar_canasta, sustituir_producto)

st.set_page_config(page_title="Sustento · tu mercado en un clic", page_icon="🧺", layout="wide")

st.markdown("""
<style>
  .block-container {max-width: 1100px; padding-top: 1.5rem;}
  .sx-emoji {font-size: 2.6rem; line-height: 1; text-align: center;}
  .sx-badge {display:inline-block; padding:2px 8px; border-radius:999px; font-size:.78rem;
             background:#e8f3ea; color:#1f4d2b; border:1px solid #b9d9c0; margin-left:4px;}
  .sx-bar {display:flex; height:18px; border-radius:9px; overflow:hidden; margin:.4rem 0 .6rem;}
  .sx-bar div {height:100%;}
  .sx-grande li {font-size:1.35rem; margin-bottom:.45rem;}
</style>
""", unsafe_allow_html=True)

MADUREZ = {"Me da igual": "indiferente", "Verde / pintón": "verde", "Maduro": "maduro"}
METODOS_PAGO = ["Efectivo contra entrega", "Nequi o Daviplata al recibir"]
FRANJAS = ["Sábado 8 a.m. – 12 m.", "Sábado 2 – 6 p.m.", "Domingo 8 a.m. – 12 m."]

ss = st.session_state
ss.setdefault("sesion", uuid.uuid4().hex[:8])
ss.setdefault("semilla_sipsa", None)
ss.setdefault("canasta", None)
ss.setdefault("aviso", None)
ss.setdefault("pedido", None)


# ----------------------------------------------------------------------------
# Datos
# ----------------------------------------------------------------------------
@st.cache_resource(show_spinner=False)
def _fuentes(semilla: int | None):
    f = cargar_fuentes()
    if semilla is not None:
        f.sipsa = simular_boletin_sipsa(f.productos, semilla)
    return f


def fuentes():
    return _fuentes(ss.semilla_sipsa)


def foto(producto_id: str) -> Path | None:
    for ext in ("jpg", "jpeg", "png", "webp"):
        p = config.FOTOS_DIR / f"{producto_id}.{ext}"
        if p.exists():
            return p
    return None


def log(evento: str, **detalle):
    evidencia.registrar_evento(ss.sesion, evento, **detalle)


# ----------------------------------------------------------------------------
# Acciones
# ----------------------------------------------------------------------------
def generar(perfil: PerfilHogar):
    ss.pedido = None
    try:
        with st.spinner("Armando tu canasta con los precios de hoy…"):
            ss.canasta = optimizar_canasta(perfil, fuentes())
        c = ss.canasta
        ss.aviso = None
        log("canasta_generada", presupuesto=perfil.presupuesto, personas=perfil.personas,
            localidad=perfil.localidad, etapa=c.etapa.nombre, total=c.total,
            productos=len(c.productos), cosecha_extra=perfil.incluir_cosecha_extra)
    except PresupuestoInsuficiente as e:
        ss.canasta = None
        log("presupuesto_insuficiente", presupuesto=perfil.presupuesto, minimo=e.minimo_sugerido)
        st.error(str(e))
        if e.minimo_sugerido:
            st.info(f"💡 Prueba con {pesos(e.minimo_sugerido)} o más, o activa {config.NOMBRE_EXCEDENTE}.")


def cambiar(producto_id: str):
    c = ss.canasta
    sale = c.items.loc[c.items["producto_id"] == producto_id, "nombre"].iloc[0]
    try:
        nueva, entran = sustituir_producto(c, producto_id, fuentes())
    except PresupuestoInsuficiente:
        ss.aviso = f"No encontramos un reemplazo para {sale} dentro de tu presupuesto."
        return
    ss.canasta = nueva
    nombres = nueva.items.drop_duplicates("producto_id").set_index("producto_id")["nombre"]
    if entran:
        ss.aviso = f"🔄 Cambiamos **{sale}** por **{', '.join(nombres[p] for p in entran)}**. Sigues dentro de tu presupuesto."
    else:
        ss.aviso = f"🔄 Quitamos **{sale}** y repartimos ese dinero en el resto de tu canasta."
    log("cambiar_producto", sale=producto_id, entran=entran, total=nueva.total)


def reiniciar():
    ss.canasta, ss.aviso, ss.pedido = None, None, None


# ----------------------------------------------------------------------------
# Barra lateral: modo equipo
# ----------------------------------------------------------------------------
with st.sidebar:
    st.markdown("### 🧺 Sustento")
    st.caption("Prototipo MVP · Taller 4")
    modo_equipo = st.toggle("Modo equipo", help="Solo para el equipo: boletín SIPSA y evidencia de las pruebas.")
    if modo_equipo:
        st.markdown("**Boletín de precios (SIPSA simulado)**")
        st.caption("Boletín de archivo" if ss.semilla_sipsa is None else f"Boletín aleatorio #{ss.semilla_sipsa}")
        c1, c2 = st.columns(2)
        nueva_semilla = ss.semilla_sipsa
        if c1.button("🎲 Nuevo boletín", width="stretch"):
            nueva_semilla = int(uuid.uuid4().int % 10_000)
        if c2.button("↩︎ Archivo", width="stretch"):
            nueva_semilla = None
        if nueva_semilla != ss.semilla_sipsa:
            ss.semilla_sipsa = nueva_semilla
            if ss.canasta is not None:  # recalcula la canasta actual con los precios nuevos
                generar(ss.canasta.perfil)
                if ss.canasta is not None:
                    ss.aviso = "📈 Precios del día actualizados: recalculamos tu canasta."
        with st.expander("Ver boletín del día"):
            st.dataframe(fuentes().sipsa, hide_index=True, width="stretch")

        st.divider()
        st.markdown("**Evidencia de las pruebas (Paso 6)**")
        ev = evidencia.leer("eventos")
        ped = evidencia.leer("pedidos")
        if ev.empty:
            st.caption("Aún no hay eventos registrados.")
        else:
            conteo = ev["evento"].value_counts()
            canastas = int(conteo.get("canasta_generada", 0))
            pedidos = int(conteo.get("pedido_confirmado", 0))
            m1, m2 = st.columns(2)
            m1.metric("Sesiones", ev["sesion"].nunique())
            m2.metric("Canastas", canastas)
            m1.metric("Pedidos", pedidos)
            m2.metric("Conversión", f"{(pedidos / canastas * 100) if canastas else 0:.0f}%")
            st.dataframe(conteo.rename("veces"), width="stretch")
            st.download_button("⬇️ eventos.csv", ev.to_csv(index=False).encode("utf-8"),
                               "eventos.csv", "text/csv", width="stretch")
        if not ped.empty:
            st.dataframe(ped[["pedido_id", "total", "metodo_pago", "volveria_a_comprar", "objecion"]],
                         hide_index=True, width="stretch")
            st.download_button("⬇️ pedidos.csv", ped.to_csv(index=False).encode("utf-8"),
                               "pedidos.csv", "text/csv", width="stretch")

# ----------------------------------------------------------------------------
# Encabezado
# ----------------------------------------------------------------------------
st.title("🧺 Sustento")
st.markdown("**Dinos cuánto tienes para el mercado. Nosotros lo armamos** con productos frescos, "
            "directo de productores de la Sabana, sin pasarnos de tu presupuesto.")

try:
    F = fuentes()
except ErrorDatos as e:
    st.error(f"No se pudieron cargar los datos: {e}")
    st.stop()

# ----------------------------------------------------------------------------
# Paso 1: onboarding
# ----------------------------------------------------------------------------
if ss.canasta is None:
    nombres = F.productos.drop_duplicates("nombre").set_index("id")["nombre"]
    with st.form("onboarding"):
        a, b = st.columns(2)
        with a:
            presupuesto = st.number_input("💰 ¿Cuánto quieres gastar esta semana? (incluye domicilio)",
                                          min_value=5_000, max_value=400_000, value=50_000, step=1_000)
            localidad = st.selectbox("📍 Localidad de entrega", F.localidades["localidad"].tolist(),
                                     index=F.localidades["localidad"].tolist().index("Kennedy"))
            st.markdown("**👨‍👩‍👧 ¿Quiénes comen en tu casa?**")
            p1, p2, p3 = st.columns(3)
            adultos = p1.number_input("Adultos", 0, 12, 2)
            ninos = p2.number_input("Niños", 0, 12, 1)
            mayores = p3.number_input("Mayores de 60", 0, 12, 0)
        with b:
            tomate = st.radio("🍅 Tomate", list(MADUREZ), horizontal=True)
            platano = st.radio("🍌 Plátano", list(MADUREZ), horizontal=True)
            excluidos = st.multiselect("🚫 ¿Qué NO comen en tu casa?", nombres.index.tolist(),
                                       format_func=lambda i: nombres[i],
                                       placeholder="Ej.: brócoli, habichuela…")
            extra = st.toggle(f"Incluir {config.NOMBRE_EXCEDENTE}", value=True,
                              help="Productos perfectos por dentro, con forma o tamaño distinto. "
                                   "Mismo sabor, menor precio, y ayudas a que no se pierda la cosecha.")
        enviar = st.form_submit_button("🧺 Armar mi canasta", type="primary", width="stretch")
    if enviar:
        excl = set(excluidos)
        # Si excluyen un producto con variantes de madurez, se excluyen ambas variantes.
        for pid in list(excl):
            grupo = F.productos.loc[F.productos["id"] == pid, "grupo_madurez"].iloc[0]
            if grupo:
                excl |= set(F.productos.loc[F.productos["grupo_madurez"] == grupo, "id"])
        try:
            perfil = PerfilHogar(int(presupuesto), localidad, int(adultos), int(ninos), int(mayores),
                                 excluidos=tuple(sorted(excl)),
                                 madurez={"tomate": MADUREZ[tomate], "platano": MADUREZ[platano]},
                                 incluir_cosecha_extra=extra)
            perfil.validar()
        except ValueError as e:
            st.error(str(e))
        else:
            generar(perfil)
            if ss.canasta is not None:
                st.rerun()
    st.stop()

# ----------------------------------------------------------------------------
# Paso 2: dashboard de la canasta
# ----------------------------------------------------------------------------
C = ss.canasta
comp, des, imp = C.comparativo(), C.desglose(), C.impacto()

top_a, top_b = st.columns([4, 1])
top_a.markdown(f"#### Tu canasta para **{C.perfil.personas} personas** · {C.perfil.localidad}")
top_b.button("✏️ Cambiar mis datos", on_click=reiniciar, width="stretch")
if C.etapa.mensaje:
    st.warning(C.etapa.mensaje)
if ss.aviso:
    st.success(ss.aviso)

m = st.columns(4)
m[0].metric("Total con domicilio", pesos(C.total), f"de {pesos(C.perfil.presupuesto)}", delta_color="off")
m[1].metric("Te sobran", pesos(C.sobrante))
m[2].metric("Ahorras vs. D1", pesos(comp["ahorro_d1"]))
m[3].metric("Ahorras vs. Rappi", pesos(comp["ahorro_rappi"]))

tab_canasta, tab_origen, tab_wpp, tab_pedido = st.tabs(
    ["🧺 Tu canasta", "👩‍🌾 De dónde viene", "💬 Pedir por WhatsApp", "✅ Confirmar pedido"])

with tab_canasta:
    izq, der = st.columns([3, 2], gap="large")
    with izq:
        for cat in ORDEN_CATEGORIAS:
            grupo = C.items[C.items["categoria"] == cat]
            if grupo.empty:
                continue
            st.markdown(f"**{NOMBRE_CATEGORIA[cat]}**")
            for r in grupo.itertuples():
                with st.container(border=True):
                    c0, c1, c2, c3 = st.columns([1, 5, 2, 2], vertical_alignment="center")
                    f = foto(r.producto_id)
                    if f:
                        c0.image(str(f), width="stretch")
                    else:
                        c0.markdown(f"<div class='sx-emoji'>{r.emoji}</div>", unsafe_allow_html=True)
                    badge = (f"<span class='sx-badge'>{config.NOMBRE_EXCEDENTE} −{r.alpha:.0%}</span>"
                             if r.tipo == "cosecha_extra" else "")
                    c1.markdown(f"**{r.nombre}**{badge}<br><small>{r.unidad} · {r.prod_nombre}, "
                                f"vereda {r.prod_vereda} ({r.prod_municipio})</small>",
                                unsafe_allow_html=True)
                    if r.tipo == "cosecha_extra" and r.motivo_excedente:
                        c1.caption(f"¿Por qué más barato? {r.motivo_excedente}.")
                    c2.markdown(f"{r.cantidad} × {pesos(r.precio)}<br>**{pesos(r.subtotal)}**",
                                unsafe_allow_html=True)
                    c3.button("🔄 Cambiar", key=f"cambiar_{r.key}", on_click=cambiar,
                              args=(r.producto_id,), width="stretch")
    with der:
        with st.container(border=True):
            st.markdown("**¿A dónde va tu plata?**")
            tot = max(C.total, 1)
            st.markdown(
                "<div class='sx-bar'>"
                f"<div style='width:{des['agricultor'] / tot:.1%};background:#2f6b3a'></div>"
                f"<div style='width:{des['logistica'] / tot:.1%};background:#d9a441'></div>"
                f"<div style='width:{des['plataforma'] / tot:.1%};background:#c8704a'></div></div>",
                unsafe_allow_html=True)
            st.markdown(f"🟩 Agricultores: **{pesos(des['agricultor'])}**  \n"
                        f"🟨 Domicilio: **{pesos(des['logistica'])}**  \n"
                        f"🟧 Sustento (acopio, empaque, operación): **{pesos(des['plataforma'])}**")
            st.caption(f"Los agricultores reciben el {config.PARTICIPACION_AGRICULTOR:.0%} del valor de los productos.")
        with st.container(border=True):
            st.markdown("**Tu impacto esta semana**")
            st.markdown(f"Le pagas precio justo a **{imp['productores']} productores** y llevas "
                        f"**{imp['kg_total']:.1f} kg** de comida fresca.")
            if imp["kg_rescatados"] > 0:
                st.markdown(f"🌱 Evitas que se pierdan **{imp['kg_rescatados']:.1f} kg** de {config.NOMBRE_EXCEDENTE}.")
        with st.container(border=True):
            st.markdown("**La misma canasta en otras partes**")
            st.dataframe(pd.DataFrame({
                "Dónde": ["Sustento (con domicilio)", "D1 (en tienda, sin domicilio)", "Rappi (con domicilio)"],
                "Total": [pesos(comp["sustento"]), pesos(comp["d1"]), pesos(comp["rappi"])],
            }), hide_index=True, width="stretch")
            st.caption("Precios de referencia simulados para el prototipo: validar en campo.")
        with st.container(border=True):
            st.markdown("🛡️ **Garantía Sustento**: si algo llega mal, te lo cambiamos o te devolvemos "
                        "la plata, sin trámites. Y siempre hay una persona a quien llamar.")

with tab_origen:
    prod = (C.items.groupby(["prod_nombre", "prod_finca", "prod_vereda", "prod_municipio",
                             "prod_region", "prod_lat", "prod_lon", "prod_anos_cultivando"],
                            as_index=False)
            .agg(productos=("nombre", lambda s: ", ".join(dict.fromkeys(s)))))
    st.map(prod.rename(columns={"prod_lat": "lat", "prod_lon": "lon"}), latitude="lat",
           longitude="lon", size=900, color="#2f6b3a")
    cols = st.columns(2)
    for k, r in enumerate(prod.itertuples()):
        with cols[k % 2].container(border=True):
            st.markdown(f"🪪 **{r.prod_nombre}** · {r.prod_finca}")
            st.markdown(f"📍 Vereda {r.prod_vereda}, {r.prod_municipio} ({r.prod_region})  \n"
                        f"🌾 {r.prod_anos_cultivando} años cultivando  \n🧺 Te envía: {r.productos}")
    st.caption("Productores y fincas: datos de ejemplo del prototipo. Reemplazar por los productores aliados reales.")

with tab_wpp:
    st.markdown("¿Prefieres pedir por **WhatsApp o por teléfono**? Te ayudamos a hacerlo, o un familiar "
                "puede pedir por ti con este mensaje.")
    texto = mensaje_whatsapp(C)
    if st.button("💬 Preparar mi pedido por WhatsApp", type="primary"):
        log("whatsapp_preparado", total=C.total)
        ss.wpp_listo = True
    if ss.get("wpp_listo"):
        st.link_button("Abrir WhatsApp ↗", enlace_whatsapp(texto))
        st.code(texto, language=None)
    st.divider()
    st.markdown("**📞 ¿Prefieres que te llamemos?**")
    with st.form("llamada"):
        tel = st.text_input("Tu número de celular")
        if st.form_submit_button("Que me llamen"):
            if tel.strip():
                log("solicitud_llamada", telefono=tel.strip(), total=C.total)
                st.success("Listo. Una persona del equipo te llamará para confirmar tu canasta.")
            else:
                st.error("Escribe un número para poder llamarte.")
    with st.expander("👓 Vista grande para leer la canasta por teléfono"):
        st.markdown("<ul class='sx-grande'>" + "".join(
            f"<li>{r.emoji} {r.cantidad} × {r.nombre} — {pesos(r.subtotal)}</li>" for r in C.items.itertuples())
            + f"</ul><p style='font-size:1.5rem'><b>Total: {pesos(C.total)}</b></p>", unsafe_allow_html=True)

with tab_pedido:
    if ss.pedido:
        st.success(f"✅ ¡Pedido **{ss.pedido}** confirmado! Pagas {pesos(C.total)} cuando te llegue.")
        st.markdown("Te escribiremos por WhatsApp para confirmar la hora. Si algo llega mal, lo cambiamos sin trámites.")
        st.button("🧺 Armar otra canasta", on_click=reiniciar)
    else:
        st.markdown(f"Pagas **{pesos(C.total)} cuando recibas tu canasta**. Nada de pagos por internet.")
        with st.form("checkout"):
            a, b = st.columns(2)
            nombre = a.text_input("Nombre")
            telefono = b.text_input("Celular (WhatsApp)")
            direccion = st.text_input(f"Dirección en {C.perfil.localidad}")
            franja = a.selectbox("¿Cuándo te la llevamos?", FRANJAS)
            metodo = b.radio("¿Cómo pagas al recibir?", METODOS_PAGO)
            st.markdown("**Dos preguntas rápidas (nos ayudan a mejorar)**")
            volveria = st.radio("¿Comprarías esta canasta otra vez la próxima semana?",
                                ["Sí", "Tal vez", "No"], horizontal=True, index=None)
            objecion = st.text_input("¿Qué te haría dudar de pedirla? (con tus palabras)")
            confirmar = st.form_submit_button("✅ Confirmar pedido", type="primary", width="stretch")
        if confirmar:
            if not (nombre.strip() and telefono.strip() and direccion.strip()):
                st.error("Necesitamos tu nombre, celular y dirección para llevarte la canasta.")
            else:
                pid = "SU-" + uuid.uuid4().hex[:6].upper()
                evidencia.guardar_pedido({
                    "pedido_id": pid, "sesion": ss.sesion, "nombre": nombre.strip(),
                    "telefono": telefono.strip(), "localidad": C.perfil.localidad,
                    "direccion": direccion.strip(), "franja": franja, "metodo_pago": metodo,
                    "total": C.total, "productos": "; ".join(f"{r.cantidad}x {r.nombre}" for r in C.items.itertuples()),
                    "volveria_a_comprar": volveria or "", "objecion": objecion.strip()})
                log("pedido_confirmado", pedido=pid, total=C.total, metodo=metodo,
                    volveria=volveria, objecion=objecion.strip())
                ss.pedido = pid
                st.rerun()
