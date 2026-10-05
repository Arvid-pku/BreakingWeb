from __future__ import annotations

from starlette.testclient import TestClient

from breakingweb.app import app
from breakingweb.backend.routes.lms import list_variants


def test_lms_variants_endpoint_exists_and_returns_list() -> None:
    client = TestClient(app)

    response = client.get("/api/env/lms/variants")
    assert response.status_code == 200, response.text

    variants = response.json()
    assert isinstance(variants, list)
    assert all(v.get("source") == "yaml" for v in variants)
    assert all(str(v.get("filename", "")).startswith("lms_") for v in variants)

    api_variants = list_variants()
    assert api_variants == variants
