
def generate_assembly_ilp(n, constraints, obj, lp_factor, lp_opt, num_integers, direction = ""):
	# get the break Item: up to this point, every assignment is feasible
	Zs = [i[-1] for i in constraints]

	for break_item in range(n):
		if constraints[0][break_item][0] <= Zs[0]:
			Zs[0] -= constraints[0][break_item][0]
		else:
			break

	# define all the required registers
	asm_file = """data"""
	for i in range(n):
		asm_file += f"""
	QBOOL X{i}"""
	asm_file +=f"""
	QINT C1
	QINT P
	QBOOL BP 
	
start"""

	for item in range(n):
	# for item in range(1):
		S_plus = [[constraints.index(i), *[j[0] for j in i[:-1] if j[1] == item and j[0] > 0]] for i in constraints if [j for j in i[:-1] if j[1] == item and j[0] > 0] != []]
		# S_minus = [[constraints.index(i), *[j[0] for j in i[:-1] if j[1] == item and j[0] < 0]] for i in constraints if [j for j in i[:-1] if j[1] == item and j[0] < 0] != []]

		if item < break_item:
			# up to break item, every assignment is true
			asm_file += f"""
	branch X{item} 0
	cqsub C1 {int(S_plus[0][1])} X{item}
				"""
		else:
			asm_file += f"""
	qsub C1 {int(S_plus[0][1])}
	qtstbit BP C1 0
	cqnot X{item} BP         // simulates hadamard
	qnot X{item}
	cqadd C1 {int(S_plus[0][1])} X{item}
	qnot X{item}
	qtstbit BP C1 0
	"""

	for i in obj[0][:-1]:
		if len(i) == 2:
			asm_file += f"""
		cqadd P {int(i[0])} X{int(i[1])}
		"""
		if len(i) == 3:
			if i[1] > i[2]:
				asm_file += f"""
	qqand BP X{int(i[1])} X{int(i[2])} 
	cqadd P {2 * int(i[0])} BP
	qqand BP X{int(i[1])} X{int(i[2])} """
			if i[1] == i[2]:
				asm_file += f"""
	qqand BP X{int(i[1])} X{int(i[2])} 
	cqadd P {int(i[0])} BP
	qqand BP X{int(i[1])} X{int(i[2])} """

	file = open(f"{direction}/build/circ.pqsm", "w")
	file.write(asm_file)
	file.close()

	return