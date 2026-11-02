# Changelog

Los cambios relevantes del proyecto se registran en este archivo.

## [Unreleased]

## [0.2.1] - 2026-11-02

### Added
- Dependencia runtime `faster-whisper` versionada en `requirements.txt`.
- Target `make setup-venv` para actualizar el entorno virtual con el intérprete elegido, preservar una copia previa e instalar las dependencias.

### Changed
- El worker adopta el descriptor Unix provisto por systemd y conserva el socket gestionado por la unidad.
- El servicio ya no reinicia periódicamente ante errores de inicio; una nueva conexión puede volver a activar el worker.

### Fixed
- La actualización del entorno virtual vuelve a asociar sus ejecutables con la versión de Python elegida y permite recuperarse del cambio del Python predeterminado del sistema.

## [0.2.0] - 2026-10-22

### Changed
- La instalación exige `pip` 26.2.2 o superior para incorporar las correcciones de seguridad publicadas en esa versión.
