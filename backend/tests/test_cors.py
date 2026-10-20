def preflight(client, origin):
    return client.options("/api/v1/me", headers={"Origin": origin, "Access-Control-Request-Method": "GET",
                                                  "Access-Control-Request-Headers": "authorization"})


def test_cors_allows_only_configured_origins(client):
    assert preflight(client, "https://shofly.example").headers.get("access-control-allow-origin") == "https://shofly.example"
    assert "access-control-allow-origin" not in preflight(client, "https://evil.example").headers
