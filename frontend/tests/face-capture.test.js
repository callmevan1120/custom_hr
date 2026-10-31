import test from "node:test"
import assert from "node:assert/strict"
import fs from "node:fs/promises"
import path from "node:path"
import { fileURLToPath } from "node:url"
import { createRequire } from "node:module"
import vm from "node:vm"
import { build } from "esbuild"
import { parse, compileScript } from "@vue/compiler-sfc"
import { createRenderer, defineComponent, h, nextTick } from "vue"

const require = createRequire(import.meta.url)
const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const source = await fs.readFile(path.join(root, "src/components/FaceCapture.vue"), "utf8")
const compiled = compileScript(parse(source).descriptor, { id: "face-capture", inlineTemplate: true })
const mocks = ["frappe-ui", "@vladmandic/face-api", "@/utils/face"]
const bundle = await build({
	stdin: { contents: compiled.content, resolveDir: root, loader: "js" }, bundle: true, write: false, format: "cjs", platform: "node", external: ["vue"],
	plugins: [{ name: "face-capture-mocks", setup(b) {
		b.onResolve({ filter: /.*/ }, ({ path: name }) => mocks.includes(name) ? { path: name, namespace: "mock" } : null)
		b.onLoad({ filter: /.*/, namespace: "mock" }, ({ path: name }) => ({ contents: `module.exports = globalThis.__mocks[${JSON.stringify(name)}]`, loader: "js" }))
	} }],
})
const flush = async () => { for (let i = 0; i < 6; i++) { await new Promise(setImmediate); await nextTick() } }

function mount(globals = {}) {
	const pending = [], constraints = []
	let tick = null
	const Button = defineComponent({ props: ["disabled", "loading"], setup(_, { slots }) { return () => h("button", {}, slots.default?.()) } })
	const navigator = { mediaDevices: { getUserMedia: async (c) => { constraints.push(c); return { getTracks: () => [] } } } }
	const module = { exports: {} }
	vm.runInNewContext(bundle.outputFiles[0].text, {
		module, exports: module.exports, require, console, navigator, setTimeout, clearTimeout, ...globals,
		setInterval: (fn) => { tick = fn; return 1 }, clearInterval: () => { tick = null },
		__mocks: {
			"frappe-ui": { Button },
			"@vladmandic/face-api": { detectSingleFace: () => new Promise((resolve) => pending.push(resolve)) },
			"@/utils/face": { loadFaceModels: async () => {}, detectorOptions: () => ({}), ensureLiveBackend: async () => {}, withTimeout: (p) => p,
				detectFace: async () => null, snapshotCanvas: () => ({}), descriptorToArray: Array.from },
		},
	})
	const detach = (node) => { if (node.parent) { const i = node.parent.children.indexOf(node); if (i >= 0) node.parent.children.splice(i, 1) } }
	const renderer = createRenderer({
		createElement: (type) => ({ type, children: [], props: {}, style: {}, text: "", play: async () => {} }), createText: (text) => ({ type: "text", text }), createComment: (text) => ({ type: "comment", text }),
		setText: (n, text) => { n.text = text }, setElementText: (n, text) => { n.text = text; n.children = [] },
		patchProp: (n, key, _, value) => { n.props[key] = value }, insert: (n, p, anchor) => { detach(n); n.parent = p; const index = anchor ? p.children.indexOf(anchor) : -1; if (index < 0) p.children.push(n); else p.children.splice(index, 0, n) }, remove: detach,
		parentNode: (n) => n.parent, nextSibling: (n) => n.parent?.children[n.parent.children.indexOf(n) + 1] || null,
	})
	const app = renderer.createApp(module.exports.default)
	app.provide("$translate", (text, args = []) => text.replace(/\{(\d+)\}/g, (_, i) => args[i]))
	const host = { children: [] }
	app.mount(host)
	const nodes = (type, n = host) => [...(n.type === type ? [n] : []), ...(n.children || []).flatMap((c) => nodes(type, c))]
	const text = (n = host) => n.type === "comment" ? "" : (n.text || "") + (n.children || []).map((c) => text(c)).join(" ")
	const pickPhoto = (file) => nodes("input")[0].props.onChange({ target: { files: [file] } })
	return { pending, constraints, text, pickPhoto, tick: () => tick(), unmount: () => app.unmount() }
}

test("the camera asks for a small frame: the detector shrinks it anyway", async () => {
	const ui = mount(); try {
		await flush()
		assert.equal(ui.constraints[0].video.width.ideal, 480)
		assert.equal(ui.constraints[0].video.height.ideal, 640)
	} finally { ui.unmount() }
})

test("a native camera photo is decoded small and upright, then released", async () => {
	const decoded = []
	const bitmap = { width: 640, height: 853, closed: false, close() { this.closed = true } }
	const ui = mount({ createImageBitmap: async (file, options) => { decoded.push([file, options]); return bitmap } }); try {
		await flush()
		await ui.pickPhoto("photo.jpg"); await flush()
		assert.equal(decoded.length, 1)
		assert.equal(decoded[0][1].resizeWidth, 640)
		assert.equal(decoded[0][1].imageOrientation, "from-image")
		assert.ok(bitmap.closed)
		assert.match(ui.text(), /Face not detected in the photo/)
	} finally { ui.unmount() }
})

test("a browser that rejects the decode options still reads the photo, without a base64 copy", async () => {
	const urls = []
	class Image { set src(value) { this.loaded = value; this.onload() } }
	const URL = { createObjectURL: () => { urls.push("open"); return "blob:photo" }, revokeObjectURL: () => urls.push("revoked") }
	const ui = mount({ createImageBitmap: async () => { throw new TypeError("bad option") }, Image, URL }); try {
		await flush()
		await ui.pickPhoto("photo.jpg"); await flush()
		assert.deepEqual(urls, ["open", "revoked"])
		assert.match(ui.text(), /Face not detected in the photo/)
	} finally { ui.unmount() }
})

test("a slow detection is never stacked: the next one waits until it answers", async () => {
	const ui = mount(); try {
		await flush()
		ui.tick(); ui.tick(); ui.tick(); await flush()
		assert.equal(ui.pending.length, 1)
		ui.pending[0](null); await flush()
		ui.tick(); await flush()
		assert.equal(ui.pending.length, 2)
	} finally { ui.unmount() }
})
