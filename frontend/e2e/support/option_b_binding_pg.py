"""Test-only deterministic directory change between two REAL HTTP responses.

Reuse the real S4 PostgreSQL/app/session/grants. Never synthesize an API payload
or expose this wrapper through production. The trusted test configuration changes
only after scope has passed its real response gate, before the next list request.
"""

from pydantic import SecretStr

from frontend.e2e.support import business_pg

armed = False


@business_pg.outer.post("/__option_b_test__/change-directory-after-scope")
async def change_directory_after_scope():
    global armed
    armed = True
    return {"SYNTHETIC": True, "armed": True}


async def app(scope, receive, send):
    async def observed_send(message):
        global armed
        if (
            armed
            and scope.get("path") == "/api/v1/business-access/scope"
            and message["type"] == "http.response.body"
        ):
            armed = False
            settings = business_pg.outer.state.auth.settings
            # Same valid JSON policy; distinct trusted-directory revision digest.
            # No account/grant or forecast write, and no altered response bytes.
            value = settings.local_auth_publisher_boundaries_json.get_secret_value()
            settings.local_auth_publisher_boundaries_json = SecretStr(value + "\n")
        await send(message)

    await business_pg.app(scope, receive, observed_send)
