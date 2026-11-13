"""Clever algorithms: multiplying two large numbers.

The system: start at 0 and add the number a, over and over. After b steps the
total is a times b. Three ways to get there, all counted in the same unit,
one single-bit addition:

  repeated addition through the engine
      The step object is the number a and combining is addition, so nothing
      is added to the form. Doubling turns b additions into about one and a
      half additions per binary digit of b. That is the school method, which
      the engine arrives at by itself.

  the school method, written out directly
      One shifted copy of a per binary digit of b, added up.

  the fast method (Karatsuba)
      Split each number into a high half and a low half. The school method
      needs four half-sized products; a rearrangement gets by with three.
      Do the same again inside each of the three.

Why the fast method does not fit the form. The engine works along a chain: a
jump of 2k steps is two copies of the same k-step object, so that object is
worked out once and used twice. The fast method splits one product into three
different smaller products, and three different pieces do not collapse into
one. The only way through the engine is as a single step with the whole
method inside `apply` and `combine`: no combines, engine idle.
"""

from engine import Pocket
from translators import Translation, _same

CUTOFF = 32  # below this many bits the fast method hands over to the school method


class Meter:
    """Counts single-bit additions."""

    def __init__(self):
        self.bits = 0

    def add(self, a, b):
        self.bits += max(a.bit_length(), b.bit_length(), 1)
        return a + b

    def sub(self, a, b):
        self.bits += max(a.bit_length(), b.bit_length(), 1)
        return a - b


def school(a: int, b: int, meter: Meter) -> int:
    total = 0
    for i in range(b.bit_length()):
        if (b >> i) & 1:
            total += a << i
        meter.bits += a.bit_length()  # one row of the sum, whether or not it is blank
    return total


def fast(a: int, b: int, meter: Meter) -> int:
    if not a or not b:
        return 0
    n = max(a.bit_length(), b.bit_length())
    if n <= CUTOFF:
        return school(a, b, meter)
    half = n // 2
    mask = (1 << half) - 1
    a_low, a_high, b_low, b_high = a & mask, a >> half, b & mask, b >> half
    low = fast(a_low, b_low, meter)
    high = fast(a_high, b_high, meter)
    # (a_low + a_high)(b_low + b_high) holds both cross products at once
    cross = fast(meter.add(a_low, a_high), meter.add(b_low, b_high), meter)
    cross = meter.sub(meter.sub(cross, low), high)
    return meter.add(meter.add(low, cross << half), high << (2 * half))


def repeated_addition(a: int, meter: Meter) -> Translation:
    """Start at 0 and add a at every step. The step object is the number a."""
    pocket = Pocket(a, meter.add, meter.add, lambda x: max(1, x.bit_length()))
    return Translation(pocket, _same, _same, 0)


def one_step(a: int, meter: Meter) -> Translation:
    """Multiply by a at every step. A single step is the whole product, so the
    fast method sits inside `apply` and the engine has nothing to do."""
    def multiply(x, y):
        return fast(x, y, meter)

    pocket = Pocket(a, multiply, multiply, lambda x: max(1, x.bit_length()))
    return Translation(pocket, _same, _same, 0)
