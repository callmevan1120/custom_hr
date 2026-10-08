// Frappe desk caches standard pages in localStorage, which keeps stale page
// scripts/styles after an update. Drop the cached attendance gallery page on
// every desk boot so it always loads the current version from the app.
try {
	localStorage.removeItem("_page:employee-attendance-gallery");
} catch (e) {
	// ignore storage errors (private mode etc.)
}
