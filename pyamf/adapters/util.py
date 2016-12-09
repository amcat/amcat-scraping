# Copyright (c) The PyAMF Project.
# See LICENSE.txt for details.

"""
Useful helpers for adapters.

@since: 0.4
"""

def to_list(obj, encoder):
    """
    Converts an arbitrary object C{obj} to a C{list}.
    """
    return list(obj)


def to_dict(obj, encoder):
    """
    Converts an arbitrary object C{obj} to a C{dict}.
    """
    return dict(obj)


def to_set(obj, encoder):
    """
    Converts an arbitrary object C{obj} to a C{set}.
    """
    return set(obj)


def to_tuple(obj, encoder):
    """
    Converts an arbitrary object C{obj} to a C{tuple}.
    """
    return tuple(obj)

