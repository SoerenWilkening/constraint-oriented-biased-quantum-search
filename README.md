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
x = m.add_vars(n) # n variables

m.add_constraint(sum(x[i] * z[i] for i in x) <= Z)
m.set_objective(sum(x[i] * p[i] for i in x), MAXIMIZE)
m.close()

m.set_param('branching_bias', n / 4) # upper bound of 1000 oracle
m.set_param('M', 1000) # upper bound of 1000 oracle applications
m.solve()

del m
```

## Training Guide

The `cbqs.ml` subpackage provides ML-based branching weight prediction and adaptive solving. Instead of manually choosing `branching_bias`, you can train a model to predict per-variable branching weights from problem structure.

### Installation

Install with the ML optional dependency (requires scikit-learn):
```bash
pip install -e ".[ml]"
```

### Offline Training (WeightPredictor)

Train a weight predictor offline by solving a set of small instances with diverse random weight strategies, then learning which weights work best for which problem structures.

```python
import numpy as np
from cbqs import Model, MAXIMIZE
from cbqs.ml import WeightPredictor, collect_training_data

# 1. Create training instances (small knapsack problems)
train_models = []
rng = np.random.RandomState(0)
for _ in range(5):
    n = 8
    p = rng.randint(1, 20, size=n).tolist()
    z = rng.randint(1, 15, size=n).tolist()
    Z = int(sum(z) * 0.5)

    m = Model()
    x = m.add_vars(n)
    m.add_constraint(sum(x[i] * z[i] for i in x) <= Z)
    m.set_objective(sum(x[i] * p[i] for i in x), MAXIMIZE)
    m.close()
    train_models.append(m)

# 2. Collect training data (tries n_strategies random weight vectors per model)
training_pairs = collect_training_data(
    train_models, n_strategies=10, stopping_time=5
)

# 3. Fit the predictor
predictor = WeightPredictor(random_state=42)
predictor.fit(training_pairs)

# 4. Predict weights for a new instance
m_new = Model()
x = m_new.add_vars(10)
m_new.add_constraint(sum(x[i] * 3 for i in x) <= 15)
m_new.set_objective(sum(x[i] * (i + 1) for i in x), MAXIMIZE)
m_new.close()

weights = predictor.predict(m_new)

# 5. Solve with predicted weights
m_new.set_param('branching_weights', weights)
m_new.set_param('M', 1000)
m_new.solve()

# 6. Save/load for reuse
predictor.save('predictor.joblib')
loaded = WeightPredictor.load('predictor.joblib')
```

### Online Adaptation (adaptive_solve)

`adaptive_solve` runs multiple solve rounds on a single instance, refining branching weights between rounds using Exponential Moving Average (EMA) updates driven by a combined reward signal of objective improvement and feasibility.

```python
from cbqs import Model, MAXIMIZE
from cbqs.ml import adaptive_solve

m = Model()
x = m.add_vars(8)
m.add_constraint(sum(x[i] * 2 for i in x) <= 8)
m.set_objective(sum(x[i] * (i + 1) for i in x), MAXIMIZE)
m.close()

# Basic usage: 5 rounds of adaptive solving
result = adaptive_solve(m, n_rounds=5, stopping_time=5, seed=42)

print(result.best_result.objective)  # Best objective found
print(result.best_weights)           # Weights that produced it
print(len(result.history))           # Per-round metrics
```

Key parameters:
- `n_rounds` -- number of solve rounds (default 5)
- `ema_alpha` -- EMA smoothing factor; higher values weight the reward signal more (default 0.3)
- `initial_weights` -- starting weights: `None` for uniform, an `ndarray`, or a fitted `WeightPredictor`

Chain offline prediction with online refinement by passing a trained predictor as starting weights:

```python
from cbqs.ml import WeightPredictor, adaptive_solve

predictor = WeightPredictor.load('predictor.joblib')

# Start from predicted weights, then refine online
result = adaptive_solve(
    m, n_rounds=5, stopping_time=5, seed=42,
    initial_weights=predictor
)
```

### Evaluation

Compare weight strategies side by side using `evaluate_weights`. It reports mean objective, feasibility rate, convergence time, and speedup relative to uniform weights.

```python
from cbqs.ml import evaluate_weights

strategies = {
    'predicted': lambda m: predictor.predict(m),
}

# evaluate_weights automatically adds a 'uniform' baseline
results = evaluate_weights(test_models, strategies, stopping_time=5)

# Output table columns:
# - Mean Objective: average objective value across test models
# - Feasibility Rate: fraction of feasible solutions found
# - Time-to-Best: average seconds to reach best objective
# - Speedup vs Uniform: ratio of uniform time-to-best / strategy time-to-best
```

### Transfer Learning

Train on small instances and evaluate on larger ones with a single call using `validate_transfer`. This tests whether structural patterns learned from small problems generalize to larger ones.

```python
import numpy as np
from cbqs import Model, MAXIMIZE
from cbqs.ml import validate_transfer

# Small training instances (e.g. n=8)
rng = np.random.RandomState(0)
small_models = []
for _ in range(5):
    n = 8
    m = Model()
    x = m.add_vars(n)
    m.add_constraint(sum(x[i] * rng.randint(1, 10) for i in x) <= n * 3)
    m.set_objective(sum(x[i] * rng.randint(1, 20) for i in x), MAXIMIZE)
    m.close()
    small_models.append(m)

# Larger test instances (e.g. n=16)
large_models = []
for _ in range(3):
    n = 16
    m = Model()
    x = m.add_vars(n)
    m.add_constraint(sum(x[i] * rng.randint(1, 10) for i in x) <= n * 3)
    m.set_objective(sum(x[i] * rng.randint(1, 20) for i in x), MAXIMIZE)
    m.close()
    large_models.append(m)

# Train on small, evaluate on large
results, predictor = validate_transfer(
    small_models, large_models, random_state=42
)

# Save the transfer-trained predictor for reuse
predictor.save('transfer_predictor.joblib')
```

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
