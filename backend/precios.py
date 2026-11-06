"""Precios del día y heurística de antifragilidad (descuento alpha)."""
from __future__ import annotations

import numpy as np

from . import config


def redondear(valor, paso: int = config.REDONDEO_PRECIO):
    """Redondea al múltiplo de `paso` más cercano (precios en COP)."""
    return (np.round(np.asarray(valor, dtype=float) / paso) * paso).astype(int)


def precio_dia(precio_base, factor_sipsa):
    """p_i = precio base x factor del boletín SIPSA del día."""
    return redondear(np.asarray(precio_base) * np.asarray(factor_sipsa))


def alpha_excedente(volatilidad, alpha_forzado: float | None = None):
    """Descuento alpha para lotes de excedente.

    - Base: ALPHA_MIN (el excedente siempre es más barato).
    - Si la volatilidad SIPSA supera el umbral, alpha sube linealmente
      (más caos de precios => más descuento sobre el excedente => la canasta
      sigue siendo factible dentro de B). Tope: ALPHA_MAX.
    - `alpha_forzado` lo usa el fallback para llevar todo al máximo.
    """
    vol = np.asarray(volatilidad, dtype=float)
    if alpha_forzado is not None:
        return np.full_like(vol, float(alpha_forzado))
    extra = np.clip(vol - config.UMBRAL_VOLATILIDAD, 0, None) * config.K_VOLATILIDAD
    return np.clip(config.ALPHA_MIN + extra, config.ALPHA_MIN, config.ALPHA_MAX)


def precio_estetico(p, alpha):
    """p_estetico = p_i * (1 - alpha)."""
    return redondear(np.asarray(p) * (1 - np.asarray(alpha)))
