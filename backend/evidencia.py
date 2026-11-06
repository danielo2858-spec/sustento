"""Registro de evidencia de comportamiento (Taller 4, Paso 6: "evidencia, no opiniones").

Cada acción relevante del usuario de prueba queda en data/registros/eventos.csv y
cada pedido confirmado en data/registros/pedidos.csv.
"""
from __future__ import annotations

import csv
import json
from datetime import datetime
from pathlib import Path

import pandas as pd

from . import config

_CAMPOS_EVENTO = ["fecha_hora", "sesion", "evento", "detalle"]


def _anexar(ruta: Path, campos: list[str], fila: dict) -> None:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    nuevo = not ruta.exists()
    with ruta.open("a", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=campos)
        if nuevo:
            w.writeheader()
        w.writerow(fila)


def registrar_evento(sesion: str, evento: str, directorio: Path | None = None, **detalle) -> None:
    """Nunca rompe la app: si no se puede escribir, se ignora."""
    try:
        _anexar(Path(directorio or config.REGISTROS_DIR) / "eventos.csv", _CAMPOS_EVENTO, {
            "fecha_hora": datetime.now().isoformat(timespec="seconds"),
            "sesion": sesion, "evento": evento,
            "detalle": json.dumps(detalle, ensure_ascii=False, default=str),
        })
    except OSError:
        pass


def guardar_pedido(pedido: dict, directorio: Path | None = None) -> None:
    campos = ["fecha_hora", "pedido_id", "sesion", "nombre", "telefono", "localidad", "direccion",
              "franja", "metodo_pago", "total", "productos", "volveria_a_comprar", "objecion"]
    fila = {"fecha_hora": datetime.now().isoformat(timespec="seconds"), **pedido}
    _anexar(Path(directorio or config.REGISTROS_DIR) / "pedidos.csv", campos,
            {k: fila.get(k, "") for k in campos})


def leer(nombre: str, directorio: Path | None = None) -> pd.DataFrame:
    ruta = Path(directorio or config.REGISTROS_DIR) / f"{nombre}.csv"
    if not ruta.exists():
        return pd.DataFrame()
    return pd.read_csv(ruta, encoding="utf-8")
