/**
 * @file platform.c
 * @brief Platform abstraction layer implementation (POSIX + Win32).
 *
 * The POSIX backend uses clock_gettime(CLOCK_MONOTONIC), getpid,
 * sysconf(_SC_NPROCESSORS_ONLN), /dev/urandom, signal, pthread_*, and
 * pthread_once.
 *
 * The Win32 backend uses QueryPerformanceCounter, GetCurrentProcessId,
 * GetSystemInfo, BCryptGenRandom (falling back to rand_s),
 * SetConsoleCtrlHandler, CreateThread/WaitForSingleObject/CloseHandle,
 * CRITICAL_SECTION, and InitOnceExecuteOnce.
 */

/* Feature test macros must be defined before any system header inclusion. */
#if !defined(_WIN32)
  #ifndef _POSIX_C_SOURCE
    #define _POSIX_C_SOURCE 200809L
  #endif
  /* On macOS, defining _POSIX_C_SOURCE alone hides BSD extensions such as
     _SC_NPROCESSORS_ONLN; re-enable them via _DARWIN_C_SOURCE. */
  #if defined(__APPLE__) && !defined(_DARWIN_C_SOURCE)
    #define _DARWIN_C_SOURCE
  #endif
#else
  /* rand_s() requires _CRT_RAND_S before <stdlib.h> on Windows/MinGW. */
  #ifndef _CRT_RAND_S
    #define _CRT_RAND_S
  #endif
#endif

#include "platform.h"

#include <stddef.h>
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#if defined(_WIN32)

#include <bcrypt.h>
#include <process.h>
#include <signal.h>

#ifdef _MSC_VER
  #pragma comment(lib, "bcrypt.lib")
#endif

#ifndef STATUS_SUCCESS
  #define STATUS_SUCCESS ((NTSTATUS)0x00000000L)
#endif

/* ============================================================
 * Win32: time / process / concurrency discovery
 * ============================================================ */

uint64_t cbqs_monotonic_ns(void) {
    static LARGE_INTEGER freq;
    static int freq_initialized = 0;

    if (!freq_initialized) {
        if (!QueryPerformanceFrequency(&freq) || freq.QuadPart == 0) {
            return 0;
        }
        freq_initialized = 1;
    }

    LARGE_INTEGER counter;
    if (!QueryPerformanceCounter(&counter)) {
        return 0;
    }

    /* Convert ticks to nanoseconds while preserving precision:
     *   seconds      = counter / freq
     *   nanoseconds  = (counter / freq) * 1e9
     *              = (counter * 1e9) / freq
     * Split counter into whole-seconds + remainder to avoid 64-bit overflow.
     */
    uint64_t q = (uint64_t)counter.QuadPart / (uint64_t)freq.QuadPart;
    uint64_t r = (uint64_t)counter.QuadPart % (uint64_t)freq.QuadPart;
    return q * 1000000000ULL + (r * 1000000000ULL) / (uint64_t)freq.QuadPart;
}

uint32_t cbqs_getpid(void) {
    return (uint32_t)GetCurrentProcessId();
}

int cbqs_num_processors(void) {
    SYSTEM_INFO info;
    GetSystemInfo(&info);
    int n = (int)info.dwNumberOfProcessors;
    return n > 0 ? n : 1;
}

/* ============================================================
 * Win32: OS randomness
 * ============================================================ */

int cbqs_os_random_bytes(void *buf, size_t n) {
    if (n == 0) {
        return 0;
    }
    if (buf == NULL) {
        return -1;
    }

    NTSTATUS status = BCryptGenRandom(
        NULL,
        (PUCHAR)buf,
        (ULONG)n,
        BCRYPT_USE_SYSTEM_PREFERRED_RNG
    );
    if (status == STATUS_SUCCESS) {
        return 0;
    }

    /* Fallback: rand_s (cryptographically secure on Windows per MSDN). */
    unsigned char *out = (unsigned char *)buf;
    size_t produced = 0;
    while (produced < n) {
        unsigned int val = 0;
        if (rand_s(&val) != 0) {
            return -1;
        }
        size_t chunk = n - produced;
        if (chunk > sizeof(val)) {
            chunk = sizeof(val);
        }
        memcpy(out + produced, &val, chunk);
        produced += chunk;
    }
    return 0;
}

/* ============================================================
 * Win32: interrupt handling
 * ============================================================ */

static void (*g_cbqs_interrupt_handler)(int) = NULL;

static BOOL WINAPI cbqs_console_ctrl_handler(DWORD ctrl_type) {
    void (*fn)(int) = g_cbqs_interrupt_handler;
    if (fn == NULL) {
        return FALSE;
    }
    switch (ctrl_type) {
    case CTRL_C_EVENT:
    case CTRL_BREAK_EVENT:
        fn(SIGINT);
        return TRUE;
    case CTRL_CLOSE_EVENT:
    case CTRL_LOGOFF_EVENT:
    case CTRL_SHUTDOWN_EVENT:
        fn(SIGTERM);
        return TRUE;
    default:
        return FALSE;
    }
}

int cbqs_install_interrupt_handler(void (*fn)(int)) {
    if (fn == NULL) {
        g_cbqs_interrupt_handler = NULL;
        if (!SetConsoleCtrlHandler(cbqs_console_ctrl_handler, FALSE)) {
            return -1;
        }
        return 0;
    }
    g_cbqs_interrupt_handler = fn;
    if (!SetConsoleCtrlHandler(cbqs_console_ctrl_handler, TRUE)) {
        return -1;
    }
    return 0;
}

/* ============================================================
 * Win32: threads, mutexes, call-once
 * ============================================================ */

typedef struct {
    cbqs_thread_fn_t fn;
    void *arg;
} cbqs_thread_trampoline_t;

static DWORD WINAPI cbqs_thread_trampoline(LPVOID param) {
    cbqs_thread_trampoline_t *tr = (cbqs_thread_trampoline_t *)param;
    cbqs_thread_fn_t fn = tr->fn;
    void *arg = tr->arg;
    free(tr);
    (void)fn(arg);
    return 0;
}

int cbqs_thread_create(cbqs_thread_t *thread, cbqs_thread_fn_t fn, void *arg) {
    if (thread == NULL || fn == NULL) {
        return -1;
    }
    cbqs_thread_trampoline_t *tr =
        (cbqs_thread_trampoline_t *)malloc(sizeof(*tr));
    if (tr == NULL) {
        return -1;
    }
    tr->fn = fn;
    tr->arg = arg;

    HANDLE h = CreateThread(NULL, 0, cbqs_thread_trampoline, tr, 0, NULL);
    if (h == NULL) {
        free(tr);
        return -1;
    }
    thread->handle = h;
    return 0;
}

int cbqs_thread_join(cbqs_thread_t *thread) {
    if (thread == NULL || thread->handle == NULL) {
        return -1;
    }
    DWORD rc = WaitForSingleObject(thread->handle, INFINITE);
    CloseHandle(thread->handle);
    thread->handle = NULL;
    return (rc == WAIT_OBJECT_0) ? 0 : -1;
}

int cbqs_mutex_init(cbqs_mutex_t *mutex) {
    if (mutex == NULL) {
        return -1;
    }
    InitializeCriticalSection(&mutex->cs);
    return 0;
}

void cbqs_mutex_destroy(cbqs_mutex_t *mutex) {
    if (mutex == NULL) {
        return;
    }
    DeleteCriticalSection(&mutex->cs);
}

void cbqs_mutex_lock(cbqs_mutex_t *mutex) {
    EnterCriticalSection(&mutex->cs);
}

void cbqs_mutex_unlock(cbqs_mutex_t *mutex) {
    LeaveCriticalSection(&mutex->cs);
}

int cbqs_mutex_trylock(cbqs_mutex_t *mutex) {
    return TryEnterCriticalSection(&mutex->cs) ? 0 : 1;
}

/* The Win32 InitOnceExecuteOnce API passes state as PVOID, so we must
 * round-trip a function pointer through void*. ISO C forbids that, hence
 * the pedantic-suppression scope around these two helpers (MinGW/GCC).
 */
#if defined(__GNUC__) || defined(__clang__)
#  pragma GCC diagnostic push
#  pragma GCC diagnostic ignored "-Wpedantic"
#endif

static BOOL CALLBACK cbqs_init_once_trampoline(
    PINIT_ONCE once,
    PVOID param,
    PVOID *context
) {
    (void)once;
    (void)context;
    void (*fn)(void) = (void (*)(void))param;
    if (fn != NULL) {
        fn();
    }
    return TRUE;
}

void cbqs_call_once(cbqs_once_t *once, void (*fn)(void)) {
    if (once == NULL || fn == NULL) {
        return;
    }
    InitOnceExecuteOnce(once, cbqs_init_once_trampoline, (PVOID)fn, NULL);
}

#if defined(__GNUC__) || defined(__clang__)
#  pragma GCC diagnostic pop
#endif

#else /* POSIX */

#include <errno.h>
#include <fcntl.h>
#include <signal.h>
#include <time.h>
#include <unistd.h>

/* ============================================================
 * POSIX: time / process / concurrency discovery
 * ============================================================ */

uint64_t cbqs_monotonic_ns(void) {
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) {
        return 0;
    }
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

uint32_t cbqs_getpid(void) {
    return (uint32_t)getpid();
}

int cbqs_num_processors(void) {
    long n = sysconf(_SC_NPROCESSORS_ONLN);
    if (n < 1) {
        return 1;
    }
    return (int)n;
}

/* ============================================================
 * POSIX: OS randomness
 * ============================================================ */

int cbqs_os_random_bytes(void *buf, size_t n) {
    if (n == 0) {
        return 0;
    }
    if (buf == NULL) {
        return -1;
    }

    int fd = open("/dev/urandom", O_RDONLY);
    if (fd < 0) {
        return -1;
    }

    unsigned char *out = (unsigned char *)buf;
    size_t remaining = n;
    while (remaining > 0) {
        ssize_t r = read(fd, out, remaining);
        if (r < 0) {
            if (errno == EINTR) {
                continue;
            }
            close(fd);
            return -1;
        }
        if (r == 0) {
            close(fd);
            return -1;
        }
        out += (size_t)r;
        remaining -= (size_t)r;
    }
    close(fd);
    return 0;
}

/* ============================================================
 * POSIX: interrupt handling
 * ============================================================ */

int cbqs_install_interrupt_handler(void (*fn)(int)) {
    if (fn == NULL) {
        if (signal(SIGINT, SIG_DFL) == SIG_ERR) {
            return -1;
        }
        if (signal(SIGTERM, SIG_DFL) == SIG_ERR) {
            return -1;
        }
        return 0;
    }
    if (signal(SIGINT, fn) == SIG_ERR) {
        return -1;
    }
    if (signal(SIGTERM, fn) == SIG_ERR) {
        return -1;
    }
    return 0;
}

/* ============================================================
 * POSIX: threads, mutexes, call-once
 * ============================================================ */

int cbqs_thread_create(cbqs_thread_t *thread, cbqs_thread_fn_t fn, void *arg) {
    if (thread == NULL || fn == NULL) {
        return -1;
    }
    if (pthread_create(&thread->handle, NULL, fn, arg) != 0) {
        return -1;
    }
    return 0;
}

int cbqs_thread_join(cbqs_thread_t *thread) {
    if (thread == NULL) {
        return -1;
    }
    if (pthread_join(thread->handle, NULL) != 0) {
        return -1;
    }
    return 0;
}

int cbqs_mutex_init(cbqs_mutex_t *mutex) {
    if (mutex == NULL) {
        return -1;
    }
    if (pthread_mutex_init(&mutex->mutex, NULL) != 0) {
        return -1;
    }
    return 0;
}

void cbqs_mutex_destroy(cbqs_mutex_t *mutex) {
    if (mutex == NULL) {
        return;
    }
    pthread_mutex_destroy(&mutex->mutex);
}

void cbqs_mutex_lock(cbqs_mutex_t *mutex) {
    pthread_mutex_lock(&mutex->mutex);
}

void cbqs_mutex_unlock(cbqs_mutex_t *mutex) {
    pthread_mutex_unlock(&mutex->mutex);
}

int cbqs_mutex_trylock(cbqs_mutex_t *mutex) {
    return pthread_mutex_trylock(&mutex->mutex) == 0 ? 0 : 1;
}

void cbqs_call_once(cbqs_once_t *once, void (*fn)(void)) {
    if (once == NULL || fn == NULL) {
        return;
    }
    pthread_once(once, fn);
}

#endif /* _WIN32 */
