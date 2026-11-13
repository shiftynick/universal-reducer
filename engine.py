"""The single algorithm. It knows nothing about any particular system.

A pocket of reducibility is handed to it in one common form (a Pocket):
an object standing for "advance one step", and a way to combine two such
objects into the object for "do the first, then the second".

The engine reaches step n by doubling (1, 2, 4, 8, ...), using about
2*log2(n) combines instead of n steps. That only pays off when combined
objects stay small, so the engine reports the largest object it held.
"""

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Pocket:
    step: Any                           # stands for "advance one step"
    combine: Callable[[Any, Any], Any]  # combine(a, b) stands for "do a, then b"
    apply: Callable[[Any, Any], Any]    # apply(obj, state) carries obj out on a state
    size: Callable[[Any], int]          # bits needed to store obj


@dataclass(frozen=True)
class Jump:
    obj: Any        # stands for "advance n steps"
    combines: int   # how many combines the engine used
    largest: int    # largest object it had to hold, in bits


def fast_forward(pocket: Pocket, n: int) -> Jump:
    """Build the object for "advance n steps"."""
    if n < 1:
        raise ValueError("n must be at least 1")
    result = None
    power = pocket.step
    combines = 0
    largest = pocket.size(power)
    while True:
        if n & 1:
            if result is None:
                result = power
            else:
                result = pocket.combine(result, power)
                combines += 1
                largest = max(largest, pocket.size(result))
        n >>= 1
        if not n:
            return Jump(result, combines, largest)
        power = pocket.combine(power, power)
        combines += 1
        largest = max(largest, pocket.size(power))
