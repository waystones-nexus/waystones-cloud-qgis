import pytest


@pytest.fixture(scope="session")
def qgis_app():
    """Bootstrap a headless QgsApplication for the test session.

    pytest-qgis provides this fixture automatically; this stub is here so
    tests that explicitly request it also work when the plugin is the
    provider (belt-and-suspenders).
    """
    from qgis.core import QgsApplication
    app = QgsApplication([], False)
    app.initQgis()
    yield app
    app.exitQgis()
