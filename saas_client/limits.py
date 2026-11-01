# Copyright (c) 2026, mohammedlutf and contributors
# For license information, please see license.txt
"""Plan limit enforcement for tenant sites.

The central site writes the limits of the tenant's current plan into the
tenant's ``site_config.json`` (``saas_max_users``, ``saas_max_branches``,
``saas_max_companies`` and ``saas_storage_gb``).  A value of ``0`` means
unlimited.  These hooks run inside the tenant site so a customer cannot create
more users, branches or companies than the plan allows.
"""

from __future__ import annotations

import os

import frappe
from frappe import _
from frappe.utils import cint

from saas_client.utils import get_local_limits, is_tenant_site


# ---------------------------------------------------------------------------
# Counting helpers
# ---------------------------------------------------------------------------
def _is_system_user(user_type: str | None) -> bool:
	return (user_type or "System User") != "Website User"


def _count_system_users() -> int:
	"""Count enabled desk users, excluding the built-in accounts."""
	rows = frappe.db.sql(
		"""
		select count(*) from `tabUser`
		where enabled = 1
			and name not in ('Administrator', 'Guest')
			and ifnull(user_type, 'System User') != 'Website User'
		"""
	)
	return cint(rows[0][0]) if rows else 0


def _would_use_user_slot(doc) -> bool:
	"""True when saving this User increases the number of active desk users."""
	if not cint(doc.enabled) or not _is_system_user(doc.user_type):
		return False
	if doc.is_new():
		return True

	before = frappe.db.get_value("User", doc.name, ["enabled", "user_type"], as_dict=True)
	if not before:
		return True

	was_active = cint(before.enabled) and _is_system_user(before.user_type)
	return not was_active


def _site_storage_mb() -> float:
	"""Size of the tenant's uploaded files in megabytes."""
	total = 0
	for relative in (("public", "files"), ("private", "files")):
		path = frappe.get_site_path(*relative)
		if not os.path.isdir(path):
			continue
		for root, _dirs, files in os.walk(path):
			for name in files:
				try:
					total += os.path.getsize(os.path.join(root, name))
				except OSError:
					pass
	return round(total / (1024 * 1024), 2)


# ---------------------------------------------------------------------------
# Document events
# ---------------------------------------------------------------------------
def check_user_limit(doc, method=None) -> None:
	if not is_tenant_site():
		return
	if not _would_use_user_slot(doc):
		return

	limit = get_local_limits()["max_users"]
	if not limit:
		return

	if _count_system_users() >= limit:
		frappe.throw(
			_(
				"Your plan allows a maximum of {0} users. Please upgrade your plan to add more users."
			).format(limit),
			title=_("User limit reached"),
		)


def check_branch_limit(doc, method=None) -> None:
	if not is_tenant_site():
		return

	limit = get_local_limits()["max_branches"]
	if not limit:
		return

	if doc.is_new() and frappe.db.count("Branch") >= limit:
		frappe.throw(
			_(
				"Your plan allows a maximum of {0} branches. Please upgrade your plan to add more branches."
			).format(limit),
			title=_("Branch limit reached"),
		)


def check_company_limit(doc, method=None) -> None:
	if not is_tenant_site():
		return

	limit = get_local_limits()["max_companies"]
	if not limit:
		return

	if doc.is_new() and frappe.db.count("Company") >= limit:
		frappe.throw(
			_(
				"Your plan allows a maximum of {0} companies. Please upgrade your plan to add more companies."
			).format(limit),
			title=_("Company limit reached"),
		)


def check_storage_limit(doc, method=None) -> None:
	if not is_tenant_site():
		return

	limit_gb = get_local_limits()["storage_gb"]
	if not limit_gb:
		return

	if _site_storage_mb() >= limit_gb * 1024:
		frappe.throw(
			_(
				"Your workspace storage is full ({0} GB). Please upgrade your plan or remove old files."
			).format(limit_gb),
			title=_("Storage limit reached"),
		)
