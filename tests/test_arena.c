#include <stdarg.h>
#include <stddef.h>
#include <setjmp.h>
#include <cmocka.h>
#include <stdint.h>
#include <string.h>

#include "arena.h"

/* test_arena_create_free: create arena, verify non-NULL, free without crash */
static void test_arena_create_free(void **state) {
    (void)state;

    arena_t *arena = arena_create(ARENA_DEFAULT_SIZE);
    assert_non_null(arena);
    assert_int_equal(arena_allocated(arena), ARENA_DEFAULT_SIZE);
    assert_int_equal(arena_used(arena), 0);
    arena_free(arena);
}

/* test_arena_create_custom_size: create with custom initial size */
static void test_arena_create_custom_size(void **state) {
    (void)state;

    arena_t *arena = arena_create(4096);
    assert_non_null(arena);
    assert_int_equal(arena_allocated(arena), 4096);
    arena_free(arena);

    /* Zero size should use default */
    arena = arena_create(0);
    assert_non_null(arena);
    assert_int_equal(arena_allocated(arena), ARENA_DEFAULT_SIZE);
    arena_free(arena);
}

/* test_arena_basic_alloc: allocate small buffer, verify non-NULL return */
static void test_arena_basic_alloc(void **state) {
    (void)state;

    arena_t *arena = arena_create(4096);
    assert_non_null(arena);

    void *ptr = arena_alloc(arena, 100, 8);
    assert_non_null(ptr);
    assert_true(arena_used(arena) >= 100);

    /* Write to verify memory is accessible */
    memset(ptr, 0xAB, 100);

    arena_free(arena);
}

/* test_arena_alignment: allocate with align=8, verify address is 8-byte aligned */
static void test_arena_alignment(void **state) {
    (void)state;

    arena_t *arena = arena_create(4096);
    assert_non_null(arena);

    /* Make first allocation to potentially misalign */
    void *ptr1 = arena_alloc(arena, 3, 1);  /* 3 bytes, no alignment */
    assert_non_null(ptr1);

    /* Next allocation should be 8-byte aligned */
    void *ptr2 = arena_alloc(arena, 100, 8);
    assert_non_null(ptr2);
    assert_true(((uintptr_t)ptr2 & 7) == 0);  /* 8-byte aligned */

    /* 16-byte alignment */
    void *ptr3 = arena_alloc(arena, 100, 16);
    assert_non_null(ptr3);
    assert_true(((uintptr_t)ptr3 & 15) == 0);  /* 16-byte aligned */

    /* 32-byte alignment */
    void *ptr4 = arena_alloc(arena, 100, 32);
    assert_non_null(ptr4);
    assert_true(((uintptr_t)ptr4 & 31) == 0);  /* 32-byte aligned */

    arena_free(arena);
}

/* test_arena_multiple_allocs: many small allocations, verify all distinct addresses */
static void test_arena_multiple_allocs(void **state) {
    (void)state;

    arena_t *arena = arena_create(4096);
    assert_non_null(arena);

    void *ptrs[100];
    for (int i = 0; i < 100; i++) {
        ptrs[i] = arena_alloc(arena, 16, 8);
        assert_non_null(ptrs[i]);

        /* Verify distinct from all previous allocations */
        for (int j = 0; j < i; j++) {
            assert_ptr_not_equal(ptrs[i], ptrs[j]);
        }

        /* Write pattern to verify memory */
        memset(ptrs[i], i & 0xFF, 16);
    }

    /* Verify patterns are still intact */
    for (int i = 0; i < 100; i++) {
        unsigned char *p = ptrs[i];
        for (int j = 0; j < 16; j++) {
            assert_int_equal(p[j], i & 0xFF);
        }
    }

    arena_free(arena);
}

/* test_arena_overflow_chunk: allocate more than initial size, verify overflow handling */
static void test_arena_overflow_chunk(void **state) {
    (void)state;

    /* Small initial size to force overflow quickly */
    arena_t *arena = arena_create(1024);
    assert_non_null(arena);

    size_t initial_allocated = arena_allocated(arena);
    assert_int_equal(initial_allocated, 1024);

    /* Allocate more than the initial chunk can hold */
    size_t total_alloc = 0;
    for (int i = 0; i < 10; i++) {
        void *ptr = arena_alloc(arena, 256, 8);
        assert_non_null(ptr);
        total_alloc += 256;
    }

    /* Should have allocated additional chunks */
    size_t final_allocated = arena_allocated(arena);
    assert_true(final_allocated > initial_allocated);

    /* Used should reflect our allocations plus alignment padding */
    assert_true(arena_used(arena) >= total_alloc);

    arena_free(arena);
}

/* test_arena_reset: allocate, reset, allocate again in same memory */
static void test_arena_reset(void **state) {
    (void)state;

    arena_t *arena = arena_create(4096);
    assert_non_null(arena);

    /* First set of allocations */
    void *ptr1 = arena_alloc(arena, 100, 8);
    assert_non_null(ptr1);
    void *ptr2 = arena_alloc(arena, 200, 8);
    assert_non_null(ptr2);

    size_t used_before = arena_used(arena);
    assert_true(used_before >= 300);

    /* Reset arena */
    arena_reset(arena);

    /* Used should be back to 0 */
    assert_int_equal(arena_used(arena), 0);

    /* Allocated stays the same (memory not freed) */
    assert_int_equal(arena_allocated(arena), 4096);

    /* New allocations should start from beginning */
    void *ptr3 = arena_alloc(arena, 100, 8);
    assert_non_null(ptr3);

    /* ptr3 should be at or near the start of the arena (like ptr1 was) */
    /* Due to alignment, we can't guarantee exact same address, but used should be similar */
    size_t used_after = arena_used(arena);
    assert_true(used_after < used_before);

    arena_free(arena);
}

/* test_arena_reset_with_overflow: reset clears all chunks */
static void test_arena_reset_with_overflow(void **state) {
    (void)state;

    /* Small initial to force overflow */
    arena_t *arena = arena_create(256);
    assert_non_null(arena);

    /* Force overflow into additional chunks */
    for (int i = 0; i < 5; i++) {
        void *ptr = arena_alloc(arena, 128, 8);
        assert_non_null(ptr);
    }

    size_t chunks_allocated = arena_allocated(arena);
    assert_true(chunks_allocated > 256);  /* Has overflow chunks */

    size_t used_before = arena_used(arena);
    assert_true(used_before >= 5 * 128);

    /* Reset should clear all chunks */
    arena_reset(arena);

    /* All chunks still allocated, but none used */
    assert_int_equal(arena_allocated(arena), chunks_allocated);
    assert_int_equal(arena_used(arena), 0);

    arena_free(arena);
}

/* test_arena_large_alloc: single allocation larger than chunk size */
static void test_arena_large_alloc(void **state) {
    (void)state;

    arena_t *arena = arena_create(1024);
    assert_non_null(arena);

    /* Allocate larger than both initial size and overflow chunk size */
    size_t large_size = ARENA_CHUNK_SIZE + 1000;
    void *ptr = arena_alloc(arena, large_size, 8);
    assert_non_null(ptr);

    /* Should have allocated at least enough for this request */
    assert_true(arena_allocated(arena) >= large_size);

    /* Write to verify memory is accessible */
    memset(ptr, 0xCD, large_size);

    arena_free(arena);
}

/* test_arena_null_safety: arena_alloc(NULL, ...) returns NULL, arena_free(NULL) is safe */
static void test_arena_null_safety(void **state) {
    (void)state;

    /* arena_alloc with NULL arena should return NULL */
    void *ptr = arena_alloc(NULL, 100, 8);
    assert_null(ptr);

    /* arena_reset with NULL should not crash */
    arena_reset(NULL);

    /* arena_free with NULL should not crash */
    arena_free(NULL);

    /* arena_allocated/arena_used with NULL should return 0 */
    assert_int_equal(arena_allocated(NULL), 0);
    assert_int_equal(arena_used(NULL), 0);
}

/* test_arena_zero_size_alloc: allocating 0 bytes */
static void test_arena_zero_size_alloc(void **state) {
    (void)state;

    arena_t *arena = arena_create(4096);
    assert_non_null(arena);

    /* Zero-size allocation should still return a valid pointer */
    void *ptr = arena_alloc(arena, 0, 8);
    assert_non_null(ptr);

    /* Can allocate normally after zero-size - ptr2 may equal ptr since
     * zero-size doesn't advance the bump pointer (valid behavior) */
    void *ptr2 = arena_alloc(arena, 100, 8);
    assert_non_null(ptr2);
    /* Note: ptr and ptr2 may be equal if zero-size didn't advance pointer */

    /* A subsequent non-zero allocation should be distinct */
    void *ptr3 = arena_alloc(arena, 100, 8);
    assert_non_null(ptr3);
    assert_ptr_not_equal(ptr2, ptr3);

    arena_free(arena);
}

/* test_arena_alignment_edge_cases: invalid alignment values */
static void test_arena_alignment_edge_cases(void **state) {
    (void)state;

    arena_t *arena = arena_create(4096);
    assert_non_null(arena);

    /* Non-power-of-2 alignment should default to 8 */
    void *ptr1 = arena_alloc(arena, 100, 7);
    assert_non_null(ptr1);
    assert_true(((uintptr_t)ptr1 & 7) == 0);  /* Should be 8-byte aligned */

    /* Zero alignment should default to 8 */
    void *ptr2 = arena_alloc(arena, 100, 0);
    assert_non_null(ptr2);
    assert_true(((uintptr_t)ptr2 & 7) == 0);  /* Should be 8-byte aligned */

    arena_free(arena);
}

int main(void) {
    const struct CMUnitTest tests[] = {
        cmocka_unit_test(test_arena_create_free),
        cmocka_unit_test(test_arena_create_custom_size),
        cmocka_unit_test(test_arena_basic_alloc),
        cmocka_unit_test(test_arena_alignment),
        cmocka_unit_test(test_arena_multiple_allocs),
        cmocka_unit_test(test_arena_overflow_chunk),
        cmocka_unit_test(test_arena_reset),
        cmocka_unit_test(test_arena_reset_with_overflow),
        cmocka_unit_test(test_arena_large_alloc),
        cmocka_unit_test(test_arena_null_safety),
        cmocka_unit_test(test_arena_zero_size_alloc),
        cmocka_unit_test(test_arena_alignment_edge_cases),
    };
    return cmocka_run_group_tests(tests, NULL, NULL);
}
