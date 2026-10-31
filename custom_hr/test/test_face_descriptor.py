import base64
import json
import os
import struct
import unittest
import zlib
from io import BytesIO
from unittest.mock import patch

import frappe
import numpy as np
from PIL import Image

from custom_hr.services.face_descriptor import FACE_IMAGE_MAX_BYTES, compute_descriptor, descriptor_from_face_image

REFERENCE = os.path.join(os.path.dirname(__file__), "fixtures", "face_descriptor_reference.json")


def lcg_image(seed):
	"""The deterministic 150x150 RGB image the browser reference was computed from."""
	state, values = seed, bytearray(150 * 150 * 3)
	for i in range(len(values)):
		state = (state * 1103515245 + 12345) & 0x7FFFFFFF
		values[i] = (state >> 16) & 0xFF
	return np.frombuffer(bytes(values), np.uint8).reshape(150, 150, 3)


def data_url(pixels, mode="RGB", fmt="PNG"):
	buffer = BytesIO()
	Image.fromarray(pixels, mode).save(buffer, fmt)
	return f"data:image/{fmt.lower()};base64," + base64.b64encode(buffer.getvalue()).decode()


class TestFaceDescriptor(unittest.TestCase):
	def test_numpy_is_a_declared_dependency(self):
		# only installed today because another app pulls it in; Frappe Cloud builds from pyproject
		import tomllib

		pyproject = tomllib.load(open(frappe.get_app_path("custom_hr", "..", "pyproject.toml"), "rb"))
		self.assertTrue(any(dep.replace(" ", "").startswith("numpy>=") for dep in pyproject["project"]["dependencies"]))

	def test_numpy_math_stays_on_one_core_per_worker(self):
		# set by custom_hr/__init__.py, which Frappe imports before anything loads numpy
		self.assertEqual(os.environ.get("OPENBLAS_NUM_THREADS"), "1")
		self.assertEqual(os.environ.get("OMP_NUM_THREADS"), "1")

	def test_matches_the_browser_descriptor(self):
		reference = json.load(open(REFERENCE))
		descriptor = compute_descriptor(lcg_image(reference["seed"]))
		self.assertLess(np.linalg.norm(descriptor - np.array(reference["descriptor"])), 1e-4)

	def test_reads_a_png_face_image(self):
		image = lcg_image(1)
		descriptor = descriptor_from_face_image(data_url(image))
		self.assertEqual(len(descriptor), 128)
		self.assertLess(np.linalg.norm(np.array(descriptor) - compute_descriptor(image)), 1e-6)

	def test_transparent_padding_counts_as_black(self):
		# imageToSquare leaves the padding transparent; tf.browser.fromPixels reads it as RGB 0
		rgb = lcg_image(2).copy()
		rgba = np.dstack([rgb, np.full((150, 150), 255, np.uint8)])
		rgba[:10, :, :3] = 255
		rgba[:10, :, 3] = 0
		rgb[:10] = 0
		self.assertLess(np.linalg.norm(np.array(descriptor_from_face_image(data_url(rgba, "RGBA"))) - compute_descriptor(rgb)), 1e-6)

	def test_refuses_a_wrong_size_png_before_decoding_its_pixels(self):
		# a tiny file can hold a huge flat image (12000px PNG < 200 KB): decoding it first costs ~140 MB
		with patch("PIL.ImageFile.ImageFile.load", side_effect=AssertionError("pixels decoded")):
			with self.assertRaises(frappe.ValidationError):
				descriptor_from_face_image(data_url(np.zeros((300, 300, 3), np.uint8)))

	def test_refuses_a_decompression_bomb_header(self):
		png = bytearray(base64.b64decode(data_url(np.zeros((1, 1, 3), np.uint8)).split(",", 1)[1]))
		png[16:24] = struct.pack(">II", 20000, 20000)  # IHDR width/height
		png[29:33] = struct.pack(">I", zlib.crc32(bytes(png[12:29])))
		with self.assertRaises(frappe.ValidationError):
			descriptor_from_face_image("data:image/png;base64," + base64.b64encode(bytes(png)).decode())

	def test_refuses_anything_but_a_150px_png(self):
		too_big = "data:image/png;base64," + "A" * (FACE_IMAGE_MAX_BYTES * 2)
		for value in (data_url(lcg_image(1), fmt="JPEG"), data_url(lcg_image(1)[:, :149].copy()), "not a data url", too_big, None):
			with self.assertRaises(frappe.ValidationError, msg=str(value)[:40]):
				descriptor_from_face_image(value)
