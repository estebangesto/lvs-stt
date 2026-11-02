# LVS STT

Servicio local y reutilizable de transcripción de audio. Expone un socket Unix con activación bajo demanda mediante `systemd --user`: no requiere ejecutar un daemon como `root` ni iniciar el modelo al arrancar la sesión.

## Componentes

- `transcribe_whisper_fast.py`: worker reutilizable; prioriza `faster-whisper` y admite `openai-whisper` como alternativa.
- `stt_socket_client.py`: cliente manual del socket Unix.
- `stt_benchmark.py`: utilidad para medir latencia.
- `lvs-stt.service` y `lvs-stt.socket`: unidades de usuario de systemd.
- `Makefile`: tareas de validación e instalación local.

## Requisitos

- Linux con `systemd --user` disponible para el usuario que ejecutará el servicio.
- Python 3 con soporte para `venv`.
- El módulo `venv` y `pip` disponibles para el intérprete elegido. En algunas distribuciones se instalan como paquetes del sistema separados.
- Una instalación funcional de `faster-whisper` en el entorno virtual del proyecto. Para usar CUDA, el host debe tener el driver y las bibliotecas compatibles con la versión instalada.
- Acceso de escritura al directorio de instalación elegido.

El entorno virtual `venv/`, archivos `.env`, cachés y audios de prueba son locales y no se versionan.

## Instalación como usuario común

Los comandos se ejecutan con el mismo usuario que correrá OpenClaw; no se usa `sudo`.

```bash
git clone https://github.com/<owner>/lvs-stt.git ~/.local/share/lvs-stt
cd ~/.local/share/lvs-stt

make setup-venv PYTHON=python3

mkdir -p ~/.config/lvs
cp lvs-stt.env.example ~/.config/lvs/lvs-stt.env

make lint
make install
make enable
make start
make status
```

`make install` copia las unidades a `~/.config/systemd/user/`. `make enable` habilita el socket para la sesión del usuario y `make start` inicia el socket, no el modelo. El servicio se activa al recibir una solicitud y se ejecuta con los parámetros definidos en `lvs-stt.service`.

Antes de iniciar, revisar las variables `STT_*` de `~/.config/lvs/lvs-stt.env` según el hardware, modelo, idioma y tipo de cómputo disponibles.

`make setup-venv` conserva una copia del entorno virtual existente con sufijo `.backup-AAAAmmdd-HHMMSS`, actualiza el entorno para el intérprete elegido e instala las dependencias versionadas en `requirements.txt`. El comando usa `pip --python` para instalar pip dentro del entorno sin depender de `ensurepip` en el Python del sistema.

`requirements.txt` limita PyAV a la serie 18: `faster-whisper` 1.2.1 usa el parámetro `metadata_errors` de `av.open`, que fue retirado en PyAV 19.

### Recuperación después de actualizar Python

Un entorno virtual está ligado a la versión de Python con la que se creó. Si el sistema cambia el destino de `python3`, el ejecutable del entorno puede pasar a usar otra versión mientras los paquetes siguen en `lib/pythonX.Y/site-packages` de la versión anterior.

Elegí explícitamente el intérprete instalado y reconstruí el entorno antes de iniciar el servicio. Por ejemplo:

```bash
make setup-venv PYTHON=/usr/bin/python3.14
```

El entorno previo queda respaldado en el mismo directorio. Para comprobar que el intérprete y los imports coinciden:

```bash
venv/bin/python --version
venv/bin/python -m pip --version
venv/bin/python -c 'import faster_whisper; print(faster_whisper.__file__)'
```

Si el servicio falla al cargar dependencias, systemd informa el error y no lo reinicia periódicamente. Corregí la causa y una nueva solicitud al socket volverá a intentar iniciar el worker.

## Integración con OpenClaw

OpenClaw puede utilizar `lvs-stt` como proveedor local de transcripción para los audios recibidos por sus canales. El Gateway de OpenClaw y el servicio STT deben ejecutarse con el mismo usuario: el socket se crea con permisos `0600`.

Después de instalar y habilitar el socket de `lvs-stt`, agregá una entrada de tipo `cli` dentro de `tools.media.models` en la configuración de OpenClaw. El ejemplo siguiente conserva el resto de los modelos multimedia configurados y utiliza el cliente del socket para devolver únicamente el texto transcripto:

```json5
{
  tools: {
    media: {
      models: [
        // Conservá aquí las entradas existentes para imagen, audio o vídeo.
        {
          type: "cli",
          command: "~/.local/share/lvs-stt/venv/bin/python3",
          args: [
            "~/.local/share/lvs-stt/stt_socket_client.py",
            "{{AttachmentPath}}",
          ],
          timeoutSeconds: 120,
          capabilities: ["audio"],
        },
      ],
      audio: {
        enabled: true,
        // Usá este valor si querés priorizar lvs-stt sobre otros proveedores.
        preferredModel: "cli:~/.local/share/lvs-stt/venv/bin/python3",
      },
    },
  },
}
```

Si se eligió otro directorio de instalación, reemplazá las dos rutas `~/.local/share/lvs-stt` por ese directorio. `{{AttachmentPath}}` es una variable de OpenClaw y debe conservarse literalmente: OpenClaw la reemplaza por la ruta del archivo de audio antes de ejecutar el comando.

Validá la configuración y la selección de proveedores desde el mismo usuario que ejecuta el Gateway:

```bash
openclaw config validate
openclaw capability audio providers
openclaw doctor --lint --only core/doctor/local-audio-acceleration --severity-min info
```

La primera orden comprueba la configuración completa. La segunda muestra los proveedores de audio disponibles y la tercera informa las alternativas locales detectadas. En una instalación con varios modelos de audio, `preferredModel` determina que OpenClaw intente primero la entrada local de `lvs-stt`; las demás entradas pueden conservarse como alternativas.

Para verificar el servicio antes de probarlo desde un canal de OpenClaw, usá un archivo de audio local:

```bash
~/.local/share/lvs-stt/venv/bin/python3 \
  ~/.local/share/lvs-stt/stt_socket_client.py \
  /ruta/al/audio.ogg
```

La salida estándar debe contener únicamente la transcripción. Los errores se escriben en la salida de error para que OpenClaw pueda considerar fallida esa alternativa y continuar con el orden de respaldo configurado.

## Actualización

```bash
cd ~/.local/share/lvs-stt
git pull --ff-only
make lint
make install
systemctl --user daemon-reload
systemctl --user restart lvs-stt.service
```

El reinicio explícito del servicio hace que el worker cargue la nueva versión del código. Si solo se modificó el código y no las unidades, `make install` y `daemon-reload` no son necesarios.

## Prueba manual

```bash
~/.local/share/lvs-stt/venv/bin/python3 ~/.local/share/lvs-stt/stt_socket_client.py /ruta/al/audio.ogg
~/.local/share/lvs-stt/venv/bin/python3 ~/.local/share/lvs-stt/stt_socket_client.py /ruta/al/audio.ogg --json
```

## Benchmark

```bash
~/.local/share/lvs-stt/venv/bin/python3 ~/.local/share/lvs-stt/stt_benchmark.py \
  --file /ruta/al/audio.ogg --backend fast-socket
```

## Operación

```bash
make status
systemctl --user status lvs-stt.socket lvs-stt.service --no-pager
journalctl --user -u lvs-stt.service -f
```
