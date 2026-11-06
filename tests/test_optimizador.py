"""Pruebas del motor MILP de Sustento."""
import numpy as np
import pandas as pd
import pytest

from backend import config
from backend.canal_asistido import mensaje_whatsapp
from backend.etl import cargar_fuentes, simular_boletin_sipsa
from backend.optimizador import (PerfilHogar, PresupuestoInsuficiente, optimizar_canasta,
                                 sustituir_producto)
from backend.precios import alpha_excedente, precio_estetico


@pytest.fixture(scope="module")
def fuentes():
    return cargar_fuentes()


def perfil(B=50_000, **kw):
    base = dict(localidad="Kennedy", adultos=2, ninos=1, mayores=0)
    base.update(kw)
    return PerfilHogar(B, **base)


# --- Restricción presupuestaria de borde ------------------------------------
@pytest.mark.parametrize("B", [12_000, 20_000, 35_000, 50_000, 80_000, 150_000, 300_000])
@pytest.mark.parametrize("localidad", ["Usaquén", "Kennedy", "Usme"])
def test_respeta_presupuesto_incluyendo_domicilio(fuentes, B, localidad):
    c = optimizar_canasta(perfil(B, localidad=localidad), fuentes)
    calculado = int((c.items["precio"] * c.items["cantidad"]).sum()) + c.costo_logistico
    assert calculado == c.total
    assert c.total <= B
    assert c.costo_logistico >= fuentes.costo_logistico(localidad)[0]


@pytest.mark.parametrize("semilla", range(15))
def test_respeta_presupuesto_con_boletines_volatiles(fuentes, semilla):
    f = cargar_fuentes(sipsa=simular_boletin_sipsa(fuentes.productos, semilla))
    for B in (25_000, 50_000, 90_000):
        assert optimizar_canasta(perfil(B), f).total <= B


# --- Variables enteras -------------------------------------------------------
def test_cantidades_enteras_y_positivas(fuentes):
    c = optimizar_canasta(perfil(), fuentes)
    q = c.items["cantidad"].to_numpy()
    assert np.issubdtype(q.dtype, np.integer)
    assert (q >= 1).all()


def test_respeta_oferta_eva_y_consumo_del_hogar(fuentes):
    c = optimizar_canasta(perfil(300_000), fuentes)
    oferta = fuentes.oferta.set_index("producto_id")
    for r in c.items.itertuples():
        limite = oferta.loc[r.producto_id, "excedente_unid" if r.tipo == "cosecha_extra"
                            else "oferta_semanal_unid"]
        assert r.cantidad <= limite
    assert "uchuva" not in c.productos  # EVA: oferta 0 esta semana


# --- Preferencias del onboarding --------------------------------------------
def test_excluye_lo_que_no_comen(fuentes):
    excl = ("brocoli", "habichuela", "papa_pastusa")
    c = optimizar_canasta(perfil(excluidos=excl), fuentes)
    assert not set(excl) & set(c.productos)


def test_respeta_madurez(fuentes):
    c = optimizar_canasta(perfil(150_000, madurez={"tomate": "verde"}), fuentes)
    assert "tomate_maduro" not in c.productos


def test_sin_cosecha_extra_si_el_usuario_no_quiere(fuentes):
    c = optimizar_canasta(perfil(incluir_cosecha_extra=False), fuentes)
    assert (c.items["tipo"] == "regular").all()


def test_canasta_normal_cubre_grupos_basicos(fuentes):
    c = optimizar_canasta(perfil(50_000), fuentes)
    assert c.etapa.nombre == "normal"
    assert set(config.CATEGORIAS_BASICAS) <= set(c.items["categoria"])
    assert len(c.productos) >= config.MIN_VARIEDAD


# --- Heurística de antifragilidad (alpha) -----------------------------------
def test_alpha_sube_con_volatilidad_y_tiene_tope():
    a = alpha_excedente([0.0, config.UMBRAL_VOLATILIDAD, 0.15, 0.9])
    assert a[0] == pytest.approx(config.ALPHA_MIN)
    assert a[1] == pytest.approx(config.ALPHA_MIN)
    assert config.ALPHA_MIN < a[2] < config.ALPHA_MAX
    assert a[3] == pytest.approx(config.ALPHA_MAX)


def test_precio_estetico():
    assert precio_estetico([10_000], [0.25])[0] == 7_500


def test_lotes_cosecha_extra_con_descuento(fuentes):
    c = optimizar_canasta(perfil(80_000), fuentes)
    extra = c.items[c.items["tipo"] == "cosecha_extra"]
    assert not extra.empty
    assert (extra["precio"] < extra["p"]).all()


# --- Fallback y presupuesto insuficiente ------------------------------------
def test_fallback_de_temporada_con_presupuesto_bajo(fuentes):
    c = optimizar_canasta(perfil(12_000), fuentes)
    assert c.etapa.nombre != "normal"
    assert c.etapa.mensaje
    assert c.total <= 12_000


def test_presupuesto_imposible_lanza_error_con_sugerencia(fuentes):
    with pytest.raises(PresupuestoInsuficiente) as e:
        optimizar_canasta(perfil(4_000), fuentes)  # menos que el domicilio
    assert e.value.minimo_sugerido and e.value.minimo_sugerido > 4_000
    # El mínimo sugerido sí debe ser factible
    assert optimizar_canasta(perfil(e.value.minimo_sugerido), fuentes).total <= e.value.minimo_sugerido


@pytest.mark.parametrize("malo", [dict(adultos=0, ninos=0, mayores=0), dict(adultos=-1)])
def test_perfil_invalido(fuentes, malo):
    with pytest.raises(ValueError):
        optimizar_canasta(perfil(**malo), fuentes)


def test_localidad_desconocida(fuentes):
    with pytest.raises(ValueError):
        optimizar_canasta(perfil(localidad="Narnia"), fuentes)


# --- Sustitución inteligente ------------------------------------------------
def test_cambiar_producto(fuentes):
    c = optimizar_canasta(perfil(50_000), fuentes)
    sale = c.productos[0]
    nueva, entran = sustituir_producto(c, sale, fuentes)
    assert sale not in nueva.productos
    assert nueva.total <= 50_000
    assert entran, "debería entrar al menos un producto de reemplazo"
    assert len(nueva.productos) >= len(c.productos)


def test_cambios_sucesivos_no_rompen_presupuesto(fuentes):
    c = optimizar_canasta(perfil(45_000), fuentes)
    for _ in range(5):
        c, _ = sustituir_producto(c, c.productos[0], fuentes)
        assert c.total <= 45_000
        assert np.issubdtype(c.items["cantidad"].to_numpy().dtype, np.integer)


# --- Salidas para el usuario ------------------------------------------------
def test_desglose_y_comparativo_cuadran(fuentes):
    c = optimizar_canasta(perfil(), fuentes)
    d = c.desglose()
    assert d["agricultor"] + d["plataforma"] + d["logistica"] == c.total
    comp = c.comparativo()
    assert comp["ahorro_d1"] == comp["d1"] - c.total


def test_mensaje_whatsapp(fuentes):
    c = optimizar_canasta(perfil(), fuentes)
    texto = mensaje_whatsapp(c)
    assert "TOTAL" in texto and c.perfil.localidad in texto
    assert all(n in texto for n in c.items["nombre"])
