"""
Security regression tests.

These cover defects that were live in the codebase and are cheap to
reintroduce: unescaped output, open redirects, privilege escalation through
self-service edits, and information disclosure on unauthenticated endpoints.
"""

import re
from pathlib import Path

import pytest

PAYLOAD = '<img src=x onerror="alert(1)">'
ESCAPED_MARKERS = ("&lt;img", "&amp;lt;img", "\\u003cimg")


class TestStoredXss:
    """User-supplied text must never reach a page as live markup."""

    def test_part_name_is_escaped_on_the_inventory_page(
        self, admin_client, seeded_settings, factories
    ):
        factories.part(name=PAYLOAD, sku="XSS-1")

        body = admin_client.get("/inventory/").get_data(as_text=True)

        assert 'onerror="alert(1)"' not in body
        assert any(
            marker in body for marker in ESCAPED_MARKERS
        ), "payload should appear escaped, not raw"

    def test_customer_name_is_escaped_on_the_customers_page(
        self, admin_client, seeded_settings, factories
    ):
        factories.customer(name=PAYLOAD)

        body = admin_client.get("/customers/").get_data(as_text=True)
        assert 'onerror="alert(1)"' not in body

    def test_staff_display_name_is_escaped(self, admin_client, seeded_settings, factories):
        """A user can set their own name - it must not become markup."""
        factories.user(username="xss", name=PAYLOAD)

        body = admin_client.get("/staff/").get_data(as_text=True)
        assert 'onerror="alert(1)"' not in body

    def test_supplier_name_is_escaped(self, admin_client, seeded_settings, factories):
        factories.supplier(name=PAYLOAD)

        body = admin_client.get("/suppliers/").get_data(as_text=True)
        assert 'onerror="alert(1)"' not in body


class TestClientSideEscaping:
    """The browser-side renderers must escape too - Jinja cannot help there.

    Several panels build markup with innerHTML from API JSON, so the escaping
    has to happen in JavaScript. These tests assert the helpers exist and that
    no interpolation of a user-controlled field is left unwrapped.
    """

    PROJECT_ROOT = Path(__file__).resolve().parents[2]

    # Fields that carry user-supplied text.
    RISKY_FIELD = (
        r"(name|title|message|email|sku|description|brand|address|phone|notes"
        r"|action_url|action_text|staff_name|customer_name|part_name|contact_person)"
    )

    def _sources(self):
        yield from (self.PROJECT_ROOT / "templates").rglob("*.html")
        yield from (self.PROJECT_ROOT / "static" / "js").rglob("*.js")

    def test_escaping_helpers_are_defined(self):
        api = (self.PROJECT_ROOT / "static" / "js" / "api.js").read_text(encoding="utf-8")
        assert "JRF.escapeHtml" in api
        assert "JRF.safeUrl" in api
        # Templates call the bare names, so the aliases must stay exported.
        assert "window.escapeHtml" in api
        assert "window.safeUrl" in api

        realtime = (self.PROJECT_ROOT / "static" / "js" / "realtime.js").read_text(encoding="utf-8")
        assert "static escapeHtml" in realtime
        assert "static safeUrl" in realtime

    def test_every_page_loads_the_shared_helpers_first(self):
        base = (self.PROJECT_ROOT / "templates" / "base_new.html").read_text(encoding="utf-8")
        assert "js/api.js" in base
        # api.js must load before realtime.js and any page script that uses it.
        assert base.index("js/api.js") < base.index("js/realtime.js")

    def test_no_unescaped_user_data_is_interpolated_into_markup(self):
        # ${something.name} without an escapeHtml()/safeUrl() wrapper.
        pattern = re.compile(
            r"\$\{(?!escapeHtml|safeUrl|this\.)[A-Za-z_][A-Za-z0-9_]*\."
            + self.RISKY_FIELD
            + r"\b(?!\s*\?)"
        )

        # Contexts that cannot inject markup, so raw interpolation is fine:
        #   textContent - assigns text, never parses HTML
        #   JRF.notify  - escapes its own message argument
        safe_contexts = ("textContent", "JRF.notify(")

        offenders = []
        for path in self._sources():
            for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
                if any(context in line for context in safe_contexts):
                    continue
                if pattern.search(line):
                    offenders.append(f"{path.name}:{number}: {line.strip()[:110]}")

        assert not offenders, "unescaped interpolation into markup:\n" + "\n".join(offenders)

    def test_realtime_poller_stops_on_401(self):
        """An expired session must not leave the pollers spinning forever."""
        realtime = (self.PROJECT_ROOT / "static" / "js" / "realtime.js").read_text(encoding="utf-8")
        assert "status === 401" in realtime
        assert "clearAllIntervals" in realtime


class TestOpenRedirect:
    @pytest.mark.parametrize(
        "target",
        [
            "//evil.example.com",
            "https://evil.example.com",
            "http://evil.example.com/path",
            "\\\\evil.example.com",
        ],
    )
    def test_login_refuses_offsite_next(self, client, admin, target):
        response = client.post(
            f"/login?next={target}",
            data={"email": admin.email, "password": "password123"},
        )
        assert response.status_code == 302
        assert "evil.example.com" not in response.headers["Location"]


class TestPrivilegeEscalation:
    def test_staff_cannot_promote_themselves_via_the_api(self, staff_client, staff, db):
        response = staff_client.put(
            f"/api/staff/{staff.id}", json={"role": "admin", "is_active": True}
        )

        assert response.status_code == 200  # the name/contact edit is allowed
        db.session.refresh(staff)
        assert staff.role == "staff"

    def test_staff_cannot_set_their_own_password_without_the_old_one(self, staff_client, staff, db):
        response = staff_client.put(f"/api/staff/{staff.id}", json={"password": "brandnewpassword"})
        assert response.status_code == 403
        db.session.refresh(staff)
        assert staff.check_password("password123")

    def test_last_admin_cannot_be_deleted(self, admin_client, admin, db, factories):
        other = factories.user(username="second", role="admin")
        admin_client.put(f"/api/staff/{other.id}", json={"role": "staff"})

        response = admin_client.delete(f"/api/staff/{admin.id}")
        assert response.status_code == 400


class TestInformationDisclosure:
    def test_health_endpoint_does_not_leak_connection_details(self, client):
        body = client.get("/api/system/health").get_json()

        serialised = str(body)
        assert "postgresql" not in serialised.lower()
        assert "password" not in serialised.lower()
        assert body["database"] in ("connected", "disconnected")

    def test_system_info_hides_credentials(self, admin_client):
        body = admin_client.get("/api/system/info").get_json()
        assert "://" not in body["database"] or "@" not in body["database"]

    def test_error_responses_do_not_include_a_traceback(self, admin_client):
        body = admin_client.get("/api/parts/999999").get_json()
        assert "Traceback" not in str(body)


class TestSecurityHeaders:
    def test_headers_are_present_and_not_duplicated(self, client):
        response = client.get("/health")

        for header in (
            "X-Content-Type-Options",
            "X-Frame-Options",
            "Referrer-Policy",
            "Content-Security-Policy",
        ):
            assert header in response.headers
            assert len(response.headers.get_all(header)) == 1, f"{header} duplicated"

    def test_csp_blocks_framing_and_object_embeds(self, client):
        csp = client.get("/health").headers["Content-Security-Policy"]
        assert "frame-ancestors 'none'" in csp
        assert "object-src 'none'" in csp

    @pytest.mark.parametrize("environment", ["development", "production"])
    def test_csp_allows_every_cdn_the_templates_load(self, environment):
        """A CDN missing from script-src silently breaks that feature.

        Alpine.js (the notification bell and user menu) and Chart.js (report
        graphs) are served from jsdelivr, which was absent from the policy -
        the browser blocked both and the UI just quietly stopped working.
        """
        import re
        from pathlib import Path

        from app.core.config import config

        project_root = Path(__file__).resolve().parents[2]
        templates = (project_root / "templates").rglob("*.html")

        script_hosts = set()
        for path in templates:
            text = path.read_text(encoding="utf-8")
            for match in re.finditer(r'<script[^>]+src="(https://[^"/]+)', text):
                script_hosts.add(match.group(1))

        policy = config[environment].CONTENT_SECURITY_POLICY["script-src"]

        missing = sorted(host for host in script_hosts if host not in policy)
        assert not missing, (
            f"{environment} CSP script-src is missing: {missing}\n" f"current policy: {policy}"
        )
