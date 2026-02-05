#ifndef ARENA_H
#define ARENA_H

#include <stddef.h>

#define ARENA_DEFAULT_SIZE (1024 * 1024)   /* 1MB initial chunk */
#define ARENA_CHUNK_SIZE   (256 * 1024)    /* 256KB overflow chunks */

typedef struct arena_chunk {
    struct arena_chunk *next;  /* Linked list of chunks */
    size_t size;               /* Chunk size (bytes available in data[]) */
    size_t used;               /* Current offset in data[] */
    char data[];               /* Flexible array member */
} arena_chunk_t;

typedef struct {
    arena_chunk_t *head;       /* First chunk (initial allocation) */
    arena_chunk_t *current;    /* Current allocation chunk */
} arena_t;

/**
 * Create arena with initial_size bytes.
 * Use ARENA_DEFAULT_SIZE for the default 1MB initial chunk.
 *
 * @param initial_size Size of the initial chunk in bytes
 * @return Pointer to arena, or NULL on allocation failure
 */
arena_t *arena_create(size_t initial_size);

/**
 * Allocate size bytes with given alignment from the arena.
 * Alignment must be a power of 2 (typically 8 for int64_t).
 *
 * @param arena The arena to allocate from
 * @param size Number of bytes to allocate
 * @param align Alignment requirement (must be power of 2)
 * @return Pointer to allocated memory, or NULL if arena is NULL or allocation fails
 */
void *arena_alloc(arena_t *arena, size_t size, size_t align);

/**
 * Reset all chunks to start (keeps memory allocated for reuse).
 * After reset, all previous allocations are invalidated.
 *
 * @param arena The arena to reset (no-op if NULL)
 */
void arena_reset(arena_t *arena);

/**
 * Free arena and all chunks.
 *
 * @param arena The arena to free (no-op if NULL)
 */
void arena_free(arena_t *arena);

/**
 * Debug: get total allocated bytes across all chunks.
 *
 * @param arena The arena to query
 * @return Total allocated capacity, or 0 if arena is NULL
 */
size_t arena_allocated(arena_t *arena);

/**
 * Debug: get currently used bytes across all chunks.
 *
 * @param arena The arena to query
 * @return Total used bytes, or 0 if arena is NULL
 */
size_t arena_used(arena_t *arena);

#endif /* ARENA_H */
