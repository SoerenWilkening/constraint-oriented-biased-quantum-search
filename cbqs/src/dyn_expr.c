/**
 * dyn_expr.c - Dynamic expression storage with small-object optimization (SOO)
 *
 * Implementation of memory-efficient expression storage that uses inline
 * storage for small expressions and heap allocation with 2x growth for larger ones.
 *
 * Phase 6: Memory Optimization
 */

#include "dyn_expr.h"
#include <stdlib.h>
#include <string.h>
#include <stdio.h>

/* ============================================================================
 * Internal helpers
 * ============================================================================ */

/**
 * Calculate array index for term element.
 * Same layout as Expression.c: literals[term * MAX_VARS_PER_TERM + element]
 */
static inline size_t dyn_expr_index(size_t term, int element) {
    return term * MAX_VARS_PER_TERM + (size_t)element;
}

/**
 * Ensure capacity for at least 'needed' terms.
 * Handles inline-to-heap transition and heap growth.
 * Returns 0 on success, -1 on allocation failure.
 */
static int dyn_expr_ensure_capacity(dyn_expression_t *expr, size_t needed) {
    /* Already have enough capacity */
    if (expr->capacity == 0) {
        /* Currently using inline storage */
        if (needed <= EXPR_INLINE_CAPACITY) {
            return 0;  /* Still fits in inline */
        }
        /* Need to transition to heap */
        size_t new_capacity = EXPR_INITIAL_HEAP_CAPACITY;
        while (new_capacity < needed) {
            new_capacity *= 2;
        }

        /* Allocate heap arrays */
        int64_t *new_literals = malloc(new_capacity * MAX_VARS_PER_TERM * sizeof(int64_t));
        if (!new_literals) {
            return -1;
        }
        int *new_len_literal = malloc(new_capacity * sizeof(int));
        if (!new_len_literal) {
            free(new_literals);
            return -1;
        }

        /* Initialize with -1 (padding value) */
        for (size_t i = 0; i < new_capacity * MAX_VARS_PER_TERM; i++) {
            new_literals[i] = -1;
        }

        /* Copy existing inline data */
        memcpy(new_literals, expr->inline_literals,
               expr->expr_size * MAX_VARS_PER_TERM * sizeof(int64_t));
        memcpy(new_len_literal, expr->inline_len_literal,
               expr->expr_size * sizeof(int));

        /* Switch to heap */
        expr->literals = new_literals;
        expr->len_literal = new_len_literal;
        expr->capacity = new_capacity;
        return 0;
    } else {
        /* Already using heap */
        if (needed <= expr->capacity) {
            return 0;  /* Enough capacity */
        }
        /* Need to grow heap */
        size_t new_capacity = expr->capacity;
        while (new_capacity < needed) {
            new_capacity *= 2;
        }

        int64_t *new_literals = realloc(expr->literals,
                                        new_capacity * MAX_VARS_PER_TERM * sizeof(int64_t));
        if (!new_literals) {
            return -1;
        }
        int *new_len_literal = realloc(expr->len_literal,
                                       new_capacity * sizeof(int));
        if (!new_len_literal) {
            /* Restore literals pointer on partial failure */
            expr->literals = new_literals;
            return -1;
        }

        /* Initialize new slots with -1 */
        for (size_t i = expr->capacity * MAX_VARS_PER_TERM;
             i < new_capacity * MAX_VARS_PER_TERM; i++) {
            new_literals[i] = -1;
        }

        expr->literals = new_literals;
        expr->len_literal = new_len_literal;
        expr->capacity = new_capacity;
        return 0;
    }
}

/* ============================================================================
 * Lifecycle
 * ============================================================================ */

dyn_expression_t *dyn_expr_init(void) {
    dyn_expression_t *expr = malloc(sizeof(dyn_expression_t));
    if (!expr) {
        return NULL;
    }

    /* Start in inline mode */
    expr->literals = NULL;
    expr->len_literal = NULL;
    expr->expr_size = 0;
    expr->capacity = 0;  /* 0 = inline mode */
    expr->sense = 0;
    expr->rhs = 0;

    /* Initialize inline storage with -1 (padding value) */
    for (int i = 0; i < EXPR_INLINE_CAPACITY * MAX_VARS_PER_TERM; i++) {
        expr->inline_literals[i] = -1;
    }
    for (int i = 0; i < EXPR_INLINE_CAPACITY; i++) {
        expr->inline_len_literal[i] = 0;
    }

    return expr;
}

void dyn_expr_free(dyn_expression_t *expr) {
    if (!expr) {
        return;
    }

    /* Free heap arrays if allocated */
    if (expr->capacity > 0) {
        free(expr->literals);
        free(expr->len_literal);
    }

    free(expr);
}

/* ============================================================================
 * Copy
 * ============================================================================ */

void dyn_expr_copy(dyn_expression_t *dest, const dyn_expression_t *src) {
    if (!dest || !src) {
        return;
    }

    /* Copy scalar fields */
    dest->expr_size = src->expr_size;
    dest->sense = src->sense;
    dest->rhs = src->rhs;

    /* Determine if src uses inline or heap */
    if (src->capacity == 0) {
        /* Source is inline */
        if (dest->capacity > 0) {
            /* Dest was heap, switch to inline */
            free(dest->literals);
            free(dest->len_literal);
            dest->literals = NULL;
            dest->len_literal = NULL;
            dest->capacity = 0;
        }
        /* Copy inline data */
        memcpy(dest->inline_literals, src->inline_literals,
               EXPR_INLINE_CAPACITY * MAX_VARS_PER_TERM * sizeof(int64_t));
        memcpy(dest->inline_len_literal, src->inline_len_literal,
               EXPR_INLINE_CAPACITY * sizeof(int));
    } else {
        /* Source is heap */
        /* Ensure dest has enough heap capacity */
        if (dest->capacity < src->capacity) {
            if (dest->capacity > 0) {
                free(dest->literals);
                free(dest->len_literal);
            }
            dest->literals = malloc(src->capacity * MAX_VARS_PER_TERM * sizeof(int64_t));
            dest->len_literal = malloc(src->capacity * sizeof(int));
            if (!dest->literals || !dest->len_literal) {
                /* Allocation failure - leave dest in inconsistent state */
                return;
            }
            dest->capacity = src->capacity;
        }
        /* Copy heap data */
        memcpy(dest->literals, src->literals,
               src->capacity * MAX_VARS_PER_TERM * sizeof(int64_t));
        memcpy(dest->len_literal, src->len_literal,
               src->capacity * sizeof(int));
    }
}

/* ============================================================================
 * Access
 * ============================================================================ */

int64_t *dyn_expr_literals(dyn_expression_t *expr) {
    if (!expr) {
        return NULL;
    }
    return (expr->capacity == 0) ? expr->inline_literals : expr->literals;
}

int *dyn_expr_len_literal(dyn_expression_t *expr) {
    if (!expr) {
        return NULL;
    }
    return (expr->capacity == 0) ? expr->inline_len_literal : expr->len_literal;
}

/* ============================================================================
 * Modification
 * ============================================================================ */

int dyn_expr_add_constant(dyn_expression_t *expr, int64_t constant) {
    if (!expr) {
        return -1;
    }
    if (constant == 0) {
        return 0;  /* Skip zero constants like Expression.c */
    }

    if (dyn_expr_ensure_capacity(expr, expr->expr_size + 1) != 0) {
        return -1;
    }

    int64_t *lits = dyn_expr_literals(expr);
    int *lens = dyn_expr_len_literal(expr);

    lits[dyn_expr_index(expr->expr_size, 0)] = constant;
    /* Rest of the term slots should already be -1 from initialization */
    lens[expr->expr_size] = 1;
    expr->expr_size++;

    return 0;
}

int dyn_expr_add_variable(dyn_expression_t *expr, int64_t index) {
    if (!expr) {
        return -1;
    }

    if (dyn_expr_ensure_capacity(expr, expr->expr_size + 1) != 0) {
        return -1;
    }

    int64_t *lits = dyn_expr_literals(expr);
    int *lens = dyn_expr_len_literal(expr);

    lits[dyn_expr_index(expr->expr_size, 0)] = 1;      /* coefficient */
    lits[dyn_expr_index(expr->expr_size, 1)] = index;  /* variable index */
    /* Slots 2, 3 should already be -1 */
    lens[expr->expr_size] = 2;
    expr->expr_size++;

    return 0;
}

int dyn_expr_add_term(dyn_expression_t *expr, int64_t coeff,
                      const int64_t *vars, int num_vars) {
    if (!expr) {
        return -1;
    }
    if (num_vars < 0 || num_vars >= MAX_VARS_PER_TERM) {
        return -1;  /* Invalid number of variables */
    }

    if (dyn_expr_ensure_capacity(expr, expr->expr_size + 1) != 0) {
        return -1;
    }

    int64_t *lits = dyn_expr_literals(expr);
    int *lens = dyn_expr_len_literal(expr);

    lits[dyn_expr_index(expr->expr_size, 0)] = coeff;
    for (int i = 0; i < num_vars; i++) {
        lits[dyn_expr_index(expr->expr_size, i + 1)] = vars[i];
    }
    /* Remaining slots should be -1 */
    lens[expr->expr_size] = 1 + num_vars;
    expr->expr_size++;

    return 0;
}

/* ============================================================================
 * Sense and RHS
 * ============================================================================ */

void dyn_expr_set_sense(dyn_expression_t *expr, int sense) {
    if (expr) {
        expr->sense = sense;
    }
}

void dyn_expr_set_rhs(dyn_expression_t *expr, int64_t rhs) {
    if (expr) {
        expr->rhs = rhs;
    }
}

/* ============================================================================
 * Query
 * ============================================================================ */

size_t dyn_expr_size(const dyn_expression_t *expr) {
    return expr ? expr->expr_size : 0;
}

int dyn_expr_is_inline(const dyn_expression_t *expr) {
    return expr ? (expr->capacity == 0) : 0;
}

/* ============================================================================
 * Debug
 * ============================================================================ */

void dyn_expr_print(const dyn_expression_t *expr) {
    if (!expr) {
        printf("(null expression)\n");
        return;
    }

    printf("dyn_expression_t: size=%zu, capacity=%zu (%s)\n",
           expr->expr_size, expr->capacity,
           expr->capacity == 0 ? "inline" : "heap");
    printf("  sense=%d, rhs=%lld\n", expr->sense, (long long)expr->rhs);

    const int64_t *lits = (expr->capacity == 0)
                          ? expr->inline_literals
                          : expr->literals;
    const int *lens = (expr->capacity == 0)
                      ? expr->inline_len_literal
                      : expr->len_literal;

    for (size_t i = 0; i < expr->expr_size; i++) {
        printf("  term[%zu]: ", i);
        for (int j = 0; j < lens[i]; j++) {
            printf("%lld ", (long long)lits[dyn_expr_index(i, j)]);
        }
        printf("\n");
    }
}
