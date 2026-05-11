"""Importing this package registers all @api_router routes.

Order does not matter functionally (FastAPI keys routes by path+method)
but we sort alphabetically for readability.
"""
from . import auth  # noqa: F401
from . import contracts  # noqa: F401
from . import documents  # noqa: F401
from . import finance  # noqa: F401
from . import household  # noqa: F401
from . import inventory  # noqa: F401
from . import misc  # noqa: F401
from . import notifications  # noqa: F401
from . import push  # noqa: F401
from . import reports  # noqa: F401
from . import spaces  # noqa: F401
