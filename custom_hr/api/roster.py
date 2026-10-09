# Copyright (c) 2026, callmevan1120 and contributors
# For license information, please see license.txt

"""Roster APIs: month grid of shift assignments for one outlet."""

import frappe
from frappe import _
from frappe.utils import add_days, getdate

HR_ROLES = ("HR Manager", "HR User", "System Manager")
WEEKDAY_ID = {
	"Monday": "Senin",
	"Tuesday": "Selasa",
	"Wednesday": "Rabu",
	"Thursday": "Kamis",
	"Friday": "Jumat",
	"Saturday": "Sabtu",
	"Sunday": "Minggu",
}


@frappe.whitelist()
def list_outlets():
	"""Outlets the current user may plan for."""
	allowed = _allowed_outlets()
	if allowed is None:
		allowed = frappe.get_all(
			"Outlet",
			filters={"is_active": 1},
			pluck="name",
			order_by="name",
			ignore_permissions=True,
		)
	return allowed


@frappe.whitelist()
def get_roster(outlet: str, start_date: str, end_date: str):
	_check_outlet_access(outlet)

	employees = frappe.get_all(
		"Employee",
		filters={"outlet": outlet, "status": "Active"},
		fields=["name", "employee_name"],
		order_by="employee_name",
		ignore_permissions=True,
	)
	names = [employee.name for employee in employees]
	return {
		"employees": [{"value": e.name, "label": e.employee_name} for e in employees],
		"shifts": _shift_map(names, start_date, end_date),
		"holidays": {name: _holiday_map(name, start_date, end_date) for name in names},
		"shift_options": _shift_options(outlet),
	}


@frappe.whitelist()
def set_shift(outlet: str, employee: str, date: str, shift_type: str | None = None):
	_check_outlet_access(outlet)
	if frappe.db.get_value("Employee", employee, "outlet") != outlet:
		frappe.throw(_("Karyawan tidak berada di outlet ini"), frappe.PermissionError)

	_remove_assignments(employee, date)
	if shift_type:
		frappe.get_doc(
			{
				"doctype": "Shift Assignment",
				"employee": employee,
				"employee_name": frappe.db.get_value("Employee", employee, "employee_name"),
				"company": frappe.db.get_value("Employee", employee, "company"),
				"shift_type": shift_type,
				"start_date": date,
				"end_date": date,
				"status": "Active",
			}
		).insert(ignore_permissions=True)

	frappe.db.commit()
	return {"employee": employee, "date": date, "shift_type": shift_type}


def _check_outlet_access(outlet):
	allowed = _allowed_outlets()
	if allowed is not None and outlet not in allowed:
		frappe.throw(_("Anda tidak punya akses ke outlet ini"), frappe.PermissionError)


def _allowed_outlets():
	user = frappe.session.user
	if set(HR_ROLES) & set(frappe.get_roles(user)):
		return None

	outlets = frappe.get_all(
		"Outlet",
		filters={"is_active": 1},
		or_filters=[["approver_1", "=", user], ["approver_2", "=", user]],
		pluck="name",
		ignore_permissions=True,
	)
	if not outlets:
		frappe.throw(
			_("Anda tidak terdaftar sebagai approver outlet mana pun"), frappe.PermissionError
		)
	return outlets


def _shift_map(employees, start_date, end_date):
	if not employees:
		return {}

	rows = frappe.get_all(
		"Shift Assignment",
		filters={
			"employee": ["in", employees],
			"docstatus": ["!=", 2],
			"status": "Active",
			"start_date": ["<=", end_date],
			"end_date": [">=", start_date],
		},
		fields=["employee", "shift_type", "start_date", "end_date"],
		ignore_permissions=True,
	)
	result = {}
	for row in rows:
		day = max(getdate(row.start_date), getdate(start_date))
		last = min(getdate(row.end_date or row.start_date), getdate(end_date))
		while day <= last:
			result.setdefault(row.employee, {})[str(day)] = row.shift_type
			day = add_days(day, 1)
	return result


def _holiday_map(employee, start_date, end_date):
	from erpnext.setup.doctype.employee.employee import get_holiday_list_for_employee

	holiday_list = get_holiday_list_for_employee(employee, raise_exception=False)
	if not holiday_list:
		return {}

	holidays = {}
	weekly_off = frappe.db.get_value("Holiday List", holiday_list, "weekly_off")
	if weekly_off:
		day = getdate(start_date)
		while day <= getdate(end_date):
			if day.strftime("%A") == weekly_off:
				holidays[str(day)] = WEEKDAY_ID.get(weekly_off, weekly_off)
			day = add_days(day, 1)

	rows = frappe.get_all(
		"Holiday",
		filters={"parent": holiday_list, "holiday_date": ["between", [start_date, end_date]]},
		fields=["holiday_date", "description"],
		ignore_permissions=True,
	)
	for row in rows:
		holidays[str(row.holiday_date)] = row.description or _("Libur")
	return holidays


def _shift_options(outlet):
	rows = frappe.get_all(
		"Outlet Shift",
		filters={"parent": outlet, "enabled": 1},
		fields=["shift_type"],
		ignore_permissions=True,
	)
	options = []
	for row in rows:
		color = frappe.db.get_value("Shift Type", row.shift_type, "color") or "Blue"
		options.append({"value": row.shift_type, "label": row.shift_type, "color": color})
	return options


def _remove_assignments(employee, date):
	rows = frappe.get_all(
		"Shift Assignment",
		filters={
			"employee": employee,
			"docstatus": ["!=", 2],
			"start_date": ["<=", date],
			"end_date": [">=", date],
		},
		fields=["name", "start_date", "end_date"],
		ignore_permissions=True,
	)
	for row in rows:
		start, end = getdate(row.start_date), getdate(row.end_date or row.start_date)
		if start < getdate(date):
			_duplicate_assignment(row.name, row.start_date, add_days(date, -1))
		if end > getdate(date):
			_duplicate_assignment(row.name, add_days(date, 1), row.end_date)
		frappe.delete_doc("Shift Assignment", row.name, ignore_permissions=True, force=True)


def _duplicate_assignment(name, start_date, end_date):
	copy = frappe.copy_doc(frappe.get_doc("Shift Assignment", name))
	copy.start_date = start_date
	copy.end_date = end_date
	copy.insert(ignore_permissions=True)
