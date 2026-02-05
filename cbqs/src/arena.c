#include "arena.h"
#include <stdlib.h>
#include <stdint.h>

/**
 * Create a new chunk with the given size.
 *
 * @param size Size of the chunk data area
 * @return Pointer to new chunk, or NULL on allocation failure
 */
static arena_chunk_t *arena_chunk_create(size_t size) {
    arena_chunk_t *chunk = malloc(sizeof(arena_chunk_t) + size);
    if (!chunk) {
        return NULL;
    }
    chunk->next = NULL;
    chunk->size = size;
    chunk->used = 0;
    return chunk;
}

arena_t *arena_create(size_t initial_size) {
    if (initial_size == 0) {
        initial_size = ARENA_DEFAULT_SIZE;
    }

    arena_t *arena = malloc(sizeof(arena_t));
    if (!arena) {
        return NULL;
    }

    arena_chunk_t *chunk = arena_chunk_create(initial_size);
    if (!chunk) {
        free(arena);
        return NULL;
    }

    arena->head = chunk;
    arena->current = chunk;
    return arena;
}

void *arena_alloc(arena_t *arena, size_t size, size_t align) {
    if (!arena || !arena->current) {
        return NULL;
    }

    /* Alignment must be power of 2 */
    if (align == 0 || (align & (align - 1)) != 0) {
        align = 8;  /* Default to 8-byte alignment */
    }

    arena_chunk_t *chunk = arena->current;

    /* Calculate padding for alignment */
    uintptr_t ptr = (uintptr_t)(chunk->data + chunk->used);
    size_t padding = (-(ptrdiff_t)ptr) & (align - 1);

    /* Check if allocation fits in current chunk */
    if (chunk->used + padding + size > chunk->size) {
        /* Overflow: allocate new chunk */
        size_t new_size = (size + align > ARENA_CHUNK_SIZE)
                          ? size + align + 64  /* Large allocation */
                          : ARENA_CHUNK_SIZE;

        arena_chunk_t *new_chunk = arena_chunk_create(new_size);
        if (!new_chunk) {
            return NULL;
        }

        /* Link new chunk into list */
        chunk->next = new_chunk;
        arena->current = new_chunk;
        chunk = new_chunk;

        /* Recalculate padding for new chunk (starts aligned) */
        ptr = (uintptr_t)chunk->data;
        padding = (-(ptrdiff_t)ptr) & (align - 1);
    }

    void *result = chunk->data + chunk->used + padding;
    chunk->used += padding + size;
    return result;
}

void arena_reset(arena_t *arena) {
    if (!arena) {
        return;
    }

    /* Reset used counter in all chunks */
    arena_chunk_t *chunk = arena->head;
    while (chunk) {
        chunk->used = 0;
        chunk = chunk->next;
    }

    /* Reset current to head for new allocations */
    arena->current = arena->head;
}

void arena_free(arena_t *arena) {
    if (!arena) {
        return;
    }

    /* Free all chunks in the linked list */
    arena_chunk_t *chunk = arena->head;
    while (chunk) {
        arena_chunk_t *next = chunk->next;
        free(chunk);
        chunk = next;
    }

    free(arena);
}

size_t arena_allocated(arena_t *arena) {
    if (!arena) {
        return 0;
    }

    size_t total = 0;
    arena_chunk_t *chunk = arena->head;
    while (chunk) {
        total += chunk->size;
        chunk = chunk->next;
    }
    return total;
}

size_t arena_used(arena_t *arena) {
    if (!arena) {
        return 0;
    }

    size_t total = 0;
    arena_chunk_t *chunk = arena->head;
    while (chunk) {
        total += chunk->used;
        chunk = chunk->next;
    }
    return total;
}
