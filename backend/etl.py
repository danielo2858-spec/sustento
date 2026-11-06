"""ETL: carga y cruza las fuentes de prueba.

- productos.csv       catálogo interno (precio base, valor nutricional, productor)
- sipsa_boletin.csv   factor de precio del día y volatilidad 7 días (simula SIPSA)
- eva_oferta.csv      oferta semanal S_i y excedentes por producto (simula EVA)
- dane_localidades.csv costo logístico de última milla por localidad (simula DANE)
- productores.csv     "DNI del agricultor" (datos de ejemplo)
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from . import config


class ErrorDatos(Exception):
    """Faltan archivos o columnas en las fuentes."""


COLUMNAS = {
    "productos": {"id", "nombre", "categoria", "unidad", "kg_unidad", "precio_base",
                  "valor_nutricional", "consumo_semanal_persona", "emoji", "productor_id",
                  "grupo_madurez", "madurez", "precio_ref_d1", "precio_ref_rappi"},
    "eva_oferta": {"producto_id", "oferta_semanal_unid", "excedente_unid",
                   "motivo_excedente", "temporada"},
    "sipsa_boletin": {"producto_id", "factor_precio_hoy", "volatilidad_7d"},
    "dane_localidades": {"localidad", "costo_fijo", "costo_por_kg", "lat", "lon"},
    "productores": {"productor_id", "nombre", "finca", "vereda", "municipio", "lat", "lon"},
}


def _leer(nombre: str, data_dir: Path) -> pd.DataFrame:
    ruta = Path(data_dir) / f"{nombre}.csv"
    if not ruta.exists():
        raise ErrorDatos(f"No se encontró {ruta}")
    df = pd.read_csv(ruta, encoding="utf-8")
    faltan = COLUMNAS[nombre] - set(df.columns)
    if faltan:
        raise ErrorDatos(f"{ruta.name}: faltan columnas {sorted(faltan)}")
    return df


@dataclass
class Fuentes:
    productos: pd.DataFrame
    oferta: pd.DataFrame
    sipsa: pd.DataFrame
    localidades: pd.DataFrame
    productores: pd.DataFrame

    def costo_logistico(self, localidad: str) -> tuple[int, int]:
        fila = self.localidades.loc[self.localidades["localidad"] == localidad]
        if fila.empty:
            raise ValueError(f"Localidad desconocida: {localidad}")
        return int(fila["costo_fijo"].iloc[0]), int(fila["costo_por_kg"].iloc[0])


def cargar_fuentes(data_dir: Path | None = None, sipsa: pd.DataFrame | None = None) -> Fuentes:
    data_dir = Path(data_dir or config.DATA_DIR)
    productos = _leer("productos", data_dir)
    productos["grupo_madurez"] = productos["grupo_madurez"].fillna("")
    productos["madurez"] = productos["madurez"].fillna("")
    oferta = _leer("eva_oferta", data_dir)
    oferta["motivo_excedente"] = oferta["motivo_excedente"].fillna("")
    return Fuentes(
        productos=productos,
        oferta=oferta,
        sipsa=sipsa if sipsa is not None else _leer("sipsa_boletin", data_dir),
        localidades=_leer("dane_localidades", data_dir),
        productores=_leer("productores", data_dir),
    )


def simular_boletin_sipsa(productos: pd.DataFrame, semilla: int | None = None) -> pd.DataFrame:
    """Genera un boletín SIPSA sintético (para demostrar la antifragilidad).

    Factor de precio ~ lognormal alrededor de 1, volatilidad 1-25 %.
    """
    rng = np.random.default_rng(semilla)
    n = len(productos)
    vol = rng.uniform(0.01, 0.25, n)
    factor = np.exp(rng.normal(0.0, vol))
    return pd.DataFrame({
        "producto_id": productos["id"].to_numpy(),
        "factor_precio_hoy": np.round(factor, 3),
        "volatilidad_7d": np.round(vol, 3),
    })


def tabla_maestra(f: Fuentes) -> pd.DataFrame:
    """Une productos + SIPSA + EVA + productor en una sola tabla por producto."""
    df = (f.productos
          .merge(f.sipsa, left_on="id", right_on="producto_id", how="left")
          .drop(columns="producto_id")
          .merge(f.oferta, left_on="id", right_on="producto_id", how="left")
          .drop(columns="producto_id")
          .merge(f.productores.add_prefix("prod_"), left_on="productor_id",
                 right_on="prod_productor_id", how="left")
          .drop(columns="prod_productor_id"))
    # Sin dato SIPSA: precio base y volatilidad 0. Sin dato EVA: sin oferta.
    df["factor_precio_hoy"] = df["factor_precio_hoy"].fillna(1.0)
    df["volatilidad_7d"] = df["volatilidad_7d"].fillna(0.0)
    df["oferta_semanal_unid"] = df["oferta_semanal_unid"].fillna(0).astype(int)
    df["excedente_unid"] = df["excedente_unid"].fillna(0).astype(int)
    df["motivo_excedente"] = df["motivo_excedente"].fillna("")
    df["temporada"] = df["temporada"].fillna("media")
    return df
