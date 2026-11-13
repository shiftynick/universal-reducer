# universal-reducer

An experiment on a question about Stephen Wolfram's computational irreducibility: can every pocket of reducibility, from any system, be translated into one common form, so that a single fixed algorithm performs the shortcut?

The short answer is no, not in the strongest sense. The question, the method, the results and their limits are written up in [FINDINGS.md](FINDINGS.md).

## Running it

Needs Python 3.10 or later and nothing else.

- `python3 run.py` checks every result against step-by-step running, then prints the scoreboard and a census of all 256 elementary cellular automaton rules. About 20 seconds.
- `python3 wider.py` repeats the census on a larger family of rules. About six minutes.
