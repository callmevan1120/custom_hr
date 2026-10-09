frappe.pages["outlet-roster"].on_page_load = function (wrapper) {
	new OutletRoster(wrapper);
};

const OR_COLORS = {
	Blue: "#3b82f6",
	Cyan: "#06b6d4",
	Fuchsia: "#d946ef",
	Green: "#22c55e",
	Lime: "#84cc16",
	Orange: "#f97316",
	Pink: "#ec4899",
	Red: "#ef4444",
	Violet: "#8b5cf6",
	Yellow: "#eab308",
};

class OutletRoster {
	constructor(wrapper) {
		this.wrapper = wrapper;
		wrapper.roster = this;
		this.page = frappe.ui.make_app_page({
			parent: wrapper,
			title: __("Roster Outlet"),
			single_column: true,
		});
		this.month = new Date();
		this.month.setDate(1);
		this.token = 0;
		this.selected_outlet = null;

		this.page.main.html(`
			<div class="or-toolbar">
				<select class="form-control or-outlet-select">
					<option value="">${__("Memuat outlet...")}</option>
				</select>
				<button class="btn btn-default btn-sm or-swap">${__("Tukar Libur")}</button>
				<div class="or-nav">
					<button class="btn btn-default btn-sm or-prev">&lsaquo;</button>
					<span class="or-month"></span>
					<button class="btn btn-default btn-sm or-next">&rsaquo;</button>
				</div>
			</div>
			<div class="or-grid"></div>
		`);

		this.page.main.on("change", ".or-outlet-select", () => this.load());
		this.page.main.on("click", ".or-prev", () => {
			this.month.setMonth(this.month.getMonth() - 1);
			this.load();
		});
		this.page.main.on("click", ".or-next", () => {
			this.month.setMonth(this.month.getMonth() + 1);
			this.load();
		});
		this.page.main.on("click", ".or-cell", (event) => this.pick_shift(event.currentTarget));
		this.page.main.on("click", ".or-swap", () => this.open_swap_dialog());

		this.load_outlets();
	}

	load_outlets() {
		frappe.call({
			method: "custom_hr.api.roster.list_outlets",
			callback: (r) => {
				if (!r.message) return;
				const select = this.page.main.find(".or-outlet-select");
				select.html(`<option value="">${__("Pilih outlet")}</option>`);
				r.message.forEach((outlet) => {
					select.append(`<option value="${frappe.utils.escape_html(outlet)}">${frappe.utils.escape_html(outlet)}</option>`);
				});
				if (r.message.length === 1) {
					select.val(r.message[0]).trigger("change");
				} else {
					this.load();
				}
			},
		});
	}

	get outlet() {
		return this.page.main.find(".or-outlet-select").val() || null;
	}

	month_bounds() {
		const year = this.month.getFullYear();
		const month = this.month.getMonth();
		return {
			start: frappe.datetime.obj_to_str(new Date(year, month, 1)),
			end: frappe.datetime.obj_to_str(new Date(year, month + 1, 0)),
		};
	}

	load() {
		this.selected_outlet = this.outlet;
		this.page.main
			.find(".or-month")
			.text(this.month.toLocaleString("id-ID", { month: "long", year: "numeric" }));

		if (!this.selected_outlet) {
			this.data = null;
			this.page.main
				.find(".or-grid")
				.html(`<div class="or-empty">${__("Pilih outlet untuk mulai menyusun jadwal")}</div>`);
			return;
		}

		const { start, end } = this.month_bounds();
		const token = ++this.token;
		frappe.call({
			method: "custom_hr.api.roster.get_roster",
			args: { outlet: this.selected_outlet, start_date: start, end_date: end },
			callback: (r) => {
				if (token !== this.token || !r.message) return;
				this.render(r.message, start, end);
			},
		});
	}

	render(data, start, end) {
		this.data = data;
		const days = [];
		const last = moment(end, "YYYY-MM-DD");
		for (let day = moment(start, "YYYY-MM-DD"); day.isSameOrBefore(last); day.add(1, "day")) {
			days.push(day.format("YYYY-MM-DD"));
		}

		const color_of = {};
		(data.shift_options || []).forEach((option) => (color_of[option.value] = option.color));

		let html = `<table class="or-table"><thead><tr><th class="or-emp">${__("Karyawan")}</th>`;
		for (const date of days) {
			const dow = moment(date, "YYYY-MM-DD").day();
			html += `<th class="or-day${dow === 0 ? " is-off" : ""}">${Number(date.slice(8))}</th>`;
		}
		html += "</tr></thead><tbody>";

		for (const employee of data.employees) {
			html += `<tr><td class="or-emp">${frappe.utils.escape_html(employee.label)}</td>`;
			for (const date of days) {
				const shift = (data.shifts[employee.value] || {})[date];
				const holiday = (data.holidays[employee.value] || {})[date];
				let inner = "";
				if (shift) {
					const color = OR_COLORS[color_of[shift]] || "#64748b";
					inner = `<span class="or-chip" style="background:${color}">${frappe.utils.escape_html(
						short_shift(shift)
					)}</span>`;
				} else if (holiday) {
					inner = `<span class="or-hol">${frappe.utils.escape_html(holiday)}</span>`;
				}
				html += `<td class="or-cell" data-employee="${employee.value}" data-date="${date}" title="${frappe.utils.escape_html(
					shift || holiday || ""
				)}">${inner}</td>`;
			}
			html += "</tr>";
		}
		html += "</tbody></table>";

		if (!data.employees.length) {
			html = `<div class="or-empty">${__("Belum ada karyawan aktif di outlet ini")}</div>`;
		}
		this.page.main.find(".or-grid").html(html);
	}

	open_swap_dialog() {
		if (!this.selected_outlet || !this.data) {
			frappe.msgprint(__("Pilih outlet terlebih dahulu"));
			return;
		}

		const employees = this.data.employees;
		const options = this.data.shift_options || [];
		const dialog = new frappe.ui.Dialog({
			title: __("Tukar Hari Libur — {0}", [this.selected_outlet]),
			fields: [{ fieldtype: "HTML", fieldname: "body" }],
			primary_action_label: __("Terapkan"),
			primary_action: () => this.apply_swap(dialog),
		});

		const shift_options = options
			.map(
				(o) =>
					`<option value="${frappe.utils.escape_html(o.value)}">${frappe.utils.escape_html(o.value)}</option>`
			)
			.join("");
		const employee_rows = employees
			.map(
				(e) =>
					`<label><input type="checkbox" class="or-swap-emp" data-employee="${e.value}" checked> ${frappe.utils.escape_html(e.label)}</label>`
			)
			.join("");

		dialog.fields_dict.body.$wrapper.html(`
			<div class="or-swap-form">
				<div class="or-swap-row">
					<label>${__("Tanggal Kerja (masuk)")}<input type="date" class="form-control or-swap-work"></label>
					<label>${__("Tanggal Libur (pengganti)")}<input type="date" class="form-control or-swap-off"></label>
				</div>
				<label>${__("Shift untuk tanggal kerja")}
					<select class="form-control or-swap-shift">
						<option value="">${__("Sesuai jadwal tanggal libur")}</option>
						${shift_options}
					</select>
				</label>
				<div class="or-swap-emps">
					<label class="or-swap-all-label"><input type="checkbox" class="or-swap-all" checked> ${__("Semua karyawan")}</label>
					${employee_rows}
				</div>
			</div>
		`);
		dialog.$wrapper.on("change", ".or-swap-all", (event) => {
			dialog.$wrapper.find(".or-swap-emp").prop("checked", event.currentTarget.checked);
		});
		dialog.show();
	}

	apply_swap(dialog) {
		const wrapper = dialog.$wrapper;
		const work_date = wrapper.find(".or-swap-work").val();
		const off_date = wrapper.find(".or-swap-off").val();
		const shift_type = wrapper.find(".or-swap-shift").val() || null;
		const employees = wrapper
			.find(".or-swap-emp:checked")
			.map((_, element) => element.dataset.employee)
			.get();
		if (!work_date || !off_date) {
			frappe.msgprint(__("Isi tanggal kerja dan tanggal libur"));
			return;
		}
		if (!employees.length) {
			frappe.msgprint(__("Pilih minimal satu karyawan"));
			return;
		}

		frappe.call({
			method: "custom_hr.api.roster.swap_off_days",
			args: { outlet: this.selected_outlet, work_date, off_date, shift_type, employees },
			freeze: true,
			freeze_message: __("Menukar jadwal..."),
			callback: (r) => {
				if (r.exc) return;
				dialog.hide();
				frappe.show_alert({
					message: __("Jadwal ditukar: {0} karyawan", [r.message.moved]),
					indicator: "green",
				});
				this.load();
			},
		});
	}

	pick_shift(cell) {
		const employee = cell.dataset.employee;
		const date = cell.dataset.date;
		const current = (this.data.shifts[employee] || {})[date] || null;
		const employee_label =
			(this.data.employees.find((e) => e.value === employee) || {}).label || employee;

		const dialog = new frappe.ui.Dialog({
			title: `${employee_label} — ${frappe.datetime.str_to_user(date)}`,
			fields: [{ fieldtype: "HTML", fieldname: "options" }],
		});
		let html = `<div class="or-dialog">`;
		(this.data.shift_options || []).forEach((option) => {
			const color = OR_COLORS[option.color] || "#64748b";
			const active = option.value === current ? " is-active" : "";
			html += `<button class="btn btn-default btn-sm or-pick${active}" data-shift="${frappe.utils.escape_html(
				option.value
			)}" style="border-left:4px solid ${color}">${frappe.utils.escape_html(option.value)}</button>`;
		});
		html += `<button class="btn btn-default btn-sm or-clear" data-shift="">${__(
			"Libur (kosongkan jadwal)"
		)}</button>`;
		html += `</div>`;
		dialog.fields_dict.options.$wrapper.html(html);
		dialog.$wrapper.on("click", ".or-pick, .or-clear", (event) => {
			const shift = event.currentTarget.dataset.shift || null;
			dialog.hide();
			frappe.call({
				method: "custom_hr.api.roster.set_shift",
				args: { outlet: this.selected_outlet, employee, date, shift_type: shift },
				freeze: true,
				callback: (r) => {
					if (!r.exc) this.load();
				},
			});
		});
		dialog.show();
	}
}

function short_shift(shift) {
	const part = (shift.split(" ")[1] || shift).replace(/:00/g, "");
	return part;
}
