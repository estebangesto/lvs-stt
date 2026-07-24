# Luc.ia STT

Servicio local de transcripción de audio para Luc.ia. Expone un socket Unix con activación bajo demanda mediante `systemd --user`: no requiere ejecutar un daemon como `root` ni iniciar el modelo al arrancar la sesión.

## Componentes

- `transcribe_whisper_fast.py`: worker reutilizable; prioriza `faster-whisper` y admite `openai-whisper` como alternativa.
- `stt_socket_client.py`: cliente manual del socket Unix.
- `stt_benchmark.py`: utilidad para medir latencia.
- `lucia-stt.service` y `lucia-stt.socket`: unidades de usuario de systemd.
- `Makefile`: tareas de validación e instalación local.

## Requisitos

- Linux con `systemd --user` disponible para el usuario que ejecutará Luc.ia.
- Python 3 con soporte para `venv`.
- Una instalación funcional de `faster-whisper` en el entorno virtual del proyecto. Para usar CUDA, el host debe tener el driver y las bibliotecas compatibles con la versión instalada.
- Acceso de escritura a `/opt/lucia-stt`. En esta instalación el directorio pertenece al usuario de Luc.ia; en sistemas donde `/opt` pertenezca a `root`, un administrador debe preparar ese directorio una única vez.

El entorno virtual `venv/`, archivos `.env`, cachés y audios de prueba son locales y no se versionan.

## Instalación como usuario común

Los comandos se ejecutan con el mismo usuario que correrá OpenClaw; no se usa `sudo`.

```bash
git clone git@gitlab.com:egesto/lucia-stt.git /opt/lucia-stt
cd /opt/lucia-stt

python3 -m venv venv
venv/bin/pip install --upgrade pip
venv/bin/pip install faster-whisper

make lint
make install
make enable
make start
make status
```

`make install` copia las unidades a `~/.config/systemd/user/`. `make enable` habilita el socket para la sesión del usuario y `make start` inicia el socket, no el modelo. El servicio se activa al recibir una solicitud y se ejecuta con los parámetros definidos en `lucia-stt.service`.

Antes de instalar, revisar las variables `STT_*` de `lucia-stt.service` si el host no usa CUDA o requiere otro modelo, idioma o tipo de cómputo.

## Actualización desde GitLab

```bash
cd /opt/lucia-stt
git pull --ff-only
make lint
make install
systemctl --user daemon-reload
systemctl --user restart lucia-stt.service
```

El reinicio explícito del servicio hace que el worker cargue la nueva versión del código. Si solo se modificó el código y no las unidades, `make install` y `daemon-reload` no son necesarios.

## Prueba manual

```bash
/opt/lucia-stt/venv/bin/python3 /opt/lucia-stt/stt_socket_client.py /ruta/al/audio.ogg
/opt/lucia-stt/venv/bin/python3 /opt/lucia-stt/stt_socket_client.py /ruta/al/audio.ogg --json
```

## Benchmark

```bash
/opt/lucia-stt/venv/bin/python3 /opt/lucia-stt/stt_benchmark.py \
  --file /ruta/al/audio.ogg --backend fast-socket
```

## Operación

```bash
make status
systemctl --user status lucia-stt.socket lucia-stt.service --no-pager
journalctl --user -u lucia-stt.service -f
```
