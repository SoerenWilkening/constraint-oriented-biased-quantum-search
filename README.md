# Source code of Constraint-oriented biased quantum search

Code is used to generate the data in https://github.com/SoerenWilkening/CBQS-benchmarks

Currently the code does not utilize the cicuit generator backend, but the dependency is already included.
After cloning this repository, clone the circuit backend via
```bash
git clone --recurse-submodules https://github.com/SoerenWilkening/speed-oriented-quantum-circuit-backend
```
Afterwards run 
```bash
python setup.py build_ext --inplace 
```
or 
```bash
pip install -e .
```
to compile the code.

Example:
Running the code for a small knapsack problem assuming p and z are lists of n integers
```python
from cbqs import Model, MAXIMIZE

m = Model()
x = m.add_variables(n) # n variables

m.add_constraint(sum(x[i] * z[i] for i in x) <= Z)
m.set_objective(sum(x[i] * p[i] for i in x), MAXIMIZE)
m.close()

m.set_param('branching_bias', n / 4) # upper bound of 1000 oracle
m.set_param('M', 1000) # upper bound of 1000 oracle applications
result = m.solve()

del m
```

## Evaluating a smaller portfolio without re-running

`solve()` runs a portfolio of `num_workers` independent solvers (default 12).
Every worker keeps its own improvement stream, and `result.history` is the
best-of-portfolio running-max merged from those streams. The raw streams are
kept in `result.worker_histories`:

```python
m.set_param('num_workers', 12)
result = m.solve()

result.history            # [(value, oracle), ...]  best-of-all-workers curve
result.worker_histories   # one list per worker, index == worker id
                          # [[(value, oracle, elapsed_s), ...], ...]
```

Each entry is the worker's own incumbent `value`, its own cumulative oracle
count, and the wall-clock seconds since `solve()` started. Workers never read
each other's incumbents (each is seeded from `(seed, worker_id)`), so the curve
that any subset of workers would have produced on its own is just the
running-max over that subset's streams. To see how the run would have gone with
`k` workers instead of 12:

```python
def portfolio_curve(streams, axis=1):
    """Best-of-portfolio curve over the given worker streams.

    axis=1 orders by oracle count, axis=2 by elapsed seconds (MAXIMIZE shown;
    flip the comparison for MINIMIZE).
    """
    curve, best = [], None
    for entry in sorted((e for s in streams for e in s), key=lambda e: e[axis]):
        if best is None or entry[0] > best:
            best = entry[0]
            curve.append((entry[0], entry[axis]))
    return curve

k = 4
curve_k = portfolio_curve(result.worker_histories[:k])          # first k workers
# or average over many k-subsets for the expected k-worker curve:
import itertools, random
subsets = random.sample(list(itertools.combinations(range(12), k)), 50)
curves  = [portfolio_curve([result.worker_histories[i] for i in sub]) for sub in subsets]
```

`portfolio_curve(result.worker_histories)` reproduces `result.history` exactly.
Note that on the oracle axis this replay is exact, while on the wall-clock
axis (`axis=2`) it is conservative: a real `k`-worker run would have had more
CPU per worker than the 12-worker run these streams came from.
`result.to_dict()` includes `worker_histories`, so runs can be saved and
analysed later. Set `m.set_param('track_history', False)` to disable the
tracking (both fields are then empty).

Cite as:
```bibtex
@misc{wilkening2025constraintorientedbiasedquantumsearch,
      title={Constraint-oriented biased quantum search for linear constrained combinatorial optimization problems}, 
      author={Sören Wilkening and Timo Ziegler and Maximilian Hess},
      year={2025},
      eprint={2512.05205},
      archivePrefix={arXiv},
      primaryClass={quant-ph},
      url={https://arxiv.org/abs/2512.05205}, 
}
```
