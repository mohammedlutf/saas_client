# Copyright (c) 2026, mohammedlutf and contributors
# For license information, please see license.txt
"""Helpers shared by the tenant-side SaaS client app."""

from __future__ import annotations

import json
import os

import frappe
from frappe.utils import cint


def is_tenant_site() -> bool:
	"""Return True when this site was provisioned by the SaaS platform."""
	return bool(frappe.conf.get("saas_tenant"))


def get_local_limits() -> dict:
	"""Read the limits pushed by the central site into site_config.json."""
	return {
		"max_users": cint(frappe.conf.get("saas_max_users")),
		"max_branches": cint(frappe.conf.get("saas_max_branches")),
		"max_companies": cint(frappe.conf.get("saas_max_companies")),
		"storage_gb": cint(frappe.conf.get("saas_storage_gb")),
		"suspended": cint(frappe.conf.get("saas_suspended")),
		"plan": frappe.conf.get("saas_plan"),
	}


def get_central_url() -> str:
	return (frappe.conf.get("saas_central_url") or "").rstrip("/")


def _site_config_path(site: str | None = None) -> str:
	site = site or frappe.local.site
	if site == frappe.local.site:
		return frappe.get_site_path("site_config.json")
	return os.path.join(frappe.utils.get_bench_path(), "sites", site, "site_config.json")


def read_site_config(site: str | None = None) -> dict:
	try:
		with open(_site_config_path(site)) as fh:
			return json.load(fh)
	except Exception:
		return {}


def update_site_config(updates: dict, remove_keys=None, site: str | None = None) -> dict:
	"""Persist values to site_config.json and keep the in-memory config in sync."""
	path = _site_config_path(site)
	config = read_site_config(site)

	clean = {key: value for key, value in (updates or {}).items() if value is not None}
	config.update(clean)
	for key in remove_keys or ():
		config.pop(key, None)

	tmp = path + ".tmp"
	with open(tmp, "w") as fh:
		json.dump(config, fh, indent=1, sort_keys=True)
		fh.write("\n")
	os.replace(tmp, path)

	if site is None or site == frappe.local.site:
		frappe.conf.update(clean)
		for key in remove_keys or ():
			frappe.conf.pop(key, None)

	return config
