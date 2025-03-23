
#include "constraint.h"

constraint_list_t init_con_list(){
    constraint_list_t con_list;
    con_list.num_constraints = 0;
    con_list.constraints = malloc(sizeof(constraint_t));
    con_list.constraints->sense = -1;
    return con_list;
}

constraint_t init_con(){
    constraint_t con;
    con.num_literals = 0;
    con.sense = -2;
    con.rhs = 0;
    con.digits = 0;
    con.first_non_closed = 0;
    con.rhs_adapted = 0;
    con.literals = malloc(0);
    return con;
}

lit_t init_literal(long double *literal, int len_literal){
    lit_t lit;
    lit.literal = calloc(len_literal, sizeof(long double));
    for (int i = 0; i < len_literal; i++) lit.literal[i] = literal[i];
    lit.len_literal = len_literal;

    return lit;
}

void add_constraint(constraint_list_t *con_list, constraint_t *con){
    con_list->num_constraints += 1;
    con_list->constraints = realloc(con_list->constraints, con_list->num_constraints * sizeof(constraint_t));
    con_list->constraints[con_list->num_constraints - 1] = *con;
}

void add_literal(constraint_t *con, long double *literal, int len_literal){
    con->literals = realloc(con->literals, (con->num_literals + 1) * sizeof(lit_t));
    con->literals[con->num_literals] = init_literal(literal, len_literal);
    con->num_literals++;
}

void add_sense(constraint_t *con, int sense){
    con->sense = sense;
}

void add_rhs(constraint_t *con, long double rhs){
    con->rhs += rhs;
    con->rhs_adapted += rhs;
    con->first_non_closed = 0;
}

void add_digits(constraint_t *con, int digits){
    con->digits = digits;
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
            for (int k = 0; k < cons->constraints[i].literals[j].len_literal; k++){
                printf("%Lf ", cons->constraints[i].literals[j].literal[k]);
            }
            printf("] ");
        }
        if (cons->constraints[i].sense == lessequal) printf("< ");
        else if (cons->constraints[i].sense == equal) printf("= ");
        else printf("> ");
        printf("%Lf ", cons->constraints[i].rhs_adapted);
        printf("%d ", cons->constraints[i].digits);
        printf("%Lf\n", cons->constraints[i].rhs);
    }
}


int eval_constraint(constraint_t *con, int *assignment, int assigned){
    long double total = 0;
    int open_var = con->num_literals;
    for(int i = 0; i < con->num_literals; i++){
        // is it a constant expression
        if (con->literals[i].len_literal == 1) total = total + con->literals[i].literal[0];
        // is it a linear expression?
        else if (con->literals[i].len_literal == 2){
            // is the variable already assigned?
            if (con->literals[i].literal[1] < assigned){
                // is it a negative coefficient?
                if (con->literals[i].literal[0] < 0){
                    total = total - con->literals[i].literal[0] * (1 - assignment[(int)con->literals[i].literal[1]]);
                }
                else{
                    total = total + con->literals[i].literal[0] * assignment[(int)con->literals[i].literal[1]];
                }
                // the variable is not "open" anymore
                open_var--;
            }
        }
        // is it a quadratic expression?
        else{
            // are both variables assigned already?
            if ((con->literals[i].literal[1] < assigned) && (con->literals[i].literal[2] < assigned) ){
                // is it a negative coefficient?
                if (con->literals[i].literal[0] < 0){
                    total = total - con->literals[i].literal[0] * \
                        (1 - assignment[(int)con->literals[i].literal[1]] * assignment[(int)con->literals[i].literal[2]]);
                }
                else{
                    total = total + con->literals[i].literal[0] * \
                        assignment[(int)con->literals[i].literal[1]] * assignment[(int)con->literals[i].literal[2]];
                }
                open_var = open_var - (con->literals[i].literal[1] < assigned) - (con->literals[i].literal[2] < assigned);
            }
        }
    }
    if (con->sense == equal){
        if(open_var > 0) return total <= con->rhs;
        else return total == con->rhs;
    }
    else if (con->sense == lessequal) return total <= con->rhs;
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
        // is it a constant expression
        if (con->literals[i].len_literal == 1) total = total + con->literals[i].literal[0];
        // is it a linear expression?
        else if (con->literals[i].len_literal == 2){
            int ass = sw_tstbit(assignment->vector, (int)con->literals[i].literal[1]);
            // is the variable already assigned?
            if (con->literals[i].literal[1] < assigned){
                // is it a negative coefficient?
                if (con->literals[i].literal[0] < 0){
                    total = total - con->literals[i].literal[0] * (1 - ass);
                }
                else{
                    total = total + con->literals[i].literal[0] * ass;
                }
                // the variable is not "open" anymore
                if(close) con->first_non_closed = i + 1;
                open_lit--;
            }
            if (con->literals[i].literal[1] > assigned) break;
        }
        // is it a quadratic expression?
        else{
            // are both variables assigned already?
            if ((con->literals[i].literal[1] < assigned) && (con->literals[i].literal[2] < assigned) ){
                int ass1 = sw_tstbit(assignment->vector, (int)con->literals[i].literal[1]);
                int ass2 = sw_tstbit(assignment->vector, (int)con->literals[i].literal[2]);
                // is it a negative coefficient?
                if (con->literals[i].literal[0] < 0){
                    total = total - con->literals[i].literal[0] * (1 - ass1 * ass2);
                }
                else{
                    total = total + con->literals[i].literal[0] * ass1 * ass2;
                }
                if(close) con->first_non_closed = i + 1;
                open_lit--;
            }
            if ((con->literals[i].literal[1] > assigned) && (con->literals[i].literal[2] > assigned)) break;
        }
    }
    // keep old value for evaluation
    double rhs = con->rhs_adapted;

    // update rhs based on already assigned variables
    if(close) con->rhs_adapted = con->rhs_adapted - total;

    if (con->sense == equal){
        if(open_lit > 0) return total <= rhs;
        else return total == rhs;
    }
    else if (con->sense == lessequal) return total <= rhs;
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

long double ObjVal(const state_t *state, const constraint_list_t *obj){
    long double val = 0;
    for (int i = 0; i < obj->constraints->num_literals; i++){
        // is it a linear expression?
        if (obj->constraints->literals[i].len_literal == 2){
            int ass = sw_tstbit(state->vector, (int) obj->constraints->literals[i].literal[1]);
            val += obj->constraints->literals[i].literal[0] * ass;
        }
        else{
            int ass1 = sw_tstbit(state->vector, (int) obj->constraints->literals[i].literal[1]);
            int ass2 = sw_tstbit(state->vector, (int) obj->constraints->literals[i].literal[2]);
            val += obj->constraints->literals[i].literal[0] * ass1 * ass2;
        }
    }
    return val;
}

long double ChangedObjVal(  constraint_list_t *obj, // objective function
                            state_t *new, // new state
                            int NumChanges, // how many bits were flipped
                            const int *ChangedBits, // which bits were flipped
                            const int **Indices, // objective term indices involving every item
                            const int *NumIndices, // in how many terms every item occours
                            const int *Fulfilled, // are terms of objective fulfilled
                            int *ChangedTerms,
                            int *NumChangedTerms
                            ){
    int Count = 0;
    int NTerms = obj->constraints[0].num_literals; // number terms
    int *investigated = calloc(NTerms, sizeof(int)); // was the term evaluated already? (important for quadratic functions)
    // For every changed bit, change, if the respective term changes and adjust the total profit
    long double add = 0, sub = 0;
    for(int ChangeIndex = 0; ChangeIndex < NumChanges; ChangeIndex++){
        int item = ChangedBits[ChangeIndex];
        for(int term = 0; term < NumIndices[item]; term++){
            int literal = Indices[item][term];
            if (!investigated[literal]){
                int assign = 1;
                // check every item of respective term
                for (int lits = 1; lits < obj->constraints[0].literals[literal].len_literal; lits++){
                    if (!sw_tstbit(new->vector, (int) obj->constraints[0].literals[literal].literal[lits]))
                        assign = 0;
                }
                if (Fulfilled[literal] && !assign){
                    new->tot_profit -= obj->constraints[0].literals[literal].literal[0];
                }
                if (!Fulfilled[literal] && assign){
                    new->tot_profit += obj->constraints[0].literals[literal].literal[0];
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