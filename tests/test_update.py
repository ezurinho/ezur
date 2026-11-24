"""La comprobación de versión: compara, no instala."""

from __future__ import annotations

import pytest

from server import update


def test_parse_version_acepta_prefijo_y_sufijo():
    assert update.parse_version("v0.2.0") == (0, 2, 0)
    assert update.parse_version("1.10.3-rc1") == (1, 10, 3)


def test_parse_version_rechaza_lo_que_no_es_version():
    with pytest.raises(ValueError):
        update.parse_version("sin número")
    with pytest.raises(ValueError):
        update.parse_version("")


def test_is_newer_compara_números_y_no_texto():
    # El bug clásico: "0.10.0" < "0.9.0" si se compara como cadena.
    assert update.is_newer("0.10.0", "0.9.0") is True
    assert update.is_newer("0.9.0", "0.10.0") is False
    assert update.is_newer("0.1.0", "0.1.0") is False


def test_is_newer_no_revienta_con_basura():
    assert update.is_newer("", "0.1.0") is False
    assert update.is_newer("v", "0.1.0") is False


def test_manifest_entiende_release_de_github_y_manifiesto_propio():
    github = update._manifest(
        {"tag_name": "v0.3.0", "html_url": "https://x/y", "body": "notas"}
    )
    assert github == {"version": "0.3.0", "url": "https://x/y", "notes": "notas"}

    propio = update._manifest(
        {"version": "0.4.1", "url": "https://x/setup.exe", "notes": "arreglos"}
    )
    assert propio == {"version": "0.4.1", "url": "https://x/setup.exe", "notes": "arreglos"}


def test_check_marca_disponible_solo_si_es_más_nueva():
    payload = {"tag_name": "v0.2.0", "html_url": "https://x/release"}
    result = update.check("u", "0.1.0", fetch=lambda url, timeout: payload)
    assert result["available"] is True
    assert result["latest"] == "0.2.0"
    assert result["url"] == "https://x/release"
    assert result["error"] is None

    igual = update.check("u", "0.2.0", fetch=lambda url, timeout: payload)
    assert igual["available"] is False


def test_check_sin_red_devuelve_error_y_no_lanza():
    def boom(url, timeout):
        raise OSError("sin ruta al host")

    result = update.check("u", "0.1.0", fetch=boom)
    assert result["available"] is False
    assert result["latest"] is None
    assert "sin ruta al host" in result["error"]


def test_check_con_manifiesto_sin_versión_es_error_no_una_actualización():
    result = update.check("u", "0.1.0", fetch=lambda url, timeout: {"url": "https://x"})
    assert result["available"] is False
    assert result["error"] is not None


def test_check_cached_no_repite_la_llamada_dentro_del_ttl():
    calls = []

    def fake(url, timeout):
        calls.append(url)
        return {"tag_name": "v0.2.0"}

    update.reset_cache()
    first = update.check_cached("u", "0.1.0", clock=lambda: 1000.0, fetch=fake)
    second = update.check_cached("u", "0.1.0", clock=lambda: 1010.0, fetch=fake)
    assert first is second
    assert len(calls) == 1

    third = update.check_cached("u", "0.1.0", clock=lambda: 1000.0 + 7 * 3600, fetch=fake)
    assert third["available"] is True
    assert len(calls) == 2


def test_check_cached_cachea_los_fallos_poco_tiempo():
    calls = []

    def boom(url, timeout):
        calls.append(url)
        raise OSError("caído")

    update.reset_cache()
    update.check_cached("u", "0.1.0", clock=lambda: 1000.0, fetch=boom)
    update.check_cached("u", "0.1.0", clock=lambda: 1005.0, fetch=boom)
    assert len(calls) == 1  # dentro de los dos minutos de error

    update.check_cached("u", "0.1.0", clock=lambda: 1000.0 + 300, fetch=boom)
    assert len(calls) == 2  # pasado ese margen se vuelve a intentar


def test_manifest_acepta_una_lista_y_coge_el_primero():
    lista = [
        {"tag_name": "v0.5.0", "html_url": "https://x/5"},
        {"tag_name": "v0.4.0", "html_url": "https://x/4"},
    ]
    assert update._manifest(lista)["version"] == "0.5.0"
    assert update._manifest([])["version"] == ""


def test_sin_canal_no_se_sale_a_la_red():
    def nunca(url, timeout):  # pragma: no cover - si se llama, el test falla
        raise AssertionError("no debe tocar la red sin canal configurado")

    status = update.current_status("", "0.1.0", fetch=nunca)
    assert status["available"] is False
    assert status["error"] == update.UNCONFIGURED
    assert status["current"] == "0.1.0"
