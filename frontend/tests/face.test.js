import test from "node:test"
import assert from "node:assert/strict"
import path from "node:path"
import { fileURLToPath } from "node:url"
import vm from "node:vm"
import { build } from "esbuild"

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..")
const bundle = await build({
	entryPoints: [path.join(root, "src/utils/face.js")], bundle: true, write: false, format: "cjs", platform: "node",
	plugins: [{ name: "face-api-mock", setup(b) {
		b.onResolve({ filter: /^@vladmandic\/face-api$/ }, () => ({ path: "face-api", namespace: "mock" }))
		b.onLoad({ filter: /.*/, namespace: "mock" }, () => ({ contents: "module.exports = globalThis.__faceapi", loader: "js" }))
	} }],
})

function load(contextLost) {
	const calls = []
	let backend = "webgl"
	const faceapi = {
		TinyFaceDetectorOptions: class {},
		tf: {
			getBackend: () => backend,
			backend: () => ({ gpgpu: { gl: { isContextLost: () => contextLost } } }),
			setBackend: async (name) => { calls.push(`setBackend:${name}`); backend = name },
			ready: async () => {},
		},
		detectSingleFace: () => {
			calls.push(`detect:${backend}`)
			return { withFaceLandmarks: () => ({ withFaceDescriptor: async () => "face" }) }
		},
	}
	const module = { exports: {} }
	vm.runInNewContext(bundle.outputFiles[0].text, { module, exports: module.exports, globalThis: { __faceapi: faceapi } })
	return { face: module.exports, calls }
}

test("detectFace moves to the cpu backend once the webgl context is lost (native camera app)", async () => {
	const { face, calls } = load(true)
	assert.equal(await face.detectFace({}), "face")
	assert.deepEqual(calls, ["setBackend:cpu", "detect:cpu"])
})

test("detectFace keeps webgl while its context is alive", async () => {
	const { face, calls } = load(false)
	assert.equal(await face.detectFace({}), "face")
	assert.deepEqual(calls, ["detect:webgl"])
})
