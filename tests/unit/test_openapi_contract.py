"""OpenAPI contract for the list endpoints (ARCH-07, ARCH-08, W3-08).

``app.openapi()`` must build, and every paged list endpoint must document
its response model (the ``Page[...]`` envelope, alongside the deprecated
legacy shape) and the ``offset``/``limit`` query parameters.
"""

from fastapi.routing import APIRoute

PAGED_LIST_PATHS = [
    "/api/v1/orders/",
    "/api/v1/repairs/",
    "/api/v1/quotes/",
    "/api/v1/materials/",
    "/api/v1/time-tracking/user/{user_id}",
    "/api/v1/time-tracking/order/{order_id}",
    "/api/v1/notifications/",
]


def test_openapi_renders_and_documents_paged_lists():
    from goldsmith_erp.main import app

    app.openapi_schema = None
    schema = app.openapi()
    assert "Page_OrderListRead_" in schema["components"]["schemas"]
    for path in PAGED_LIST_PATHS:
        operation = schema["paths"][path]["get"]
        ok = operation["responses"]["200"]["content"]["application/json"]["schema"]
        refs = str(ok)
        assert "Page_" in refs, (path, ok)
        params = {p["name"] for p in operation["parameters"]}
        assert {"offset", "limit"} <= params, (path, params)


def test_every_get_route_in_paged_routers_declares_a_response_model():
    from goldsmith_erp.main import app

    missing = [
        route.path
        for route in app.routes
        if isinstance(route, APIRoute)
        and route.path in PAGED_LIST_PATHS
        and route.response_model is None
    ]
    assert missing == []
