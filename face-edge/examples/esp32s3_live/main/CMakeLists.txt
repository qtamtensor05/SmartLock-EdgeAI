idf_component_register(SRCS "live_main.cpp" INCLUDE_DIRS "."
                       PRIV_REQUIRES esp32-camera face_auth esp_timer mbedtls esp_driver_uart)
