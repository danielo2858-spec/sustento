"""Canal asistido: mensaje de WhatsApp y vista simple para leer por teléfono."""
from __future__ import annotations

from urllib.parse import quote

from . import config
from .optimizador import Canasta


def pesos(valor: int) -> str:
    return f"${valor:,.0f}".replace(",", ".")


def mensaje_whatsapp(canasta: Canasta, nombre: str = "", metodo_pago: str = "Efectivo contra entrega") -> str:
    lineas = [f"Hola Sustento 👋 Quiero pedir esta canasta{(' — ' + nombre) if nombre else ''}:", ""]
    for r in canasta.items.itertuples():
        extra = f" ({config.NOMBRE_EXCEDENTE})" if r.tipo == "cosecha_extra" else ""
        lineas.append(f"• {r.cantidad} x {r.nombre}{extra} – {r.unidad} – {pesos(r.subtotal)}")
    lineas += ["",
               f"Productos: {pesos(canasta.subtotal_productos)}",
               f"Domicilio ({canasta.perfil.localidad}): {pesos(canasta.costo_logistico)}",
               f"TOTAL: {pesos(canasta.total)} (mi presupuesto: {pesos(canasta.perfil.presupuesto)})",
               f"Pago: {metodo_pago}"]
    return "\n".join(lineas)


def enlace_whatsapp(texto: str) -> str:
    destino = config.WHATSAPP_NUMERO.strip()
    return f"https://wa.me/{destino}?text={quote(texto)}" if destino else f"https://wa.me/?text={quote(texto)}"
