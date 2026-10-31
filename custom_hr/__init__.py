import os

__version__ = "0.0.1"

# The server-side face descriptor (services/face_descriptor.py) runs numpy matmuls; by default
# BLAS spreads each one over every core (12x the CPU for the same face). Frappe imports this
# package before anything loads numpy, so the limit applies to every worker.
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("OMP_NUM_THREADS", "1")
