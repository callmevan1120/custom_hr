// Frappe desk caches standard pages in localStorage, which keeps stale page
// scripts/styles after an update. Drop cached app pages on every desk boot so
// they always load the current version from the app.
for (const page of ["employee-attendance-gallery", "outlet-roster"]) {
	try {
		localStorage.removeItem(`_page:${page}`);
	} catch (e) {
		// ignore storage errors (private mode etc.)
	}
}
