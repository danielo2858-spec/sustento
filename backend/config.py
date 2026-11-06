"""Parámetros del modelo. Todo lo que el equipo quiera calibrar vive aquí."""
import os
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("SUSTENTO_DATA_DIR", RAIZ / "data"))
REGISTROS_DIR = Path(os.environ.get("SUSTENTO_REGISTROS_DIR", DATA_DIR / "registros"))
FOTOS_DIR = DATA_DIR / "fotos"

# --- Nombre comercial del excedente --------------------------------------
# Las entrevistas mostraron que "descuento estético" suena a "fruta de segunda"
# (6/10 lo cuestionaron). En código se sigue llamando alpha; en la interfaz se
# muestra con este nombre, que el equipo puede cambiar sin tocar nada más.
NOMBRE_EXCEDENTE = "Cosecha Extra"

# --- Heurística de antifragilidad (descuento alpha) ----------------------
ALPHA_MIN = 0.20          # descuento base de todo lote de excedente
ALPHA_MAX = 0.40          # tope (también se usa en el fallback)
UMBRAL_VOLATILIDAD = 0.08  # volatilidad SIPSA 7 días a partir de la cual sube alpha
K_VOLATILIDAD = 1.5       # cuánto sube alpha por cada punto de volatilidad sobre el umbral

# --- Composición de la canasta ------------------------------------------
CATEGORIAS_BASICAS = ("tuberculo", "hortaliza", "fruta")
MIN_VARIEDAD = 6          # productos distintos mínimos en la canasta normal
MIN_VARIEDAD_FALLBACK = 3
REDONDEO_PRECIO = 100     # los precios se redondean a $100 COP
TIEMPO_LIMITE_SOLVER = 10  # segundos

# --- Reparto de cada peso (transparencia pedida en entrevistas) ----------
PARTICIPACION_AGRICULTOR = 0.70   # del valor de producto
# El 30 % restante es la operación de la plataforma (acopio, empaque, margen).

# --- Referencias de competencia (SIMULADAS: validar en campo) ------------
RAPPI_DOMICILIO = 6900

# --- Canal asistido -----------------------------------------------------
# Número de WhatsApp del equipo en formato internacional sin '+', p. ej. 573001234567.
# Vacío = el enlace abre WhatsApp para que la persona elija el contacto.
WHATSAPP_NUMERO = os.environ.get("SUSTENTO_WHATSAPP", "")
