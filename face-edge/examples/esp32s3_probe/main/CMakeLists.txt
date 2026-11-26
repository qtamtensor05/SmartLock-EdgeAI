foreach(name bill1 bill2 musk1 musk2)
    if(NOT EXISTS "${CMAKE_CURRENT_LIST_DIR}/fixtures/${name}.jpg")
        message(FATAL_ERROR "Missing fixed JPEG fixtures. Run python face-edge/tools/probe.py prepare from SmartLock-EdgeAI root.")
    endif()
endforeach()
idf_component_register(
    SRCS "face_edge_probe.cpp"
    INCLUDE_DIRS "."
    REQUIRES human_face_recognition esp_timer esp_psram spiffs
    EMBED_FILES "fixtures/bill1.jpg" "fixtures/bill2.jpg" "fixtures/musk1.jpg" "fixtures/musk2.jpg"
)
target_compile_definitions(${COMPONENT_LIB} PRIVATE FACE_PROBE_FIXTURE_COMPAT=$<BOOL:${FACE_PROBE_FIXTURE_COMPAT}>)
