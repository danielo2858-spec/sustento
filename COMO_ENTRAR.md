# Cómo entrar al prototipo de Sustento (http://localhost:8501)

`http://localhost:8501` es la dirección de la app **en el computador donde se está ejecutando**.
"localhost" quiere decir "este mismo computador", así que el link solo abre si antes encendiste la app
en esa máquina (pasos 1 a 3). Si le mandas el link a otra persona, no le va a abrir.

---

## 1. Instalar lo necesario (solo la primera vez)

1. Instala **Python 3.10 o más reciente** desde https://www.python.org/downloads/.
   En Windows, marca la casilla **"Add Python to PATH"** al instalar.
2. Instala **Git** desde https://git-scm.com/downloads.

## 2. Descargar el proyecto (solo la primera vez)

Abre una terminal (en Windows: *PowerShell* o *Git Bash*) y escribe:

```bash
git clone https://github.com/danielo2858-spec/sustento.git
cd sustento
python -m pip install -r requirements.txt
```

> Si no quieres usar Git, en la página del repositorio ve a **Code → Download ZIP**, descomprímelo,
> abre una terminal dentro de la carpeta y ejecuta solo la última línea.

## 3. Encender la app (cada vez que la quieras usar)

Desde la carpeta del proyecto:

```bash
python -m streamlit run frontend/app.py
```

Vas a ver algo así:

```
  You can now view your Streamlit app in your browser.
  Local URL: http://localhost:8501
  Network URL: http://192.168.1.6:8501
```

El navegador se abre solo. Si no se abre, entra a mano a **http://localhost:8501**.

⚠️ **No cierres esa terminal** mientras uses la app: si la cierras, la app se apaga.
Para apagarla a propósito, presiona **Ctrl + C** en la terminal.

## 4. Abrirla desde un celular (para las pruebas con usuarios)

1. El celular y el computador deben estar en la **misma red WiFi**.
2. En el celular, abre el **Network URL** que aparece en la terminal (por ejemplo `http://192.168.1.6:8501`).
   Ese número cambia según la red, así que usa el que te muestre tu terminal.
3. Si no carga, Windows puede estar bloqueándolo. Cuando aparezca el aviso del Firewall, permite el acceso de
   Python en **redes privadas**.

## 5. Cómo usar la app

1. **Tus datos:** presupuesto semanal (incluye domicilio), localidad, quiénes comen en casa, cómo prefieren el
   tomate y el plátano, qué no comen y si aceptan *Cosecha Extra*. Luego oprime **"Armar mi canasta"**.
2. **Tu canasta:** la canasta que armó el motor, cuánto ahorras frente a D1 y Rappi, a dónde va tu plata y el
   botón **🔄 Cambiar** en cada producto.
3. **De dónde viene:** el mapa y la ficha de cada productor.
4. **Pedir por WhatsApp:** el mensaje listo para enviar, la opción "Que me llamen" y la vista en letra grande.
5. **Confirmar pedido:** pago contra entrega en efectivo o Nequi, más dos preguntas cortas de retroalimentación.

**Modo equipo** (interruptor en la barra lateral izquierda): muestra la evidencia de las pruebas (sesiones,
canastas, pedidos, conversión y objeciones), permite descargar `eventos.csv` y `pedidos.csv` y simula un
boletín SIPSA nuevo. Los registros se guardan en `data/registros/`.

## Problemas comunes

| Qué pasa | Qué hacer |
|---|---|
| `python` no se reconoce | Reinstala Python marcando "Add Python to PATH", o usa `py` en lugar de `python`. |
| `streamlit` no se reconoce | Usa siempre `python -m streamlit run frontend/app.py`. |
| `No module named ...` | Ejecuta otra vez `python -m pip install -r requirements.txt` dentro de la carpeta del proyecto. |
| "Port 8501 is already in use" | La app ya está encendida en otra terminal: entra directo al link. O usa otro puerto con `python -m streamlit run frontend/app.py --server.port 8502` y abre `http://localhost:8502`. |
| La página dice "This site can't be reached" | La app no está encendida: repite el paso 3. |
| El celular no abre el link | Revisa que esté en la misma WiFi y permite Python en el Firewall (paso 4). |

## Verificar que todo funciona (opcional)

```bash
python -m pytest -q
```

Debe terminar con `57 passed`.

---

¿Necesitan un link que funcione para cualquiera, sin instalar nada (por ejemplo para entregar el Taller 4)?
Hay que publicar la app en **Streamlit Community Cloud** (gratis): entren a https://share.streamlit.io con la
cuenta de GitHub, elijan este repositorio y como archivo principal `frontend/app.py`. Así obtienen una dirección
pública del tipo `https://sustento.streamlit.app`.
