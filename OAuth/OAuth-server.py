from flask import Flask, jsonify, request
import time
import secrets

app = Flask(__name__)

# 你本地联调时允许的 client_id / client_secret
VALID_CLIENTS = {
    "your-client-id": {
        "client_secret": "your-client-secret",
        "allowed_scopes": {"mcp:read", "mcp:write"},
    },
    "test-client": {
        "client_secret": "test-secret",
        "allowed_scopes": {"mcp:read"},
    },
}

# 简单内存 token 存储，便于调试 / introspect
ISSUED_TOKENS = {}


def build_token_response(access_token: str, expires_in: int, scope: str):
    return {
        "access_token": access_token,
        "token_type": "Bearer",
        "expires_in": expires_in,
        "scope": scope,
    }


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"})


@app.route("/oauth/token", methods=["POST"])
def oauth_token():
    """
    模拟 OAuth 2.0 token endpoint
    支持:
      - grant_type=client_credentials
      - client_id
      - client_secret
      - scope (可选)
    """

    content_type = request.headers.get("Content-Type", "")

    if "application/x-www-form-urlencoded" in content_type:
        data = request.form.to_dict(flat=True)
    else:
        # 兼容 JSON 传参，方便本地调试
        data = request.get_json(silent=True) or {}

    grant_type = data.get("grant_type", "")
    client_id = data.get("client_id", "")
    client_secret = data.get("client_secret", "")
    requested_scope = data.get("scope", "").strip()

    print("---- /oauth/token ----")
    print("Headers:", dict(request.headers))
    print("Body:", data)

    if grant_type != "client_credentials":
        return jsonify({
            "error": "unsupported_grant_type",
            "error_description": "Only client_credentials is supported by this mock server."
        }), 400

    client_info = VALID_CLIENTS.get(client_id)
    if not client_info:
        return jsonify({
            "error": "invalid_client",
            "error_description": "Unknown client_id."
        }), 401

    if client_secret != client_info["client_secret"]:
        return jsonify({
            "error": "invalid_client",
            "error_description": "Invalid client_secret."
        }), 401

    allowed_scopes = client_info["allowed_scopes"]

    if requested_scope:
        requested_scopes = set(requested_scope.split())
        if not requested_scopes.issubset(allowed_scopes):
            return jsonify({
                "error": "invalid_scope",
                "error_description": f"Requested scope not allowed. Allowed scopes: {' '.join(sorted(allowed_scopes))}"
            }), 400
        granted_scope = " ".join(sorted(requested_scopes))
    else:
        # 没传 scope 时，给一个默认 scope
        granted_scope = " ".join(sorted(allowed_scopes))

    expires_in = 3600
    access_token = f"mock-token-{secrets.token_urlsafe(24)}"
    expires_at = int(time.time()) + expires_in

    ISSUED_TOKENS[access_token] = {
        "client_id": client_id,
        "scope": granted_scope,
        "expires_at": expires_at,
        "active": True,
    }

    return jsonify(build_token_response(
        access_token=access_token,
        expires_in=expires_in,
        scope=granted_scope,
    ))


@app.route("/oauth/introspect", methods=["POST"])
def introspect():
    """
    可选的 token introspection endpoint
    """
    content_type = request.headers.get("Content-Type", "")

    if "application/x-www-form-urlencoded" in content_type:
        data = request.form.to_dict(flat=True)
    else:
        data = request.get_json(silent=True) or {}

    token = data.get("token", "")
    token_info = ISSUED_TOKENS.get(token)

    now = int(time.time())

    if not token_info or not token_info["active"] or token_info["expires_at"] <= now:
        return jsonify({"active": False})

    return jsonify({
        "active": True,
        "client_id": token_info["client_id"],
        "scope": token_info["scope"],
        "token_type": "Bearer",
        "exp": token_info["expires_at"],
    })


@app.route("/protected-resource", methods=["GET"])
def protected_resource():
    """
    一个简单的受保护资源，便于本地测试 Bearer Token
    """
    auth = request.headers.get("Authorization", "")
    if not auth.startswith("Bearer "):
        return jsonify({"error": "missing_bearer_token"}), 401

    token = auth.removeprefix("Bearer ").strip()
    token_info = ISSUED_TOKENS.get(token)

    now = int(time.time())
    if not token_info or not token_info["active"] or token_info["expires_at"] <= now:
        return jsonify({"error": "invalid_or_expired_token"}), 401

    return jsonify({
        "message": "authorized",
        "client_id": token_info["client_id"],
        "scope": token_info["scope"],
    })


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
