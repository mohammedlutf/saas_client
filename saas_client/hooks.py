app_name = "saas_client"
app_title = "SaaS Client"
app_publisher = "mohammedlutf"
app_description = "Tenant-side plan limits, suspension guard and first-run setup for SaaS-managed ERPNext sites."
app_email = "m.lutfdalal@gmail.com"
app_license = "mit"

# ---------------------------------------------------------------------------
# Tenant request lifecycle
# ---------------------------------------------------------------------------
# This hook is a no-op on the central site and on the template site because
# neither has ``saas_tenant`` in its site_config.json.
before_request = ["saas_client.guard.before_request"]

# ---------------------------------------------------------------------------
# Plan limits enforced inside each tenant site
# ---------------------------------------------------------------------------
doc_events = {
	"User": {
		"validate": "saas_client.limits.check_user_limit",
	},
	"Branch": {
		"validate": "saas_client.limits.check_branch_limit",
	},
	"Company": {
		"validate": "saas_client.limits.check_company_limit",
	},
	"File": {
		"before_insert": "saas_client.limits.check_storage_limit",
	},
}
