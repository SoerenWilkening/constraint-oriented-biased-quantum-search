#ifndef TYPEDEFS_H
#define TYPEDEFS_H


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
typedef void (*callback_t)(int64_t, size_t, double, double);

typedef int solver_t;

#define INVERSE 1
#define PLAIN -1
#define NEGATIVE 0
#define POSITIVE 1


#define MIN(a,b)                ((a) < (b) ? (a) : (b))
#define false 0
#define true 1

#endif