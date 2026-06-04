#ifndef TYPEDEFS_H
#define TYPEDEFS_H

#include <stdbool.h>

// define constants
//#define UNDEFINED -2

#define MINIMIZE 1
#define MAXIMIZE -1

#define OPTIMIZE 2
#define SATISFY 3

#define INTEGER 4
#define FRACTIONAL 5

#define GREATER 6
#define LOWER 7
#define EQUAL 8

#define LINEAR 2    // needs to be adjusted later
#define QUADRATIC 3//

#define ACCEPTMANY 1
#define ACCEPTONE 0

#define STOPATBEST 0
#define STOPATFIRST 1

// define callback functionality
typedef void (*callback_t)(void);

typedef int solver_t;

#define INVERSE 1
#define PLAIN -1
#define NEGATIVE 0
#define POSITIVE 1

#define SPARSE 10
#define DENSE 11


#define MIN(a,b)                ((a) < (b) ? (a) : (b))

/* Portability macro: mark parameters as intentionally unused */
#if defined(__GNUC__) || defined(__clang__)
  #define CBQS_UNUSED __attribute__((unused))
#else
  #define CBQS_UNUSED
#endif

/* Portability macro: thread-local storage */
#if defined(_MSC_VER)
  #define CBQS_THREAD_LOCAL __declspec(thread)
#elif defined(__GNUC__) || defined(__clang__)
  #define CBQS_THREAD_LOCAL __thread
#else
  #define CBQS_THREAD_LOCAL _Thread_local
#endif

#endif
