# Copyright (c) 2026, mohammedlutf and contributors
# For license information, please see license.txt
"""First-run setup executed on a freshly provisioned tenant site.

The central site calls :func:`setup_tenant_site` with ``bench execute`` after
the tenant database has been cloned from the template.  Everything here is
self-contained so the tenant only needs the lightweight ``saas_client`` app.

Company and currency are intentionally left alone: the tenant finishes the
ERPNext setup wizard on first login, where the company, chart of accounts and
default currency are chosen.
"""

from __future__ import annotations

import frappe

from saas_client.utils import update_site_config


def setup_tenant_site(
	tenant_name: str,
	company_name: str | None = None,
	admin_email: str | None = None,
	admin_full_name: str | None = None,
	currency: str | None = None,
	language: str = "en",
	country: str | None = None,
	admin_password: str | None = None,
	plan: str | None = None,
):
	"""Configure a freshly cloned tenant site.

	``company_name`` is used only as the display/branding name; the company
	itself is created by the tenant through the ERPNext setup wizard.
	``currency`` is accepted for backwards compatibility with the caller and
	is not applied here.
	"""
	company_name = (company_name or tenant_name or "").strip()
	language = language if language in ("en", "ar") else "en"

	# System settings -------------------------------------------------------
	_set_single("System Settings", "language", language)
	if country and frappe.db.exists("Country", country):
		_set_single("System Settings", "country", country)
		_set_single("Global Defaults", "country", country)
	_set_single("System Settings", "app_name", company_name)
	_set_single("System Settings", "allow_login_using_user_name", 1)
	_set_single("System Settings", "disable_signup", 1)

	# Website settings ------------------------------------------------------
	_set_single("Website Settings", "app_name", company_name)
	_set_single("Website Settings", "disable_signup", 1)
	_set_single("Website Settings", "hide_footer", 1)

	# Administrator ---------------------------------------------------------
	if admin_email:
		_setup_admin_user(admin_email, admin_full_name or company_name, admin_password, language)

	# Mark this site as a tenant in its own config -------------------------
	update_site_config(
		{
			"saas_tenant": tenant_name,
			"saas_tenant_name": company_name,
			"saas_plan": plan,
			"saas_suspended": 0,
		}
	)

	frappe.db.commit()
	frappe.clear_cache()
	return {"ok": True, "site": frappe.local.site}


def rename_company(company_name: str) -> dict:
	"""Rename the tenant's first company (executed on the tenant site)."""
	company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
	if not company:
		return {"ok": False}
	frappe.db.set_value("Company", company, "company_name", company_name, update_modified=False)
	frappe.db.set_value("System Settings", "System Settings", "app_name", company_name, update_modified=False)
	frappe.db.set_value("Website Settings", "Website Settings", "app_name", company_name, update_modified=False)
	frappe.db.commit()
	frappe.clear_cache()
	return {"ok": True, "company": company}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
def _set_single(doctype: str, field: str, value) -> None:
	try:
		frappe.db.set_single_value(doctype, field, value, update_modified=False)
	except Exception:
		pass


def _setup_admin_user(email: str, full_name: str, password: str | None, language: str) -> None:
	email = email.strip().lower()
	if not email:
		return
	parts = (full_name or email).split(" ", 1)
	first_name = parts[0]
	last_name = parts[1] if len(parts) > 1 else ""

	if frappe.db.exists("User", email):
		user = frappe.get_doc("User", email)
	else:
		user = frappe.new_doc("User")
		user.email = email
		user.send_welcome_email = 0

	user.first_name = first_name
	user.last_name = last_name
	user.enabled = 1
	user.user_type = "System User"
	user.language = language
	if password:
		user.new_password = password
	user.flags.ignore_permissions = True
	user.flags.no_welcome_mail = True
	user.save(ignore_permissions=True)
    roles = ["Academics User", "Accounts Manager", "Accounts User", "Agriculture Manager", "Agriculture User", "Auditor", "Blogger", "Customer", "Dashboard Manager", "Delivery Manager", "Delivery User", "Fleet Manager", "Fulfillment User", "HR Manager", "HR User", "Inbox User", "Item Manager", "Knowledge Base Contributor", "Knowledge Base Editor", "Maintenance Manager", "Maintenance User", "Manufacturing Manager", "Manufacturing User", "Newsletter Manager", "Prepared Report User", "Projects Manager", "Projects User", "Purchase Manager", "Purchase Master Manager", "Purchase User", "Quality Manager", "Report Manager", "Sales Manager", "Sales Master Manager", "Sales User", "Script Manager", "Stock Manager", "Stock User", "Supplier", "Support Team", "System Manager", "Translator", "Website Manager", "Workspace Manager"]
	for role in roles:
		if frappe.db.exists("Role", role):
			user.add_roles(role)

	# Administrator keeps its own per-tenant password (set by `bench new-site
	# --admin-password` and `bench set-admin-password`).  Keep it enabled so
	# support can always recover a workspace; customers use their own user.
	try:
		frappe.db.set_value("User", "Administrator", "enabled", 1, update_modified=False)
	except Exception:
		pass
