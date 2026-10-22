cmake_minimum_required(VERSION 3.16)
add_compile_definitions(BSP_CONFIG_NO_GRAPHIC_LIB=1)
include($ENV{IDF_PATH}/tools/cmake/project.cmake)
project(tab5_display_test)
