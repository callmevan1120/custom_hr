app_name = "custom_hr"
app_title = "Custom HR"
app_publisher = "callmevan1120"
app_description = "Custom HR extensions on top of Frappe HR: attendance gallery, face check-in, realtime attendance marking"
app_email = "admin@example.com"
app_license = "mit"
required_apps = ["hrms"]

# ----------------------------------------------------------------------------
# Desk assets
# ----------------------------------------------------------------------------

# Drop Frappe's cached copy of the attendance gallery page on every desk boot,
# so an updated page script/style is always picked up.
app_include_js = "custom_hr.bundle.js"

# ----------------------------------------------------------------------------
# DocType javascript
# ----------------------------------------------------------------------------

doctype_js = {
	"Employee": "public/js/employee_face.js",
}

doctype_list_js = {
	"Employee Checkin": "public/js/employee_checkin_list.js",
}

# ----------------------------------------------------------------------------
# DocType overrides
# ----------------------------------------------------------------------------

# self-service check-in limits, face verification requirement, realtime
# attendance marking right after check-out
override_doctype_class = {
	"Employee Checkin": "custom_hr.overrides.employee_checkin.CustomEmployeeCheckin",
}

# ----------------------------------------------------------------------------
# Fixtures
# ----------------------------------------------------------------------------

fixtures = [
	{
		"doctype": "Custom Field",
		"filters": [
			[
				"name",
				"in",
				[
					"Employee Checkin-face_verification_section",
					"Employee Checkin-face_verified",
					"Employee Checkin-face_score",
					"Employee Checkin-column_break_face",
					"Employee Checkin-face_photo",
					"HR Settings-enable_face_checkin",
					"HR Settings-require_face_checkin",
					"HR Settings-face_match_threshold",
					"HR Settings-face_enroll_samples",
				],
			]
		],
	},
	{"doctype": "Workspace", "filters": [["name", "=", "Shift & Attendance"]]},
]
