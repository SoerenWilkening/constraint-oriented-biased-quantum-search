set(CMAKE_SYSTEM_NAME Windows)
set(CMAKE_SYSTEM_PROCESSOR x86_64)
set(CMAKE_C_COMPILER   x86_64-w64-mingw32-gcc)
set(CMAKE_CXX_COMPILER x86_64-w64-mingw32-g++)
set(CMAKE_RC_COMPILER  x86_64-w64-mingw32-windres)
set(CMAKE_FIND_ROOT_PATH /usr/x86_64-w64-mingw32)
set(CMAKE_FIND_ROOT_PATH_MODE_PROGRAM NEVER)
set(CMAKE_FIND_ROOT_PATH_MODE_LIBRARY ONLY)
set(CMAKE_FIND_ROOT_PATH_MODE_INCLUDE ONLY)
# Run ctest's .exe targets through Wine with a valid XDG_RUNTIME_DIR so Wine
# does not print "error: XDG_RUNTIME_DIR is invalid or not set in the
# environment." on stderr. This only affects cbqs's own add_test() targets;
# upstream cmocka's vendored self-tests (test_basics_tap, test_groups_xml,
# etc.) bypass CMAKE_CROSSCOMPILING_EMULATOR and invoke wine directly, and
# additionally emit "wine32 missing", winediag, systray, and ntoskrnl lines
# under a minimal Linux Wine install -- those break cmocka's ^-anchored
# output regexes regardless of XDG, so they are treated as a known Wine
# limitation; narrow ctest to cbqs tests (e.g. -I 1,20) for clean runs.
set(CMAKE_CROSSCOMPILING_EMULATOR env XDG_RUNTIME_DIR=/tmp wine)
