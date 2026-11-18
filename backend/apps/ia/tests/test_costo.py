"""Costo estimado de una consulta al agente (Serie II, inciso 9)."""

from decimal import Decimal

import pytest

from apps.ia.services import estimar_costo_usd


def test_aplica_el_precio_por_millon_de_cada_tipo_de_token():
    # (1,834 × 0.30 + 212 × 2.50) / 1,000,000 = 0.0010802
    assert estimar_costo_usd(tokens_entrada=1834, tokens_salida=212) == Decimal(
        "0.001080"
    )


def test_sin_consumo_cuesta_cero():
    assert estimar_costo_usd(tokens_entrada=0, tokens_salida=0) == Decimal("0.000000")


@pytest.mark.parametrize("entrada, salida", [(None, 5), (10, None), (None, None)])
def test_con_un_contador_desconocido_el_costo_es_desconocido(entrada, salida):
    assert estimar_costo_usd(tokens_entrada=entrada, tokens_salida=salida) is None


def test_los_precios_salen_de_settings(settings):
    settings.IA_PRECIO_ENTRADA_USD_MILLON = Decimal("1.00")
    settings.IA_PRECIO_SALIDA_USD_MILLON = Decimal("4.00")

    # (1,000,000 × 1.00 + 500,000 × 4.00) / 1,000,000 = 3.00
    assert estimar_costo_usd(
        tokens_entrada=1_000_000, tokens_salida=500_000
    ) == Decimal("3.000000")
