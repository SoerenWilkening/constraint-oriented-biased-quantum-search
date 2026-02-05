/**
 * dyn_expr.h - Dynamic expression storage with small-object optimization (SOO)
 *
 * This module provides a memory-efficient expression type that:
 * - Uses inline storage for small expressions (<=8 terms) without heap allocation
 * - Dynamically grows with 2x capacity doubling for larger expressions
 * - Maintains API compatibility with expression_t patterns
 *
 * Phase 6: Memory Optimization
 */

#ifndef DYN_EXPR_H
#define DYN_EXPR_H

#include <stdint.h>
#include <stddef.h>

/* Maximum variables per term (coefficient + up to 3 variable indices) */
#define MAX_VARS_PER_TERM 4

/* Inline storage threshold (no heap allocation for <= this many terms) */
#define EXPR_INLINE_CAPACITY 8

/* Initial heap capacity when transitioning from inline */
#define EXPR_INITIAL_HEAP_CAPACITY 32

/**
 * Dynamic expression with small-object optimization.
 *
 * Storage strategy:
 * - If capacity == 0: using inline storage (inline_literals, inline_len_literal)
 * - If capacity > 0: using heap storage (literals, len_literal pointers)
 *
 * Each term is stored as:
 *   literals[term_idx * MAX_VARS_PER_TERM + 0] = coefficient
 *   literals[term_idx * MAX_VARS_PER_TERM + 1..3] = variable indices (or -1 if unused)
 *   len_literal[term_idx] = number of elements used (1 for constant, 2+ for variables)
 */
typedef struct {
    /* Heap storage pointers (NULL when using inline) */
    int64_t *literals;
    int *len_literal;

    /* Current term count and allocated capacity */
    size_t expr_size;
    size_t capacity;        /* 0 = using inline storage */

    /* Constraint sense and RHS */
    int sense;
    int64_t rhs;

    /* Inline storage for small expressions */
    int64_t inline_literals[EXPR_INLINE_CAPACITY * MAX_VARS_PER_TERM];
    int inline_len_literal[EXPR_INLINE_CAPACITY];
} dyn_expression_t;

/* ============================================================================
 * Lifecycle
 * ============================================================================ */

/**
 * Create a new dynamic expression.
 * Returns NULL on allocation failure.
 */
dyn_expression_t *dyn_expr_init(void);

/**
 * Free a dynamic expression and its resources.
 * Safe to call with NULL.
 */
void dyn_expr_free(dyn_expression_t *expr);

/* ============================================================================
 * Copy
 * ============================================================================ */

/**
 * Deep copy expression contents from src to dest.
 * Dest must be initialized. Existing dest data is overwritten.
 */
void dyn_expr_copy(dyn_expression_t *dest, const dyn_expression_t *src);

/* ============================================================================
 * Access (handles inline vs heap transparently)
 * ============================================================================ */

/**
 * Get pointer to literals array (inline or heap).
 * Valid until next add operation.
 */
int64_t *dyn_expr_literals(dyn_expression_t *expr);

/**
 * Get pointer to len_literal array (inline or heap).
 * Valid until next add operation.
 */
int *dyn_expr_len_literal(dyn_expression_t *expr);

/* ============================================================================
 * Modification
 * ============================================================================ */

/**
 * Add a constant term to the expression.
 * Returns 0 on success, -1 on allocation failure.
 */
int dyn_expr_add_constant(dyn_expression_t *expr, int64_t constant);

/**
 * Add a single variable term (coefficient 1) to the expression.
 * Returns 0 on success, -1 on allocation failure.
 */
int dyn_expr_add_variable(dyn_expression_t *expr, int64_t index);

/**
 * Add a term with coefficient and variable indices.
 * vars array should have num_vars elements.
 * Returns 0 on success, -1 on allocation failure.
 */
int dyn_expr_add_term(dyn_expression_t *expr, int64_t coeff,
                      const int64_t *vars, int num_vars);

/* ============================================================================
 * Sense and RHS
 * ============================================================================ */

/**
 * Set the constraint sense (GREATER, LOWER, EQUAL from definitions.h).
 */
void dyn_expr_set_sense(dyn_expression_t *expr, int sense);

/**
 * Set the constraint right-hand side value.
 */
void dyn_expr_set_rhs(dyn_expression_t *expr, int64_t rhs);

/* ============================================================================
 * Query
 * ============================================================================ */

/**
 * Get the number of terms in the expression.
 */
size_t dyn_expr_size(const dyn_expression_t *expr);

/**
 * Check if expression is using inline storage.
 * Returns non-zero if inline, 0 if heap.
 */
int dyn_expr_is_inline(const dyn_expression_t *expr);

/* ============================================================================
 * Debug
 * ============================================================================ */

/**
 * Print expression contents to stdout.
 */
void dyn_expr_print(const dyn_expression_t *expr);

#endif /* DYN_EXPR_H */
