# Copyright (c) 2026, mohammedlutf and contributors
# For license information, please see license.txt
"""Request guard for tenant sites: suspension and desk-only routes."""

from __future__ import annotations

import frappe
from frappe.utils import cint
from werkzeug.exceptions import HTTPException
from werkzeug.utils import redirect

from saas_client.utils import get_central_url, is_tenant_site

ALLOWED_PREFIXES = (
	"/app",
	"/assets",
	"/api",
	"/files",
	"/private",
	"/login",
	"/logout",
	"/update-password",
	"/reset-password",
	"/favicon",
	"/robots.txt",
	"/website_script",
	"/desk",
	"/.well-known",
)


def before_request() -> None:
	if not is_tenant_site():
		return

	request = getattr(frappe.local, "request", None)
	if not request:
		return

	path = (request.path or "/").split("?")[0]

	# Suspended tenants are sent to the central site.
	if cint(frappe.conf.get("saas_suspended")):
		if not path.startswith("/assets") and not path.startswith("/api"):
			central = get_central_url()
			if central:
				response = redirect(
					f"{central}/suspended?site={frappe.conf.get('saas_subdomain') or ''}"
				)
				raise HTTPException(response=response)

	# Tenant sites are ERP workspaces, not marketing websites.
	if path in ("", "/", "/index"):
		raise HTTPException(response=redirect("/app"))

	if any(path == prefix or path.startswith(prefix + "/") for prefix in ALLOWED_PREFIXES):
		return

	if path.startswith("/api/method/") or path.startswith("/api/resource/"):
		return

	frappe.local.flags.redirect_location = "/app"
	raise frappe.Redirect
