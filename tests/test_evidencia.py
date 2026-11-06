from backend import evidencia


def test_registra_y_lee_eventos(tmp_path):
    evidencia.registrar_evento("s1", "canasta_generada", directorio=tmp_path, total=48_000)
    evidencia.registrar_evento("s1", "pedido_confirmado", directorio=tmp_path, total=48_000)
    ev = evidencia.leer("eventos", tmp_path)
    assert list(ev["evento"]) == ["canasta_generada", "pedido_confirmado"]


def test_guarda_pedido(tmp_path):
    evidencia.guardar_pedido({"pedido_id": "SU-1", "total": 50_000, "objecion": "el domicilio"}, tmp_path)
    ped = evidencia.leer("pedidos", tmp_path)
    assert ped.loc[0, "pedido_id"] == "SU-1" and ped.loc[0, "objecion"] == "el domicilio"


def test_leer_sin_archivo(tmp_path):
    assert evidencia.leer("eventos", tmp_path).empty
