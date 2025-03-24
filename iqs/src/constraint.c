#include "constraint.h"

constraint_list_t init_con_list(){
    constraint_list_t con_list;
    con_list.num_constraints = 0;
    con_list.constraints = malloc(sizeof(constraint_t));
    con_list.constraints->sense = MAXIMIZE;
    return con_list;
}

constraint_t init_con(){
    constraint_t con;
    con.num_literals = 0;
    con.sense = -2;
    con.rhs = 0;
    con.first_non_closed = 0;
    con.rhs_adapted = 0;
    con.literals = malloc(0);
    return con;
}

lit_t init_literal(int64_t *literal, int len_literal){
    lit_t lit;
    lit.variables = calloc(len_literal - 1, sizeof(int64_t));
    lit.factor = literal[0];
    for (int i = 0; i < len_literal - 1; i++) lit.variables[i] = literal[i + 1];
    lit.len_literal = len_literal;

    return lit;
}

void add_constraint(constraint_list_t *con_list, constraint_t *con){
    con_list->num_constraints += 1;
    con_list->constraints = realloc(con_list->constraints, con_list->num_constraints * sizeof(constraint_t));
    con_list->constraints[con_list->num_constraints - 1] = *con;
}

void add_literal(constraint_t *con, int64_t *literal, int len_literal){
    con->literals = realloc(con->literals, (con->num_literals + 1) * sizeof(lit_t));
    con->literals[con->num_literals] = init_literal(literal, len_literal);
    con->num_literals++;
}

void add_sense(constraint_t *con, int sense){
    con->sense = sense;
}

void add_rhs(constraint_t *con, int64_t rhs){
    con->rhs += rhs;
    con->rhs_adapted += rhs;
    con->first_non_closed = 0;
}

void reset_constraint_list(constraint_list_t *cons){
    for(int i = 0; i < cons->num_constraints; i++){
        cons->constraints[i].rhs_adapted = cons->constraints[i].rhs;
        cons->constraints[i].first_non_closed = 0;
    }
}

void print_constraints(constraint_list_t *cons){
    for (int i = 0; i < cons->num_constraints; i++){
        for (int j = 0; j < cons->constraints[i].num_literals; j++){
            printf("[");
            printf("%lld ", cons->constraints[i].literals[j].factor);
            for (int k = 0; k < cons->constraints[i].literals[j].len_literal - 1; k++){
                printf("%d ", cons->constraints[i].literals[j].variables[k]);
            }
            printf("] ");
        }
        if (cons->constraints[i].sense == LOWER || cons->constraints[i].sense == MAXIMIZE) printf("< ");
        else if (cons->constraints[i].sense == EQUAL) printf("= ");
        else printf("> ");
        printf("%lld ", cons->constraints[i].rhs_adapted);
        printf("%lld\n", cons->constraints[i].rhs);
    }
}


int eval_constraint(constraint_t *con, int *assignment, int assigned){
    int64_t total = 0;
    int open_var = con->num_literals;

    for(int i = 0; i < con->num_literals; i++){
        lit_t *lit = &con->literals[i];

        // is it a constant expression
        if (lit->len_literal == 1) total = total + con->literals[i].factor;
        // is it a linear expression?
        else if (lit->len_literal == 2){
            // is the variable already assigned?
            if (lit->variables[0] < assigned){
                // is it a negative coefficient?
                if (lit->factor < 0){
                    total = total - lit->factor * (1 - assignment[lit->variables[0]]);
                }
                else{
                    total = total + lit->factor * assignment[lit->variables[0]];
                }
                // the variable is not "open" anymore
                open_var--;
            }
        }
        // is it a quadratic expression?
        else{
            // are both variables assigned already?
            if ((lit->variables[0] < assigned) && (lit->variables[1] < assigned) ){
                // is it a negative coefficient?
                if (lit->factor < 0){
                    total = total - lit->factor * \
                        (1 - assignment[lit->variables[0]] * assignment[lit->variables[1]]);
                }
                else{
                    total += lit->factor * \
                        assignment[lit->variables[0]] * assignment[con->literals[i].variables[1]];
                }
                open_var = open_var - (lit->variables[0] < assigned) - (lit->variables[1] < assigned);
            }
        }
    }
    if (con->sense == EQUAL){
        if(open_var > 0) return total <= con->rhs;
        else return total == con->rhs;
    }
    else if (con->sense == LOWER) return total <= con->rhs;
    else return total >= con->rhs;
}

int quantum_feasibility(constraint_list_t *con, int *assignment, int assigned){
    if (assigned == 0) return true;
    for (int i = 0; i < con->num_constraints; i++){
        if (!eval_constraint(&con->constraints[i], assignment, assigned)){
            return false;
        }
    }
    return true;
}


int eval_constraint2(constraint_t *con, state_t *assignment, int assigned, int close){
    double total = 0;
    int open_lit = con->num_literals - con->first_non_closed;
    int first_non_closed = con->first_non_closed;

    for(int i = first_non_closed; i < con->num_literals; i++){
        lit_t *lit = &con->literals[i];
        // is it a constant expression
        if (lit->len_literal == 1) total = total + lit->factor;
        // is it a linear expression?
        else if (lit->len_literal == 2){
            int ass = sw_tstbit(assignment->vector, lit->variables[0]);
            // is the variable already assigned?
            if (lit->variables[0] < assigned){
                // is it a negative coefficient?
                if (lit->factor < 0){
                    total = total - lit->factor * (1 - ass);
                }
                else{
                    total = total + lit->factor * ass;
                }
                // the variable is not "open" anymore
                if(close) con->first_non_closed = i + 1;
                open_lit--;
            }
            if (lit->variables[0] > assigned) break;
        }
        // is it a quadratic expression?
        else{
            // are both variables assigned already?
            if ((lit->variables[0] < assigned) && (lit->variables[1] < assigned) ){
                int ass1 = sw_tstbit(assignment->vector, lit->variables[0]);
                int ass2 = sw_tstbit(assignment->vector, lit->variables[1]);
                // is it a negative coefficient?
                if (lit->factor < 0){
                    total = total - lit->factor * (1 - ass1 * ass2);
                }
                else{
                    total = total + lit->factor * ass1 * ass2;
                }
                if(close) con->first_non_closed = i + 1;
                open_lit--;
            }
            if ((lit->variables[0] > assigned) && (lit->variables[1] > assigned)) break;
        }
    }
    // keep old value for evaluation
    double rhs = con->rhs_adapted;

    // update rhs based on already assigned variables
    if(close) con->rhs_adapted = con->rhs_adapted - total;

    if (con->sense == EQUAL){
        if(open_lit > 0) return total <= rhs;
        else return total == rhs;
    }
    else if (con->sense == LOWER) return total <= rhs;
    else return total >= rhs;
}


int quantum_feasibility2(constraint_list_t *con, state_t *assignment, int assigned, int close){
    if (assigned == 0) return true;
    for (int i = 0; i < con->num_constraints; i++){
        if (!eval_constraint2(&con->constraints[i], assignment, assigned, close)){
            return false;
        }
    }
    return true;
}

int count_satisfyed_constraints(constraint_list_t *con, state_t *assignment, int assigned, int close, int allowed_false){
    if (assigned == 0) return 0;
    int count = 0;
    int false_cons = 0;
    for (int i = 0; i < con->num_constraints; i++){
        if (eval_constraint2(&con->constraints[i], assignment, assigned, close)) count++;
        else{
            false_cons++;
            if (false_cons > allowed_false) return count;
        }
//        count += eval_constraint2(&con->constraints[i], assignment, assigned, close);
    }
    return count;
}

int64_t ObjVal(state_t *state, constraint_list_t *obj){
    int64_t val = 0;
    for (int i = 0; i < obj->constraints->num_literals; i++){
        lit_t *lit = &obj->constraints->literals[i];
        // is it a linear expression?
        if (lit->len_literal == 2){
            int ass = sw_tstbit(state->vector, lit->variables[0]);
            val += lit->factor * ass;
        }
        else{
            int ass1 = sw_tstbit(state->vector, lit->variables[0]);
            int ass2 = sw_tstbit(state->vector, lit->variables[1]);
            val += lit->factor * ass1 * ass2;
        }
    }
    return val;
}

int64_t ChangedObjVal(  constraint_list_t *obj, // objective function
                            state_t *new, // new state
                            int NumChanges, // how many bits were flipped
                            int *ChangedBits, // which bits were flipped
                            int **Indices, // objective term indices involving every item
                            int *NumIndices, // in how many terms every item occours
                            int *Fulfilled, // are terms of objective fulfilled
                            int *ChangedTerms,
                            int *NumChangedTerms
                            ){
    int Count = 0;
    int NTerms = obj->constraints[0].num_literals; // number terms
    int *investigated = calloc(NTerms, sizeof(int)); // was the term evaluated already? (important for quadratic functions)
    // For every changed bit, change, if the respective term changes and adjust the total profit
    for(int ChangeIndex = 0; ChangeIndex < NumChanges; ChangeIndex++){
        int item = ChangedBits[ChangeIndex];
        for(int term = 0; term < NumIndices[item]; term++){
            int literal = Indices[item][term];
            lit_t *lit = &obj->constraints[0].literals[literal];
            if (!investigated[literal]){
                int assign = 1;
                // check every item of respective term
                for (int lits = 0; lits < lit->len_literal - 1; lits++){
                    if (!sw_tstbit(new->vector, lit->variables[lits]))
                        assign = 0;
                }
                if (Fulfilled[literal] && !assign){
                    new->tot_profit -= lit->factor;
                }
                if (!Fulfilled[literal] && assign){
                    new->tot_profit += lit->factor;
                }
                if (assign != Fulfilled[literal]) ChangedTerms[Count++] = literal;
            }
            // to avoid considering the same term multiple times
            investigated[literal] = 1;
        }
    }
    *NumChangedTerms = Count;
    free(investigated);
    return new->tot_profit;
}