# Copyright (c) 2026, mohammedlutf and contributors
# For license information, please see license.txt
"""First-run setup executed on a freshly provisioned tenant site.

The central site calls :func:`setup_tenant_site` with ``bench execute`` after
the tenant database has been cloned from the template.  Everything here is
self-contained so the tenant only needs the lightweight ``saas_client`` app.
"""

from __future__ import annotations

import frappe
from frappe import _

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
	"""Configure a freshly cloned tenant site."""
	company_name = (company_name or tenant_name or "").strip()
	language = language if language in ("en", "ar") else "en"
	currency = (currency or "USD").upper()

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

	# Currency --------------------------------------------------------------
	if frappe.db.exists("Currency", currency):
		if not frappe.db.get_value("Currency", currency, "enabled"):
			frappe.db.set_value("Currency", currency, "enabled", 1)
		_set_single("Global Defaults", "default_currency", currency)

	# Company ---------------------------------------------------------------
	company = frappe.db.get_value("Company", {}, "name", order_by="creation asc")
	if not company:
		company = _create_company(company_name or tenant_name, currency, country, tenant_name)
	if company:
		_ensure_transit_warehouse(company)
		updates = {"company_name": company_name or company}
		if frappe.db.exists("Currency", currency):
			updates["default_currency"] = currency
		if country and frappe.db.exists("Country", country):
			updates["country"] = country
		try:
			frappe.db.set_value("Company", company, updates, update_modified=False)
		except Exception:
			frappe.log_error(frappe.get_traceback(), "SaaS client company update")
		_set_single("Global Defaults", "default_company", company)

		# SaaS custom fields on Company (present only when the template has them).
		for fieldname, value in (("saas_tenant", tenant_name), ("saas_plan", plan)):
			try:
				frappe.db.set_value("Company", company, fieldname, value, update_modified=False)
			except Exception:
				pass

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
	return {"ok": True, "site": frappe.local.site, "company": company}


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
# Company / warehouse helpers
# ---------------------------------------------------------------------------
def _ensure_warehouse_type() -> None:
	"""Make sure the Transit warehouse type exists (needed by Company)."""
	if frappe.db.exists("Warehouse Type", "Transit"):
		return
	try:
		frappe.get_doc(
			{
				"doctype": "Warehouse Type",
				"__newname": "Transit",
				"description": "Goods in transit",
			}
		).insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "SaaS client warehouse type")


def _ensure_transit_warehouse(company: str) -> None:
	"""Create the standard 'Goods In Transit' warehouse when it is missing."""
	if frappe.db.exists("Warehouse", {"company": company, "warehouse_type": "Transit"}):
		return
	_ensure_warehouse_type()
	parent = frappe.db.get_value(
		"Warehouse", {"company": company, "is_group": 1}, "name", order_by="lft asc"
	)
	try:
		warehouse = frappe.get_doc(
			{
				"doctype": "Warehouse",
				"warehouse_name": _("Goods In Transit"),
				"company": company,
				"warehouse_type": "Transit",
				"parent_warehouse": parent,
			}
		)
		warehouse.flags.ignore_permissions = True
		warehouse.flags.ignore_mandatory = True
		warehouse.insert(ignore_permissions=True)
		frappe.db.commit()
	except Exception:
		frappe.log_error(frappe.get_traceback(), "SaaS client transit warehouse")


def _create_company(
	company_name: str,
	currency: str,
	country: str | None = None,
	tenant_name: str | None = None,
) -> str | None:
	"""Create the first company with a standard chart of accounts."""
	company_name = (company_name or tenant_name or "Company").strip() or "Company"

	resolved_country = None
	if country and frappe.db.exists("Country", country):
		resolved_country = country
	if not resolved_country:
		for candidate in ("Saudi Arabia", "United Arab Emirates", "Yemen", "United States"):
			if frappe.db.exists("Country", candidate):
				resolved_country = candidate
				break
	if not resolved_country:
		resolved_country = frappe.db.get_value("Country", {}, "name")

	ascii_part = "".join(
		ch for ch in (tenant_name or company_name) if ch.isascii() and ch.isalnum()
	)
	abbr = (ascii_part[:5] or "CO").upper()

	# A fresh ERPNext install has no Warehouse Type records, but company
	# creation always creates a "Transit" warehouse.
	_ensure_warehouse_type()

	try:
		company = frappe.get_doc(
			{
				"doctype": "Company",
				"company_name": company_name,
				"abbr": abbr,
				"default_currency": currency,
				"country": resolved_country,
				"chart_of_accounts": "Standard",
				"create_chart_of_accounts_based_on": "Standard Template",
			}
		)
		company.flags.ignore_permissions = True
		company.insert(ignore_permissions=True)
		frappe.db.commit()
		return company.name
	except Exception:
		frappe.log_error(frappe.get_traceback(), "SaaS client company creation")
		return None


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

	for role in ("System Manager", "Accounts Manager", "Sales Manager", "Purchase Manager", "Stock Manager"):
		if frappe.db.exists("Role", role):
			user.add_roles(role)

	# Administrator keeps its own per-tenant password (set by `bench new-site
	# --admin-password` and `bench set-admin-password`).  Keep it enabled so
	# support can always recover a workspace; customers use their own user.
	try:
		frappe.db.set_value("User", "Administrator", "enabled", 1, update_modified=False)
	except Exception:
		pass
