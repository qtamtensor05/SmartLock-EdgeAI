idf_component_register(SRCS "face_auth.cpp"
                       INCLUDE_DIRS "include"
                       REQUIRES nvs_flash
                       PRIV_REQUIRES human_face_detect human_face_recognition esp-dl)

# Ask ESP-DL to compile the ops/kernels the face models use. Without this, any other
# component that registers its own list (ESP-SR via Arduino) strips them out.
idf_build_get_property(build_components BUILD_COMPONENTS)
if("espressif__esp-dl" IN_LIST build_components)
    idf_component_get_property(espdl_dir espressif__esp-dl COMPONENT_DIR)
elseif("esp-dl" IN_LIST build_components)
    idf_component_get_property(espdl_dir esp-dl COMPONENT_DIR)
endif()
if(espdl_dir)
    include(${espdl_dir}/cmake/compile_register.cmake)
    esp_dl_compile_add_yml(${COMPONENT_DIR}/face_models.compile_req.yml)
endif()
