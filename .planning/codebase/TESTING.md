# Testing Patterns

**Analysis Date:** 2026-02-04

## Test Framework

**Runner:**
- No test runner configured (pytest, unittest not found in project root)
- CMake includes basic test compilation: `cbqs/src/test.c`
- Manual test execution via compiled C executables or example scripts

**Assertion Library:**
- No assertion library detected
- C test code uses implicit assertions (exit codes, printf output verification)
- Python examples use basic print output for validation

**Run Commands:**
```bash
cmake . && make                    # Build test executable
./constraint-oriented-biased-quantum-search  # Run C-level tests
python others/bounded_integers/test.py       # Run Python example/test
```

**Build Configuration:**
- CMakeLists.txt defines test executable at `/Users/sorenwilkening/Desktop/constraint-oriented-biased-quantum-search/CMakeLists.txt`
- Executable: `constraint-oriented-biased-quantum-search` (line 8)
- Uses compiled C sources directly

## Test File Organization

**Location:**
- Manual C test: `cbqs/src/test.c`
- Python example/test scripts in `others/` subdirectories:
  - `others/bounded_integers/test.py`
  - `others/2DVBP/run_local.py`
  - `others/MaxClique/run_quantum.py`
- No dedicated test directory structure (no `tests/`, `test_*.py` files in main cbqs/)

**Naming:**
- C test file: `test.c` (simple name)
- Python scripts: `test.py`, `run_*.py` (descriptive names)
- No standard test discovery pattern (test_*.py, *_test.py not used in cbqs/)

**Structure:**
```
constraint-oriented-biased-quantum-search/
├── cbqs/
│   ├── src/
│   │   └── test.c           # Single C test file
│   └── [modules]            # No separate test modules
└── others/
    ├── bounded_integers/
    │   └── test.py          # Example/benchmark script
    ├── 2DVBP/
    │   └── run_local.py     # Example/benchmark script
    └── MaxClique/
        └── run_quantum.py   # Example/benchmark script
```

## Test Structure

**Suite Organization:**

C test format from `test.c` (`/Users/sorenwilkening/Desktop/constraint-oriented-biased-quantum-search/cbqs/src/test.c`):
```c
int main(){
	srand(clock());

	int arr[5];
	for (int i = 0; i < 5; ++i) arr[i] = 0;
	state_t *sol = init_state(0, arr, 5);
	sol->tot_profit = INT64_MAX;
	sol->feasible = 0;

	// generate simple 0-1 knapsack instance
	expression_t *expr = init_expression();
	add_variable(expr, 0);
	multiply_constant(expr, 2);
	// ... setup continues

	// Execute test
	preprocessing(5, &obj);
	preprocessing(5, &con);

	size_t total_oracle_application = 0;
	quantum_local_search(&obj, &con, sol, 2, &total_oracle_application);
	printf("%zu ", total_oracle_application);
	print_state(sol);
	printf("\n");

	free_state(sol, 1);
    return 0;
}
```

**Patterns:**
- Setup: Manual memory allocation and initialization
- Execution: Direct function calls
- Verification: printf output inspection (no assertions)
- Teardown: Manual memory cleanup with free() calls

**Python Test Pattern from test.py** (`/Users/sorenwilkening/Desktop/constraint-oriented-biased-quantum-search/others/bounded_integers/test.py` lines 64-116):
```python
def solve(index, k, n):
	print(n)
	s = int(time())
	set_seed(s)
	dat = np.load(f"instances/{n},{bound}_{index}.npz")
	weights = dat["weights"]
	profits = dat["profits"]
	Z = bound ** 2 * sum(weights) // 8
	t1 = time()
	m = Model()

	x1 = {}
	x1_2 = {}
	x1_fixed = {}
	x1_fixed2 = {}
	for i in range(n):
		x1[i] = m.add_variable(i, bound = bound)
		x1_2[i] = copy.copy(x1[i])
		x1_fixed[i] = copy.copy(x1[i])
		x1_fixed2[i] = copy.copy(x1[i])

	if not os.path.exists(path):
		file = open(path, "w")
		file.write("size,index,bound,obj,time,oracles,k,method\n")
		file.close()

	counter = [0]
	def callback(a, b, c, d, counter):
		print(f"{n},{index},{bound},{-a},{c:.3f},{int(22.5 * 2 * counter[0] * n ** (k / 2))},{k},local-search")

	# Build model
	exp1 = sum(x1[i] * x1_2[i] * int(weights[i]) for i in x1) <= int(Z)
	exp2 = sum(x1_fixed[i] * x1_fixed2[j] * int(profits[i, j]) for i in x1 for j in x1 if i <= j)
	m.add_constraint(exp1)
	m.set_objective(exp2, sense = MAXIMIZE)
	del exp1, exp2
	m.close()
	m.general_greedy()
	m.local_search(3, max_worse_acceptances = 10, stop_time = 246, callback = callback2, stopping_condition = 1)
	del m, x1, x1_2, x1_fixed
```

**Organization:**
- Setup phase: Create Model instance, add variables and constraints
- Execution phase: Call solve/local_search methods with callbacks
- Verification: Print output to stdout (captured and compared)
- Cleanup: Delete model and variables

## Mocking

**Framework:** None detected

**Patterns:**
- No test mocks or stubs found in codebase
- Callbacks used for verification during execution: `callback(a, b, c, d, counter)`
- Example callback from test.py:
```python
def callback(a, b, c, d, counter):
	print(f"{n},{index},{bound},{-a},{c:.3f},{int(22.5 * 2 * counter[0] * n ** (k / 2))},{k},local-search")

def callback2():
	print(f"{n},{index},{m.objective_value},{m.runtime},{m.oracle_calls},local-search")
```

**What to Mock:**
- External optimizers (Gurobi) - already abstracted in StateGenerator.py via gurobipy module
- File I/O for large datasets - examples handle directly with np.load()

**What NOT to Mock:**
- Core C functions that perform constraint evaluation
- State management and memory allocation
- Constraint and objective evaluation (are the focus of tests)

## Fixtures and Factories

**Test Data:**

Example data generation pattern from test.py (`/Users/sorenwilkening/Desktop/constraint-oriented-biased-quantum-search/others/bounded_integers/test.py` lines 21-39):
```python
def generate(n):
	for i in range(30):
		weights = np.array([randint(1, 10000) for _ in range(n // 2)] + [randint(1, 100) for _ in range(n // 2)])
		profits = np.array([[randint(1, 10000) for _ in range(n // 2)] + [randint(1, 100) for _ in range(n // 2)] for _ in range(n)])
		profits = (profits + profits.T) // 2

		# Compute efficiencies
		efficiencies = [sum(profits[i]) / weights[i] for i in range(n)]

		# Get sorted indices (descending by efficiency)
		sorting = np.array(sorted(range(n), key=lambda i: efficiencies[i], reverse=True))

		# Reorder weights
		weights = weights[sorting]

		# Reorder profits (rows and columns)
		profits = profits[np.ix_(sorting, sorting)]

		np.savez(f"instances/{n},{bound}_{i}.npz", weights=weights, profits=profits)
```

**Location:**
- Test data stored in `.npz` files (NumPy compressed arrays)
- Generated via `generate()` function in test scripts
- Located in `others/bounded_integers/instances/` directory
- Format: `{n},{bound}_{index}.npz`

**Model Construction Pattern:**
Example from test.py shows variable and constraint factory approach:
```python
m = Model()

x1 = {}
for i in range(n):
	x1[i] = m.add_variable(i, bound = bound)
	x1_2[i] = copy.copy(x1[i])
	x1_fixed[i] = copy.copy(x1[i])
	x1_fixed2[i] = copy.copy(x1[i])

exp1 = sum(x1[i] * x1_2[i] * int(weights[i]) for i in x1) <= int(Z)
exp2 = sum(x1_fixed[i] * x1_fixed2[j] * int(profits[i, j]) for i in x1 for j in x1 if i <= j)
m.add_constraint(exp1)
m.set_objective(exp2, sense = MAXIMIZE)
```

## Coverage

**Requirements:** None enforced

**View Coverage:**
- No coverage tool integrated
- Test results verified via:
  - stdout comparison (expected values printed)
  - Oracle call counts
  - Solution feasibility flags

## Test Types

**Unit Tests:**
- Scope: Individual C functions (constraint evaluation, state operations)
- Approach: Direct function calls in test.c with manual verification
- Example from test.c:
```c
quantum_local_search(&obj, &con, sol, 2, &total_oracle_application);
printf("%zu ", total_oracle_application);  // Manual verification
print_state(sol);
```

**Integration Tests:**
- Scope: Full model solving pipeline (Model creation → constraint compilation → search)
- Approach: Python scripts in `others/` directories
- Patterns: Model initialization, constraint/objective setup, solve execution
- Example from test.py: Full workflow from data loading to solve execution

**Benchmarking Tests:**
- Scope: Algorithm performance and solution quality comparison
- Approach: Comparison against Gurobi solver
- Output: CSV-formatted results for analysis
- Example from test.py:
```python
def solve_gurobi(index, n):
	# ... Gurobi model setup ...
	m.optimize(callback = callback_gur)
	res = m.ObjVal
	print(res, m.Runtime)
```

**E2E Tests:**
- Framework: Not formally structured
- Approach: Scripts in `others/` subdirectories that test complete problem instances
- Location: `others/bounded_integers/test.py`, `others/2DVBP/run_local.py`, `others/MaxClique/run_quantum.py`

## Common Patterns

**Async Testing:**
- Not applicable (no async operations in codebase)
- Multi-worker testing handled via `Parallel(n_jobs = num_workers, backend = "threading")` in Model.solve()

**Error Testing:**
- Type checking with assertions:
```python
assert results in ["min", "average"]
assert stopping_condition in [STOPATFIRST, STOPATBEST]
```

- Invalid type detection:
```python
if isinstance(other, float): raise TypeError("Not allowed type!")
```

- Memory leak prevention via RAII patterns in C:
```c
if (mod->manual_bias != NULL) free(mod->manual_bias);
if (mod->initial_state != NULL) free_state(mod->initial_state, 1);
```

**State Verification Pattern:**
From test.c, verification happens via print output:
```c
printf("%zu ", total_oracle_application);  // Check oracle calls
print_state(sol);                            // Verify final state
printf("\n");
```

**Output Verification:**
CSV-based result collection from test.py:
```python
def callback(a, b, c, d, counter):
	print(f"{n},{index},{bound},{-a},{c:.3f},{int(22.5 * 2 * counter[0] * n ** (k / 2))},{k},local-search")
	# Results can be piped to file or compared against baseline
```

## Setup and Teardown

**Cython Cleanup Patterns:**

From state.pyx (`/Users/sorenwilkening/Desktop/constraint-oriented-biased-quantum-search/cbqs/state.pyx`):
```python
def __dealloc__(self) -> None:
	if self.state is not NULL:
		free_state(self.state, self.num_states)
```

From Model.pyx:
```python
def __del__(self):
	free_model(self.mod)
	if self.final_state is not None: self.final_state = None
	if self.initial_state is not None: self.initial_state = None
	self.objective = None
	self.constraint = None
	self.circuit = None
```

**Python Cleanup:**
From test.py:
```python
del exp1, exp2
m.close()              # Compile constraints before solve
m.general_greedy()     # Initialize state
m.local_search(...)    # Run algorithm
del m, x1, x1_2, x1_fixed  # Manual cleanup
```

---

*Testing analysis: 2026-02-04*
