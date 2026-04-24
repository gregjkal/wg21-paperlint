#
# Copyright (c) 2026 Sergio DuBois (sentientsergio@gmail.com)
#
# Distributed under the Boost Software License, Version 1.0. (See accompanying
# file LICENSE_1_0.txt or copy at http://www.boost.org/LICENSE_1_0.txt)
#
# Official repository: https://github.com/cppalliance/paperlint
#

"""Transition shim: storage lives in the ``paperstore`` package now.

Remove once all paperlint-internal imports reference ``paperstore`` directly.
"""

from __future__ import annotations

from paperstore import JsonBackend, StorageBackend

__all__ = ["JsonBackend", "StorageBackend"]
