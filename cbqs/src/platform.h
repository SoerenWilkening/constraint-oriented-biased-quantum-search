/**
 * @file platform.h
 * @brief Platform abstraction layer (POSIX vs Win32)
 *
 * This header centralises all POSIX vs Win32 differences so the rest of the
 * codebase can remain portable. Each function has a POSIX implementation
 * (pthreads, clock_gettime, /dev/urandom, signal, ...) and a Win32
 * implementation (CRITICAL_SECTION, QueryPerformanceCounter, BCryptGenRandom,
 * SetConsoleCtrlHandler, ...).
 *
 * The static inline bit helpers (cbqs_popcount64, cbqs_ctz64) pick the best
 * intrinsic available on the current compiler.
 */

#ifndef CBQS_PLATFORM_H
#define CBQS_PLATFORM_H

#include <stddef.h>
#include <stdint.h>

#if defined(_WIN32)
  #ifndef WIN32_LEAN_AND_MEAN
    #define WIN32_LEAN_AND_MEAN
  #endif
  #include <windows.h>
#else
  #include <pthread.h>
#endif

#if defined(_MSC_VER)
  #include <intrin.h>
#endif

#ifdef __cplusplus
extern "C" {
#endif

/* ============================================================
 * Time / process / concurrency discovery
 * ============================================================ */

/**
 * @brief Monotonic clock in nanoseconds since an unspecified epoch.
 *
 * POSIX:  clock_gettime(CLOCK_MONOTONIC)
 * Win32:  QueryPerformanceCounter scaled by QueryPerformanceFrequency
 *
 * @return Monotonic nanoseconds, or 0 on failure.
 */
uint64_t cbqs_monotonic_ns(void);

/**
 * @brief Current process id.
 *
 * POSIX:  getpid()
 * Win32:  GetCurrentProcessId()
 *
 * @return Process id truncated to 32 bits.
 */
uint32_t cbqs_getpid(void);

/**
 * @brief Number of logical processors online.
 *
 * POSIX:  sysconf(_SC_NPROCESSORS_ONLN)
 * Win32:  GetSystemInfo().dwNumberOfProcessors
 *
 * @return Processor count (>= 1).
 */
int cbqs_num_processors(void);

/* ============================================================
 * OS randomness
 * ============================================================ */

/**
 * @brief Fill @p buf with @p n bytes from the OS entropy source.
 *
 * POSIX:  read /dev/urandom
 * Win32:  BCryptGenRandom (falls back to rand_s if unavailable)
 *
 * @param buf Destination buffer (must be non-NULL when n > 0).
 * @param n   Number of bytes to read.
 * @return 0 on success, -1 on failure.
 */
int cbqs_os_random_bytes(void *buf, size_t n);

/* ============================================================
 * Interrupt handling
 * ============================================================ */

/**
 * @brief Install a handler invoked on user interrupt.
 *
 * POSIX:  signal(SIGINT, fn); signal(SIGTERM, fn)
 * Win32:  SetConsoleCtrlHandler that translates CTRL_C_EVENT /
 *         CTRL_BREAK_EVENT / CTRL_CLOSE_EVENT into fn(SIGINT) or fn(SIGTERM)
 *
 * @param fn Callback taking a signal-number-like int.
 * @return 0 on success, -1 on failure.
 */
int cbqs_install_interrupt_handler(void (*fn)(int));

/* ============================================================
 * Threads and mutexes
 * ============================================================ */

#if defined(_WIN32)
typedef struct {
    HANDLE handle;
} cbqs_thread_t;

typedef struct {
    CRITICAL_SECTION cs;
} cbqs_mutex_t;

typedef INIT_ONCE cbqs_once_t;
#define CBQS_ONCE_INIT INIT_ONCE_STATIC_INIT
#else
typedef struct {
    pthread_t handle;
} cbqs_thread_t;

typedef struct {
    pthread_mutex_t mutex;
} cbqs_mutex_t;

typedef pthread_once_t cbqs_once_t;
#define CBQS_ONCE_INIT PTHREAD_ONCE_INIT
#endif

/**
 * @brief Thread entry point signature (matches pthreads convention).
 */
typedef void *(*cbqs_thread_fn_t)(void *);

/**
 * @brief Create a new thread running @p fn with argument @p arg.
 *
 * @return 0 on success, -1 on failure.
 */
int cbqs_thread_create(cbqs_thread_t *thread, cbqs_thread_fn_t fn, void *arg);

/**
 * @brief Wait for @p thread to finish.
 *
 * @return 0 on success, -1 on failure.
 */
int cbqs_thread_join(cbqs_thread_t *thread);

/**
 * @brief Initialise a mutex.
 *
 * @return 0 on success, -1 on failure.
 */
int cbqs_mutex_init(cbqs_mutex_t *mutex);

/**
 * @brief Destroy a mutex.
 */
void cbqs_mutex_destroy(cbqs_mutex_t *mutex);

/**
 * @brief Lock a mutex (blocking).
 */
void cbqs_mutex_lock(cbqs_mutex_t *mutex);

/**
 * @brief Unlock a mutex.
 */
void cbqs_mutex_unlock(cbqs_mutex_t *mutex);

/**
 * @brief Non-blocking lock attempt.
 *
 * @return 0 if the lock was acquired, non-zero otherwise.
 */
int cbqs_mutex_trylock(cbqs_mutex_t *mutex);

/**
 * @brief Invoke @p fn exactly once across all threads that share @p once.
 */
void cbqs_call_once(cbqs_once_t *once, void (*fn)(void));

/* ============================================================
 * Bit utilities (popcount / count-trailing-zeros on uint64_t)
 * ============================================================ */

/**
 * @brief Population count of a 64-bit value.
 */
static inline int cbqs_popcount64(uint64_t x) {
#if defined(_MSC_VER) && (defined(_M_X64) || defined(_M_ARM64))
    return (int)__popcnt64(x);
#elif defined(__GNUC__) || defined(__clang__)
    return __builtin_popcountll(x);
#else
    /* Pure-C fallback (SWAR popcount) */
    x = x - ((x >> 1) & 0x5555555555555555ULL);
    x = (x & 0x3333333333333333ULL) + ((x >> 2) & 0x3333333333333333ULL);
    x = (x + (x >> 4)) & 0x0f0f0f0f0f0f0f0fULL;
    return (int)((x * 0x0101010101010101ULL) >> 56);
#endif
}

/**
 * @brief Count trailing zeros of a 64-bit value.
 *
 * Behaviour is undefined when @p x == 0 (mirrors __builtin_ctzll).
 */
static inline int cbqs_ctz64(uint64_t x) {
#if defined(_MSC_VER) && (defined(_M_X64) || defined(_M_ARM64))
    unsigned long idx;
    _BitScanForward64(&idx, x);
    return (int)idx;
#elif defined(__GNUC__) || defined(__clang__)
    return __builtin_ctzll(x);
#else
    /* Pure-C fallback (de Bruijn sequence) */
    static const int debruijn[64] = {
         0,  1,  2, 53,  3,  7, 54, 27,
         4, 38, 41,  8, 34, 55, 48, 28,
        62,  5, 39, 46, 44, 42, 22,  9,
        24, 35, 59, 56, 49, 18, 29, 11,
        63, 52,  6, 26, 37, 40, 33, 47,
        61, 45, 43, 21, 23, 58, 17, 10,
        51, 25, 36, 32, 60, 20, 57, 16,
        50, 31, 19, 15, 30, 14, 13, 12
    };
    return debruijn[((x & (uint64_t)(-(int64_t)x)) * 0x022fdd63cc95386dULL) >> 58];
#endif
}

#ifdef __cplusplus
}
#endif

#endif /* CBQS_PLATFORM_H */
