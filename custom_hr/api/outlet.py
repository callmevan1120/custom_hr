# Copyright (c) 2026, callmevan1120 and contributors
# For license information, please see license.txt

"""Outlet APIs: sync outlets from the Company tree, bulk-provision employees."""

import frappe
from frappe.utils import getdate, today

EXCLUDED_COMPANIES = frozenset(
	["JURI GROUP", "PT. JUARA ROTI INDONESIA", "OUTLET", "TRAINING", "OUTLET PAMERAN"]
)
OUTLET_ROLES = ("HR Manager", "HR User", "System Manager")


@frappe.whitelist()
def sync_outlets_from_companies():
	"""Create an Outlet for every leaf Company except the group's own entities."""
	frappe.only_for(OUTLET_ROLES)

	companies = frappe.get_all("Company", filters={"is_group": 0}, pluck="name")
	created = 0
	for company in companies:
		if company in EXCLUDED_COMPANIES or frappe.db.exists("Outlet", company):
			continue
		frappe.get_doc({"doctype": "Outlet", "company": company}).insert(ignore_permissions=True)
		created += 1

	frappe.db.commit()
	return {"created": created, "companies": len(companies)}


@frappe.whitelist()
def provision_outlet(outlet):
	"""Assign the outlet's holiday list to all active employees of the outlet."""
	frappe.only_for(OUTLET_ROLES)

	outlet_doc = frappe.get_doc("Outlet", outlet)
	employees = frappe.get_all(
		"Employee", filters={"outlet": outlet, "status": "Active"}, pluck="name"
	)
	assigned = 0
	for employee in employees:
		if outlet_doc.holiday_list and _assign_holiday_list(employee, outlet_doc.holiday_list):
			assigned += 1

	frappe.db.commit()
	return {"employees": len(employees), "holidays_assigned": assigned}


def _assign_holiday_list(employee, holiday_list):
	if frappe.db.exists(
		"Holiday List Assignment",
		{
			"applicable_for": "Employee",
			"assigned_to": employee,
			"holiday_list": holiday_list,
			"docstatus": 1,
		},
	):
		return False

	holiday = frappe.get_doc("Holiday List", holiday_list)
	assignment = frappe.new_doc("Holiday List Assignment")
	assignment.holiday_list = holiday_list
	assignment.applicable_for = "Employee"
	assignment.assigned_to = employee
	assignment.from_date = max(getdate(holiday.from_date), getdate(today()))
	assignment.insert(ignore_permissions=True)
	if assignment.meta.is_submittable:
		assignment.submit()
	return True
