if(EXISTS "/Users/johntedesco/KDS/new_py2cpp/build/tests/testlib[1]_tests.cmake")
  include("/Users/johntedesco/KDS/new_py2cpp/build/tests/testlib[1]_tests.cmake")
else()
  add_test(testlib_NOT_BUILT testlib_NOT_BUILT)
endif()
