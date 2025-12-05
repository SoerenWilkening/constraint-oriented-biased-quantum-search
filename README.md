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
pip install .
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
m.solve(M = 1000) # upper bound of 1000 oracle applications

del m 
```
