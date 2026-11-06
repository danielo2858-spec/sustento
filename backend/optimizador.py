"""Motor de optimización MILP de la canasta (modelo inverso).

Variables
    x_l  ∈ Z+   unidades del lote l (cada producto tiene un lote "regular" y,
                si hay excedente en EVA, un lote "cosecha_extra" con descuento alpha)
    y_j  ∈ {0,1} el producto j entra o no en la canasta

Función objetivo
    max Z = Σ_l  w_j(l) · v_j(l) · x_l
    w_j : peso de la categoría según la composición del hogar (frontend)
    v_j : valor nutricional por unidad × √(kg por unidad)   ("valor y volumen")

Restricciones
    (1) Presupuesto de borde:  Σ_l (p_l + c_kg·kg_l) x_l + c_fijo  ≤  B
        (la última milla, DANE, se incluye de forma transparente dentro de B)
    (2) Abastecimiento (EVA):  0 ≤ x_l ≤ min(S_l, U_j)
    (3) Consumo del hogar:     Σ_{l∈j} x_l ≤ U_j · y_j
    (4) Activación:            y_j ≤ Σ_{l∈j} x_l
    (5) Canasta básica:        Σ_{j∈c} y_j ≥ 1   para c ∈ {tubérculo, hortaliza, fruta}
    (6) Variedad:              Σ_j y_j ≥ V_min

Si el problema es infactible se activa una cascada de fallback (productos de
temporada + alpha máximo -> canasta mínima). Si ni así alcanza, se lanza
PresupuestoInsuficiente con el presupuesto mínimo sugerido.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd
from scipy.optimize import Bounds, LinearConstraint, milp

from . import config
from .etl import Fuentes, tabla_maestra
from .precios import alpha_excedente, precio_dia, precio_estetico

ORDEN_CATEGORIAS = ["tuberculo", "leguminosa", "hortaliza", "hoja", "fruta", "proteina", "lacteo"]
NOMBRE_CATEGORIA = {
    "tuberculo": "Tubérculos y plátano", "leguminosa": "Granos", "hortaliza": "Verduras",
    "hoja": "Hojas verdes", "fruta": "Frutas", "proteina": "Proteína", "lacteo": "Lácteos",
}


# ----------------------------------------------------------------------------
# Entradas
# ----------------------------------------------------------------------------
class PresupuestoInsuficiente(Exception):
    def __init__(self, mensaje: str, minimo_sugerido: int | None):
        super().__init__(mensaje)
        self.minimo_sugerido = minimo_sugerido


@dataclass
class PerfilHogar:
    presupuesto: int
    localidad: str
    adultos: int = 2
    ninos: int = 0
    mayores: int = 0
    excluidos: tuple[str, ...] = ()
    madurez: dict[str, str] = field(default_factory=dict)  # grupo -> verde|maduro|indiferente
    incluir_cosecha_extra: bool = True

    @property
    def personas(self) -> int:
        return self.adultos + self.ninos + self.mayores

    @property
    def personas_equivalentes(self) -> float:
        # Un niño consume ~60 % de la porción de un adulto.
        return self.adultos + self.mayores + 0.6 * self.ninos

    def validar(self) -> None:
        if min(self.adultos, self.ninos, self.mayores) < 0:
            raise ValueError("El número de personas no puede ser negativo.")
        if self.personas < 1:
            raise ValueError("El hogar debe tener al menos una persona.")
        if self.presupuesto <= 0:
            raise ValueError("El presupuesto debe ser mayor que cero.")


def pesos_hogar(perfil: PerfilHogar) -> dict[str, float]:
    """w por categoría según composición del hogar."""
    n = perfil.personas
    sn, sm = perfil.ninos / n, perfil.mayores / n
    return {
        "tuberculo": 0.9 - 0.1 * sm,
        "leguminosa": 1.0 + 0.3 * sm,
        "hortaliza": 1.1,
        "hoja": 1.1 + 0.3 * sm,
        "fruta": 1.0 + 0.4 * sn,
        "proteina": 1.0 + 0.3 * sn,
        "lacteo": 0.9 + 0.4 * sn,
    }


@dataclass(frozen=True)
class Etapa:
    nombre: str
    mensaje: str
    min_variedad: int
    cobertura: bool
    alpha_forzado: float | None
    solo_temporada_alta: bool


_MSG_FALLBACK = (f"Tu presupuesto no alcanzaba para la canasta completa, así que la armamos con "
                 f"productos de temporada y el máximo precio de {config.NOMBRE_EXCEDENTE}.")
ETAPAS = (
    Etapa("normal", "", config.MIN_VARIEDAD, True, None, False),
    Etapa("fallback_temporada", _MSG_FALLBACK, config.MIN_VARIEDAD_FALLBACK, True, config.ALPHA_MAX, True),
    Etapa("fallback_amplio", _MSG_FALLBACK, config.MIN_VARIEDAD_FALLBACK, True, config.ALPHA_MAX, False),
    Etapa("minima", "Con este presupuesto solo alcanza una canasta mínima que no cubre todos los grupos "
          "(tubérculo, verdura y fruta).", 1, False, config.ALPHA_MAX, False),
)
ETAPAS_POR_NOMBRE = {e.nombre: e for e in ETAPAS}


# ----------------------------------------------------------------------------
# Construcción del problema
# ----------------------------------------------------------------------------
def construir_lotes(maestra: pd.DataFrame, perfil: PerfilHogar, etapa: Etapa,
                    costo_kg: int) -> pd.DataFrame:
    df = maestra[~maestra["id"].isin(perfil.excluidos)]
    df = df[df["oferta_semanal_unid"] + df["excedente_unid"] > 0]
    for grupo, pref in perfil.madurez.items():
        if pref and pref != "indiferente":
            df = df[~((df["grupo_madurez"] == grupo) & (df["madurez"] != pref))]
    if etapa.solo_temporada_alta:
        df = df[df["temporada"] == "alta"]
    if df.empty:
        return pd.DataFrame()

    df = df.copy()
    pesos = pesos_hogar(perfil)
    df["p"] = precio_dia(df["precio_base"], df["factor_precio_hoy"])
    df["w"] = df["categoria"].map(pesos).fillna(1.0)
    df["v"] = df["valor_nutricional"] * np.sqrt(df["kg_unidad"])
    df["U"] = np.maximum(1, np.ceil(df["consumo_semanal_persona"] * perfil.personas_equivalentes)).astype(int)
    df["ref_d1"] = precio_dia(df["precio_ref_d1"], df["factor_precio_hoy"])
    df["ref_rappi"] = precio_dia(df["precio_ref_rappi"], df["factor_precio_hoy"])

    regular = df.assign(tipo="regular", precio=df["p"], alpha=0.0,
                        cap=np.minimum(df["U"], df["oferta_semanal_unid"]))
    lotes = [regular[regular["cap"] > 0]]
    if perfil.incluir_cosecha_extra:
        exc = df[df["excedente_unid"] > 0]
        if not exc.empty:
            a = alpha_excedente(exc["volatilidad_7d"], etapa.alpha_forzado)
            lotes.append(exc.assign(tipo="cosecha_extra", alpha=a,
                                    precio=precio_estetico(exc["p"], a),
                                    cap=np.minimum(exc["U"], exc["excedente_unid"])))
    out = pd.concat(lotes, ignore_index=True)
    out["costo_var"] = np.ceil(costo_kg * out["kg_unidad"]).astype(int)
    out["key"] = out["id"] + "|" + out["tipo"]
    return out.reset_index(drop=True)


def _resolver(lotes: pd.DataFrame, presupuesto_neto: int, min_variedad: int,
              cobertura: bool, fijos: dict[str, int] | None = None) -> np.ndarray | None:
    """Resuelve el MILP. Devuelve x (enteros) o None si es infactible."""
    L = len(lotes)
    productos = list(dict.fromkeys(lotes["id"]))
    P = len(productos)
    idx_prod = {pid: k for k, pid in enumerate(productos)}
    U = lotes.groupby("id")["U"].first().reindex(productos).to_numpy()
    cat_prod = lotes.groupby("id")["categoria"].first().reindex(productos).to_numpy()

    # Objetivo (milp minimiza): -Σ w v x  + desempate mínimo hacia lo más barato
    valor = (lotes["w"] * lotes["v"]).to_numpy()
    costo = (lotes["precio"] + lotes["costo_var"]).to_numpy(dtype=float)
    c = np.concatenate([-valor + 1e-7 * costo, np.zeros(P)])

    filas, lo, hi = [], [], []
    # (1) presupuesto
    filas.append(np.concatenate([costo, np.zeros(P)])); lo.append(-np.inf); hi.append(presupuesto_neto)
    for pid, j in idx_prod.items():
        sel = (lotes["id"] == pid).to_numpy().astype(float)
        e = np.zeros(P); e[j] = 1.0
        # (3) Σ x ≤ U y      (4) y ≤ Σ x
        filas.append(np.concatenate([sel, -U[j] * e])); lo.append(-np.inf); hi.append(0)
        filas.append(np.concatenate([-sel, e])); lo.append(-np.inf); hi.append(0)
    if cobertura:  # (5)
        for cat in config.CATEGORIAS_BASICAS:
            filas.append(np.concatenate([np.zeros(L), (cat_prod == cat).astype(float)]))
            lo.append(1); hi.append(np.inf)
    # (6) variedad
    filas.append(np.concatenate([np.zeros(L), np.ones(P)])); lo.append(min_variedad); hi.append(np.inf)

    lb = np.zeros(L + P)
    ub = np.concatenate([lotes["cap"].to_numpy(dtype=float), np.ones(P)])
    for key, q in (fijos or {}).items():  # sustitución: se mantienen las demás cantidades
        pos = np.flatnonzero(lotes["key"].to_numpy() == key)
        if pos.size:
            lb[pos[0]] = min(q, ub[pos[0]])

    res = milp(c, constraints=LinearConstraint(np.vstack(filas), lo, hi),
               integrality=np.ones(L + P), bounds=Bounds(lb, ub),
               options={"time_limit": config.TIEMPO_LIMITE_SOLVER})
    if res.x is None:
        return None
    return np.round(res.x[:L]).astype(int)


# ----------------------------------------------------------------------------
# Resultado
# ----------------------------------------------------------------------------
@dataclass
class Canasta:
    items: pd.DataFrame
    perfil: PerfilHogar
    etapa: Etapa
    costo_fijo: int
    costo_logistico: int
    subtotal_productos: int

    @property
    def total(self) -> int:
        return self.subtotal_productos + self.costo_logistico

    @property
    def sobrante(self) -> int:
        return self.perfil.presupuesto - self.total

    @property
    def productos(self) -> list[str]:
        return list(dict.fromkeys(self.items["producto_id"]))

    def comparativo(self) -> dict[str, int]:
        d1 = int((self.items["ref_d1"] * self.items["cantidad"]).sum())
        rappi = int((self.items["ref_rappi"] * self.items["cantidad"]).sum()) + config.RAPPI_DOMICILIO
        return {"sustento": self.total, "d1": d1, "rappi": rappi,
                "ahorro_d1": d1 - self.total, "ahorro_rappi": rappi - self.total}

    def desglose(self) -> dict[str, int]:
        agricultor = int(round(self.subtotal_productos * config.PARTICIPACION_AGRICULTOR))
        return {"agricultor": agricultor, "plataforma": self.subtotal_productos - agricultor,
                "logistica": self.costo_logistico}

    def impacto(self) -> dict[str, float]:
        it = self.items
        extra = it[it["tipo"] == "cosecha_extra"]
        return {"productores": int(it["productor_id"].nunique()),
                "kg_total": float((it["kg_unidad"] * it["cantidad"]).sum()),
                "kg_rescatados": float((extra["kg_unidad"] * extra["cantidad"]).sum())}


def _armar(lotes: pd.DataFrame, x: np.ndarray, perfil: PerfilHogar, etapa: Etapa,
           costo_fijo: int) -> Canasta:
    it = lotes.assign(cantidad=x)
    it = it[it["cantidad"] > 0].copy()
    it["subtotal"] = it["precio"] * it["cantidad"]
    it["orden"] = it["categoria"].map({c: k for k, c in enumerate(ORDEN_CATEGORIAS)}).fillna(99)
    it = it.sort_values(["orden", "nombre", "tipo"]).rename(columns={"id": "producto_id"})
    cols = ["key", "producto_id", "nombre", "emoji", "categoria", "unidad", "kg_unidad", "tipo",
            "cantidad", "precio", "p", "alpha", "subtotal", "costo_var", "motivo_excedente",
            "ref_d1", "ref_rappi", "productor_id"] + [c for c in it.columns if c.startswith("prod_")]
    it = it[cols].reset_index(drop=True)
    costo_log = costo_fijo + int((it["costo_var"] * it["cantidad"]).sum())
    return Canasta(items=it, perfil=perfil, etapa=etapa, costo_fijo=costo_fijo,
                   costo_logistico=costo_log, subtotal_productos=int(it["subtotal"].sum()))


def presupuesto_minimo(perfil: PerfilHogar, fuentes: Fuentes) -> int | None:
    """Costo de la canasta básica más barata (1 unidad por grupo básico), redondeado a $1.000."""
    costo_fijo, costo_kg = fuentes.costo_logistico(perfil.localidad)
    etapa = ETAPAS_POR_NOMBRE["fallback_amplio"]
    lotes = construir_lotes(tabla_maestra(fuentes), perfil, etapa, costo_kg)
    if lotes.empty:
        return None
    total = costo_fijo
    for cat in config.CATEGORIAS_BASICAS:
        sub = lotes[lotes["categoria"] == cat]
        if sub.empty:
            return None
        total += int((sub["precio"] + sub["costo_var"]).min())
    return int(math.ceil(total / 1000) * 1000)


def optimizar_canasta(perfil: PerfilHogar, fuentes: Fuentes) -> Canasta:
    perfil.validar()
    costo_fijo, costo_kg = fuentes.costo_logistico(perfil.localidad)
    maestra = tabla_maestra(fuentes)
    neto = perfil.presupuesto - costo_fijo
    if neto > 0:
        for etapa in ETAPAS:
            lotes = construir_lotes(maestra, perfil, etapa, costo_kg)
            if lotes.empty:
                continue
            x = _resolver(lotes, neto, etapa.min_variedad, etapa.cobertura)
            if x is not None and x.sum() > 0:
                return _armar(lotes, x, perfil, etapa, costo_fijo)
    minimo = presupuesto_minimo(perfil, fuentes)
    msg = f"Con ${perfil.presupuesto:,.0f} no alcanza ni para el domicilio y un producto básico."
    if minimo:
        msg += f" La canasta básica más económica hoy cuesta desde ${minimo:,.0f}."
    raise PresupuestoInsuficiente(msg.replace(",", "."), minimo)


def sustituir_producto(canasta: Canasta, producto_id: str, fuentes: Fuentes) -> tuple[Canasta, list[str]]:
    """'Cambiar producto': saca `producto_id`, mantiene el resto y busca un reemplazo.

    Devuelve (nueva canasta, ids de productos que entraron).
    """
    perfil = replace(canasta.perfil,
                     excluidos=tuple(sorted(set(canasta.perfil.excluidos) | {producto_id})))
    costo_fijo, costo_kg = fuentes.costo_logistico(perfil.localidad)
    etapa = canasta.etapa
    lotes = construir_lotes(tabla_maestra(fuentes), perfil, etapa, costo_kg)
    previos = canasta.items[canasta.items["producto_id"] != producto_id]
    fijos = dict(zip(previos["key"], previos["cantidad"]))
    n_objetivo = max(etapa.min_variedad, len(canasta.productos))

    nueva = None
    if not lotes.empty:
        neto = perfil.presupuesto - costo_fijo
        for fj, nv in ((fijos, n_objetivo), (None, n_objetivo), (None, etapa.min_variedad)):
            x = _resolver(lotes, neto, nv, etapa.cobertura, fj)
            if x is not None and x.sum() > 0:
                nueva = _armar(lotes, x, perfil, etapa, costo_fijo)
                break
    if nueva is None:
        nueva = optimizar_canasta(perfil, fuentes)
    entrantes = [p for p in nueva.productos if p not in canasta.productos]
    return nueva, entrantes
