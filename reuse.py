"""Hashlife-style reuse: one translator for every rule, no proof needed.

The system is a two-colour cellular automaton on an endless line of cells
that starts white everywhere except a finite patch. A cell's next colour
depends on itself and `radius` neighbours on each side: radius 1 gives the
256 elementary rules, radius 2 a family of about four billion. A state is (offset,
bits): bit i of `bits` is the cell at position offset + i, and a 1 marks a
cell that differs from the background. The background is white at the start.
What it does next depends on the rule, in one of three ways:

  stays white    one pocket step is one real step
  blinks         white, black, white, ...: one pocket step is two real steps,
                 and only even-numbered rows are predicted
  turns black    black from step 1 on. Swapping the two colours then gives a
                 "twin" rule with a white background, so the translator runs
                 one real step, swaps colours, and hands over the twin

How it fits the engine's form:
  step object   a recipe, not a finished object. The base recipe is "advance
                one step". combine(a, b) just records "a, then b".
  apply         carries a recipe out on a tree of cells. The row is stored as
                a tree whose identical pieces are stored once, and each recipe
                keeps a table of the pieces it has already advanced. A piece
                is advanced by splitting it into overlapping halves, exactly
                the doubling the engine does in time, repeated in space.

Nothing here knows why a rule might be reducible. If pieces of the pattern
repeat, the tables stay small and the jump is cheap. If they do not, the
tables grow as fast as running the system would. The cost is known only
afterwards, as the number of table entries filled.
"""

from engine import Pocket
from translators import Translation

_PRIME = (1 << 61) - 1
_BASE = 0x1F3A5C7E9B2D4F61 % _PRIME


class _Recipe:
    __slots__ = ("steps", "first", "second", "table")

    def __init__(self, steps, first=None, second=None):
        self.steps = steps
        self.first = first
        self.second = second
        self.table = {}  # piece -> that piece's middle half, `steps` later


class OverBudget(Exception):
    """The tables grew past the allowed size: no pocket found within budget."""


class Reuse:
    def __init__(self, rule: int, budget: int | None = None, unit: int = 1, radius: int = 1):
        all_black = (1 << (2 * radius + 1)) - 1  # the neighbourhood with every cell black
        colour = 0  # of an all-white row after `unit` steps
        for _ in range(unit):
            colour = (rule >> (all_black * colour)) & 1
        if unit not in (1, 2) or radius not in (1, 2) or colour:
            raise ValueError("a white row must be white again after one pocket step")
        self.rule = rule
        self.radius = radius
        self.unit = unit             # real steps per pocket step
        self.reach = radius * unit   # cells a change can travel in one pocket step
        self.base_level = (4 * self.reach).bit_length() - 1  # smallest piece a step is worked out on
        self.budget = budget  # give up once this many table entries are filled
        # Pieces of row. Piece 0 is one white cell, piece 1 one black cell;
        # every other piece is a left half and a right half, stored once.
        self.left = [None, None]
        self.right = [None, None]
        self.level = [0, 0]   # a piece of level k is 2**k cells long
        self.count = [0, 1]   # black cells in the piece
        self.print = [0, 1]   # fingerprint of where the black cells are
        self._by_halves = {}
        self._white = [0]
        self._shift = [_BASE]  # _shift[k] = _BASE ** (2**k)
        self.base = _Recipe(1)
        self._recipes = {}
        self.filled = 0       # table entries filled so far: the real cost

    # --- pieces ---

    def join(self, a, b):
        key = (a, b)
        piece = self._by_halves.get(key)
        if piece is None:
            piece = len(self.left)
            k = self.level[a]
            while len(self._shift) <= k:
                self._shift.append(self._shift[-1] ** 2 % _PRIME)
            self.left.append(a)
            self.right.append(b)
            self.level.append(k + 1)
            self.count.append(self.count[a] + self.count[b])
            self.print.append((self.print[a] + self._shift[k] * self.print[b]) % _PRIME)
            self._by_halves[key] = piece
        return piece

    def white(self, level):
        while len(self._white) <= level:
            self._white.append(self.join(self._white[-1], self._white[-1]))
        return self._white[level]

    # --- recipes ---

    def then(self, a, b):
        key = (id(a), id(b))
        recipe = self._recipes.get(key)
        if recipe is None:
            recipe = self._recipes[key] = _Recipe(a.steps + b.steps, a, b)
        return recipe

    def run(self, recipe, piece):
        """The middle half of `piece`, advanced by the recipe's number of steps."""
        out = recipe.table.get(piece)
        if out is not None:
            return out
        level = self.level[piece]
        reach = self.reach * recipe.steps  # how far the recipe can carry a change
        assert 4 * reach <= 1 << level, "piece too small for this recipe"
        left, right, join = self.left, self.right, self.join
        if self.count[piece] == 0:
            out = self.white(level - 1)
        elif level == self.base_level:  # one pocket step: apply the rule itself
            row = [(self._bits(piece) >> i) & 1 for i in range(1 << level)]
            r = self.radius
            for _ in range(self.unit):  # the leftmost neighbour is the highest bit of the index
                row = [(self.rule >> sum(row[i + d] << (r - d) for d in range(-r, r + 1))) & 1
                       for i in range(r, len(row) - r)]
            out = self._build(sum(bit << i for i, bit in enumerate(row)), level - 1)
        else:
            west, east = left[piece], right[piece]
            middle = join(right[west], left[east])
            if 8 * reach <= 1 << level:
                # Room to spare: halve the space and keep the recipe.
                p, q, r = self.run(recipe, west), self.run(recipe, middle), self.run(recipe, east)
                out = join(join(right[p], left[q]), join(right[q], left[r]))
            else:
                # No room: halve the time too. First part on three halves,
                # second part on the two halves made from the results.
                first, second = recipe.first, recipe.second
                p, q, r = self.run(first, west), self.run(first, middle), self.run(first, east)
                out = join(self.run(second, join(p, q)), self.run(second, join(q, r)))
        recipe.table[piece] = out
        self.filled += 1
        if self.budget is not None and self.filled > self.budget:
            raise OverBudget
        return out

    # --- states: a piece plus the position of its first cell ---

    def advance(self, recipe, state):
        piece, origin = state
        size = 1 << self.level[piece]
        need = 2 * size + 4 * self.reach * recipe.steps
        while size < need:  # pad with white so the pattern cannot reach the edge
            margin = self.white(self.level[piece] - 1)
            piece = self.join(self.join(margin, self.left[piece]), self.join(self.right[piece], margin))
            origin -= size // 2
            size *= 2
        return self._trim(self.run(recipe, piece), origin + size // 4)

    def _trim(self, piece, origin):
        while self.level[piece] > 2:
            west, east = self.left[piece], self.right[piece]
            if self.count[self.left[west]] or self.count[self.right[east]]:
                break
            origin += 1 << (self.level[piece] - 2)
            piece = self.join(self.right[west], self.left[east])
        return piece, origin

    def encode(self, state):
        offset, bits = state
        level = max(2, (max(bits.bit_length(), 1) - 1).bit_length())
        return self._trim(self._build(bits, level), offset)

    def _build(self, bits, level):
        if bits == 0:
            return self.white(level)
        if level == 0:
            return 1
        half = 1 << (level - 1)
        return self.join(self._build(bits & ((1 << half) - 1), level - 1),
                         self._build(bits >> half, level - 1))

    def decode(self, state):
        piece, origin = state
        bits = self._bits(piece)
        if not bits:
            return (0, 0)
        shift = (bits & -bits).bit_length() - 1
        return (origin + shift, bits >> shift)

    def _bits(self, piece):
        if self.count[piece] == 0:
            return 0
        if self.level[piece] == 0:
            return 1
        half = 1 << (self.level[piece] - 1)
        return self._bits(self.left[piece]) | (self._bits(self.right[piece]) << half)

    def black(self, state):
        """Number of black cells."""
        return self.count[state[0]]

    def fingerprint(self, state):
        """A number that pins down exactly which cells are black (up to a
        one-in-2**61 chance of a clash), without listing them."""
        piece, origin = state
        return pow(_BASE, origin % (_PRIME - 1), _PRIME) * self.print[piece] % _PRIME


def reuse_line(rule: int, budget: int | None = None,
               radius: int = 1) -> tuple[Translation, Translation, Reuse]:
    """Two translations sharing one cache: one predicts the whole row, one
    predicts only how many cells differ from the background (for jumps whose
    row would be too long to write out)."""
    encode, period, lead = None, 1, 0
    all_black = (1 << (2 * radius + 1)) - 1  # the neighbourhood with every cell black
    if not rule & 1:                   # the background stays white
        world = Reuse(rule, budget, radius=radius)
    elif not (rule >> all_black) & 1:  # the background blinks
        world = Reuse(rule, budget, unit=2, radius=radius)
        period = 2
    else:                              # the background turns black: one real step, then the twin
        twin = sum((1 - ((rule >> (all_black - index)) & 1)) << index for index in range(all_black + 1))
        world = Reuse(twin, budget, radius=radius)
        # one step of the rule with the output colours swapped
        first = Reuse(rule ^ ((1 << (all_black + 1)) - 1), radius=radius)
        lead = 1

        def encode(state):
            return world.encode(first.decode(first.advance(first.base, first.encode(state))))

    encode = encode or world.encode
    pocket = Pocket(world.base, world.then, world.advance, lambda recipe: len(recipe.table))
    work = lambda: world.filled  # noqa: E731
    whole = Translation(pocket, encode, world.decode, lead, period=period, lead=lead, work=work)
    counting = Translation(pocket, encode, world.black, lead, period=period, lead=lead, work=work,
                           feature=lambda state: state[1].bit_count(),
                           note="reuse: predicts how many cells differ from the background")
    return whole, counting, world
