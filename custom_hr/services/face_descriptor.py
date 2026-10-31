"""128-value face descriptor computed on the server.

A numpy port of face-api's FaceRecognitionNet (@vladmandic/face-api 1.7.15,
src/faceRecognitionNet), run on the same weight files the browser used, so
descriptors match those enrolled from phones. The phone sends the aligned face
as face-api prepares it: a 150x150 PNG (imageToSquare of the aligned crop).
"""

import base64
import binascii
import json
import os
from io import BytesIO

import frappe
import numpy as np
from frappe import _
from numpy.lib.stride_tricks import sliding_window_view
from PIL import Image, UnidentifiedImageError

FACE_IMAGE_SIZE = 150
FACE_IMAGE_MAX_BYTES = 200_000
PNG_PREFIX = "data:image/png;base64,"
MEAN_RGB = np.array([122.782, 117.001, 104.298], np.float32)

_weights = None


def descriptor_from_face_image(data_url: str) -> list[float]:
	return compute_descriptor(_decode_face_image(data_url)).tolist()


def compute_descriptor(rgb: np.ndarray) -> np.ndarray:
	"""rgb: 150x150x3 aligned face, values 0-255."""
	W = _load_weights()
	x = (rgb.astype(np.float32) - MEAN_RGB) / 255
	x = _conv_layer(x, W, "conv32_down", 2, True, "valid")
	x = _pool(x, 3, 2, "max")
	for name in ("conv32_1", "conv32_2", "conv32_3"):
		x = _residual(x, W, name)
	x = _residual_down(x, W, "conv64_down")
	for name in ("conv64_1", "conv64_2", "conv64_3"):
		x = _residual(x, W, name)
	x = _residual_down(x, W, "conv128_down")
	for name in ("conv128_1", "conv128_2"):
		x = _residual(x, W, name)
	x = _residual_down(x, W, "conv256_down")
	for name in ("conv256_1", "conv256_2"):
		x = _residual(x, W, name)
	x = _residual_down(x, W, "conv256_down_out")
	return x.mean(axis=(0, 1)) @ W["fc"]


def _decode_face_image(data_url):
	if not isinstance(data_url, str) or not data_url.startswith(PNG_PREFIX):
		frappe.throw(_("Invalid face image."))
	payload = data_url[len(PNG_PREFIX):]
	if len(payload) * 3 // 4 > FACE_IMAGE_MAX_BYTES:  # check before decoding anything
		frappe.throw(_("Invalid face image."))
	try:
		# PNG decoder only, and the size checked from the header before any pixel is decoded:
		# a small file can still describe a huge image
		image = Image.open(BytesIO(base64.b64decode(payload, validate=True)), formats=["PNG"])
		if image.size != (FACE_IMAGE_SIZE, FACE_IMAGE_SIZE):
			frappe.throw(_("Invalid face image."))
		rgba = np.asarray(image.convert("RGBA"))
	except (binascii.Error, ValueError, OSError, UnidentifiedImageError, Image.DecompressionBombError):
		frappe.throw(_("Invalid face image."))
	# imageToSquare leaves its padding transparent; tf.browser.fromPixels reads that as black
	return np.where(rgba[..., 3:] == 0, 0, rgba[..., :3]).astype(np.uint8)


def _load_weights():
	global _weights
	if _weights is None:
		_weights = _read_weights(frappe.get_app_path("custom_hr", "public", "face", "models"), "face_recognition_model")
	return _weights


def _read_weights(folder, name):
	weights = {}
	for group in json.load(open(os.path.join(folder, f"{name}-weights_manifest.json"))):
		raw = b"".join(open(os.path.join(folder, path), "rb").read() for path in group["paths"])
		offset = 0
		for spec in group["weights"]:
			count = int(np.prod(spec["shape"])) if spec["shape"] else 1
			quantization = spec.get("quantization")
			dtype = np.dtype(quantization["dtype"] if quantization else "float32")
			values = np.frombuffer(raw, dtype=dtype, count=count, offset=offset).astype(np.float32)
			if quantization:
				values = values * quantization["scale"] + quantization["min"]
			offset += count * dtype.itemsize
			weights[spec["name"]] = values.reshape(spec["shape"]).astype(np.float32)
	return weights


def _same_padding(size, kernel, stride):
	out = -(-size // stride)
	total = max((out - 1) * stride + kernel - size, 0)
	return total // 2, total - total // 2


def _conv2d(x, filters, stride, padding):
	"""TensorFlow conv2d semantics; x is HxWxC, filters are kh x kw x in x out."""
	kh, kw, cin, cout = filters.shape
	if padding == "same":
		x = np.pad(x, (_same_padding(x.shape[0], kh, stride), _same_padding(x.shape[1], kw, stride), (0, 0)))
	windows = sliding_window_view(x, (kh, kw), axis=(0, 1))[::stride, ::stride]
	oh, ow = windows.shape[:2]
	columns = windows.reshape(oh * ow, cin * kh * kw)
	return (columns @ filters.transpose(2, 0, 1, 3).reshape(cin * kh * kw, cout)).reshape(oh, ow, cout)


def _pool(x, size, stride, op):
	windows = sliding_window_view(x, (size, size), axis=(0, 1))[::stride, ::stride]
	return windows.max(axis=(3, 4)) if op == "max" else windows.mean(axis=(3, 4))


def _conv_layer(x, W, prefix, stride, relu, padding="same"):
	out = _conv2d(x, W[f"{prefix}/conv/filters"], stride, padding) + W[f"{prefix}/conv/bias"]
	out = out * W[f"{prefix}/scale/weights"] + W[f"{prefix}/scale/biases"]
	return np.maximum(out, 0) if relu else out


def _residual(x, W, prefix):
	out = _conv_layer(x, W, f"{prefix}/conv1", 1, True)
	out = _conv_layer(out, W, f"{prefix}/conv2", 1, False)
	return np.maximum(out + x, 0)


def _residual_down(x, W, prefix):
	out = _conv_layer(x, W, f"{prefix}/conv1", 2, True, "valid")
	out = _conv_layer(out, W, f"{prefix}/conv2", 1, False)
	pooled = _pool(x, 2, 2, "avg")
	if pooled.shape[:2] != out.shape[:2]:  # face-api pads the conv branch with a zero row and column at the end
		out = np.pad(out, ((0, pooled.shape[0] - out.shape[0]), (0, pooled.shape[1] - out.shape[1]), (0, 0)))
	if pooled.shape[2] != out.shape[2]:
		pooled = np.pad(pooled, ((0, 0), (0, 0), (0, out.shape[2] - pooled.shape[2])))
	return np.maximum(pooled + out, 0)
