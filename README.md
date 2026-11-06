# Sustento: prototipo MVP

Plataforma de **modelo inverso**: el hogar dice cuánto quiere gastar y quiénes comen en casa. Un motor
MILP arma la canasta con productos de la Sabana sin pasarse del presupuesto, y el domicilio va incluido.

## Cómo correrlo

```bash
pip install -r requirements.txt
streamlit run frontend/app.py      # abre http://localhost:8501
python -m pytest -q                # pruebas
```

## Estructura

```
backend/
  config.py         parámetros calibrables (alpha, umbral, variedad, % agricultor, nombre "Cosecha Extra")
  etl.py            carga y cruza SIPSA / EVA / DANE / productores; simulador de boletín SIPSA
  precios.py        precio del día y heurística de antifragilidad (descuento alpha)
  optimizador.py    modelo MILP (scipy.optimize.milp / HiGHS), fallback y "Cambiar producto"
  canal_asistido.py mensaje y enlace de WhatsApp
  evidencia.py      registro de eventos y pedidos para el Paso 6 del Taller 4
frontend/app.py     interfaz Streamlit
data/               fuentes de prueba (CSV) · data/fotos/ · data/registros/ (se crea solo)
tests/              pytest
```

## Modelo matemático

- **Variables:** `x_l ∈ Z+` = unidades de cada lote (regular o Cosecha Extra) · `y_j ∈ {0,1}` = el producto entra o no
- **Objetivo:** `max Σ w_j · v_j · x_l` (w = peso según el hogar · v = valor nutricional × √kg)
- **Presupuesto:** `Σ (p_l + c_kg·kg_l) x_l + c_fijo ≤ B` (la última milla DANE va dentro de B)
- **Oferta EVA:** `x_l ≤ min(S_l, U_j)` · **Consumo:** `Σ x ≤ U_j·y_j`, `y_j ≤ Σ x`
- **Canasta básica:** al menos 1 tubérculo, 1 verdura y 1 fruta · **Variedad:** `Σ y ≥ 6`
- **Alpha:** `p_extra = p·(1−α)`, con `α = 0,20 + 1,5·(volatilidad − 0,08)`, entre 0,20 y 0,40
- **Fallback:** si no alcanza, se usan productos de temporada con α máximo; si aún no alcanza, canasta mínima. Si ni así alcanza, la app explica el error y sugiere el presupuesto mínimo.

## Para las pruebas con usuarios (Taller 4)

- Cada canasta, cambio de producto, pedido por WhatsApp, solicitud de llamada y pedido queda en
  `data/registros/eventos.csv` y `pedidos.csv`. El checkout pregunta *"¿la comprarías otra vez?"* y
  *"¿qué te haría dudar?"* para guardar las objeciones con las palabras de cada persona.
- El **Modo equipo** (barra lateral) muestra la conversión, permite descargar los CSV y simula un boletín SIPSA nuevo.
- **Fotos reales:** pon `data/fotos/<id_producto>.jpg` (por ejemplo `papaya.jpg`) y reemplazan al emoji.
- **WhatsApp del equipo:** define la variable `SUSTENTO_WHATSAPP=57300...` o edita `config.py`.

> Productores, fincas, precios de referencia de D1 y Rappi y boletines son **datos de ejemplo**. Hay que
> reemplazarlos por los productores aliados y por precios tomados en campo antes de mostrarlos como reales.
