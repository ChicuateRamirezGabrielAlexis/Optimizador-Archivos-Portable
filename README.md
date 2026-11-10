# ⚡ Optimizador y Compresor Masivo Pro (Portable USB)

> Aplicación de escritorio moderna, de alto rendimiento y consumo ultra bajo de recursos (**< 40 MB de memoria RAM**), desarrollada en Python y `customtkinter`, diseñada para ejecutarse de manera **100% portable desde cualquier memoria USB** en Windows sin necesidad de instalación previa.

---

## 🎯 Características Principales

### 1. Interfaz Gráfica de Usuario Premium (`customtkinter`)
- **Estética Dark Mode Minimalista:** Fondo primario `#121212`, tarjetas y contenedores `#1E1E1E`, con bordes sutiles `#2E2E2E` y contrastes de acento eléctrico (`#2563EB`).
- **Icono Portable Dinámico:** Carga automática de `app_icon.ico` tanto en entorno de desarrollo (`.py`) como empaquetado en binario independiente (`sys._MEIPASS`) mediante `get_resource_path()`.
- **Panel Superior de Control:**
  - `CTkSegmentedButton` con selector de categorías: `📋 Todos | 🖼️ Imágenes | 📄 PDFs | 🎬 Videos` con filtrado dinámico en la tabla.
  - Slider interactivo de porcentaje de reducción (10% a 90%) con feedback visual en vivo (*Ligero*, *Equilibrado*, *Máximo Ahorro*).
  - Conmutador (*Switch*) para **"Preservar Calidad Visual Sin Pérdida"** (activado por defecto), adaptando la tasa de compresión a los umbrales perceptuales humanos.
- **Panel Central (Tabla de Lote y Estimación Dinámica):**
  - Contenedor con `CTkScrollableFrame` estilizado.
  - Botones ergonómicos: `📁 Agregar Archivos`, `📂 Agregar Carpeta` (recorrido recursivo) y `🗑️ Limpiar Lista`.
  - Columnas estructuradas:
    - **Nombre de Archivo** (truncamiento inteligente con tooltip visual).
    - **Formato** (badges cromáticos diferenciados para Imagen, PDF y Video).
    - **Tamaño Original** (MB / KB).
    - **% Elegido** (actualizado reactivamente con el slider).
    - **Peso Estimado** (cálculo en tiempo real antes de procesar).
    - **Estado** (`Listo`, `Procesando...`, `Completado`, `Error`).
- **Panel Inferior de Operación y Monitoreo:**
  - Selector de carpeta de salida portable (por defecto `./Optimizado` relativo a la ubicación del ejecutable en la memoria USB).
  - Botón `📁 Abrir Carpeta` para inspección rápida de resultados.
  - Métrica de **Ahorro Total Acumulado** (en MB reales y porcentaje efectivo).
  - Contador de progreso: `Procesados: X / N`.
  - **Monitor de RAM en Tiempo Real:** Badge indicador `🟢 RAM: ~12 MB (< 40 MB)` con telemetría basada en `psutil`.
  - Barra de progreso interactiva (`CTkProgressBar`) y botón de acción `⚡ Reducir Peso` con soporte para cancelación segura (`🛑 Detener Proceso`).

---

## 🧠 Arquitectura de Bajo Consumo de Recursos (< 40 MB RAM)

La aplicación implementa técnicas avanzadas de ingeniería de software para mantener un consumo de memoria mínimo:

1. **Lazy Loading de Bibliotecas Pesadas:** Los motores de procesamiento (`Pillow` y `pypdf`) se importan bajo demanda dentro de sus respectivas funciones operativas, evitando cargar de golpe tablas de fuentes y decodificadores criptográficos al iniciar la GUI.
2. **Streaming y Subprocesos Out-of-Process:** 
   - El procesamiento de video mediante `FFmpeg` corre fuera del heap de Python en un subproceso nativo con `stdout=subprocess.DEVNULL` y `stderr=subprocess.DEVNULL`, garantizando que el streaming de video no ocupe memoria en Python y eliminando cualquier bloqueo de búfer (*buffer deadlocks*).
3. **Recolección Forzada de Basura (`gc.collect()`):** Se ejecuta explícitamente tras procesar cada archivo individual del lote, destruyendo de inmediato búferes de imagen y árboles de objetos PDF.
4. **Recorte de Working Set en Windows (`EmptyWorkingSet`):** Mediante la API de Windows `psapi.EmptyWorkingSet()`, la aplicación solicita al kernel de Windows vaciar páginas de memoria privada innecesarias, reduciendo la memoria física residente (RSS) a rangos de **10 MB a 25 MB** durante toda la ejecución.

---

## ⚙️ Motores de Compresión

| Formato | Tecnología | Estrategia de Optimización |
| :--- | :--- | :--- |
| **Imágenes** (`.jpg`, `.jpeg`, `.png`, `.webp`, `.bmp`, `.tiff`) | `Pillow` | Reoptimización de búferes, stripping de metadatos superfluos, preservación de perfil EXIF de rotación, compresión progresiva en JPEG, compresión de nivel 9 en PNG y codificación de calidad perceptual en WebP. |
| **Documentos PDF** (`.pdf`) | `pypdf` | Compresión de flujos de contenido (`FlateDecode level 9`), deduplicación de objetos idénticos y descarte de referencias huérfanas (`compress_identical_objects`), reoptimización opcional de imágenes internas. |
| **Videos** (`.mp4`, `.mkv`, `.avi`, `.mov`, `.wmv`, `.webm`, etc.) | `FFmpeg` Portable | Transcodificación H.264 optimizada con `-crf 26 -preset faster`, audio AAC a 128 kbps, píxeles en `yuv420p` y banderas de streaming web `+faststart`. |

---

## 📁 Portabilidad USB y Rutas Dinámicas

La aplicación no asume rutas fijas en el disco local (`C:\`). En su lugar, utiliza tres helpers modulares:

```python
# 1. get_resource_path(relative_path):
#    Resuelve recursos internos empaquetados en sys._MEIPASS o directorio del script.
icon = get_resource_path("app_icon.ico")

# 2. get_app_dir():
#    Devuelve la carpeta real donde se encuentra el .exe dentro de la memoria USB.
out_dir = os.path.join(get_app_dir(), "Optimizado")

# 3. get_ffmpeg_location():
#    Localiza ffmpeg.exe buscando en _MEIPASS, en la raíz de la USB, en /bin o en el PATH del sistema.
ffmpeg = get_ffmpeg_location()
```

---

## 📂 Estructura del Proyecto

```text
Optimizador y Compresor Masivo Pro/
├── main.py                   # Código fuente principal, GUI y motores de compresión
├── requirements.txt          # Dependencias oficiales del proyecto
├── build_portable.bat        # Script de compilación PyInstaller OneFile
├── generate_icon.py          # Generador del icono multidisplay (.ico)
├── app_icon.ico              # Icono portable multidisplay (16x16 a 256x256)
├── ffmpeg.exe                # Binario nativo de FFmpeg para compresión de video
├── ffprobe.exe               # Binario complementario de FFmpeg
└── README.md                 # Documentación técnica completa
```

---

## 🚀 Instalación y Uso en Desarrollo

### 1. Prerrequisitos
- Python 3.10 o superior (probado en Python 3.12).
- Sistema Operativo Windows (10/11) o memorias USB en formato NTFS/FAT32/exFAT.

### 2. Instalación de Dependencias
Abre una terminal en el directorio del proyecto y ejecuta:
```bash
pip install -r requirements.txt
```

### 3. Ejecutar la Aplicación
```bash
python main.py
```

---

## 📦 Compilación Portable (.EXE OneFile)

El proyecto incluye el script automatizado `build_portable.bat`, el cual ejecuta la siguiente instrucción exacta de compilación:

```cmd
pyinstaller --noconsole --onefile --add-data "app_icon.ico;." --add-data "ffmpeg.exe;." --add-data "ffprobe.exe;." --icon=app_icon.ico --name "Optimizador_Archivos_Portable" main.py
```

### Pasos para compilar:
1. Haz doble clic en `build_portable.bat`.
2. El script verificará la presencia del icono y de `ffmpeg.exe`. Si faltan, los generará o copiará automáticamente.
3. PyInstaller creará el ejecutable unificado en la carpeta `dist\Optimizador_Archivos_Portable.exe`.
4. **Copia el archivo `Optimizador_Archivos_Portable.exe` a tu memoria USB**: funcionará en cualquier computadora con Windows sin instalar Python ni dependencias.

---

## 🔒 Manejo Seguro de Hilos y Concurrencia

El procesamiento por lotes se ejecuta en un hilo secundario (`threading.Thread(daemon=True)`) conectado con la interfaz mediante una cola sincronizada y segura (`queue.Queue`). Esto garantiza:
- **Cero congelamiento de la GUI:** La interfaz responde con fluidez en todo momento, permitiendo mover la ventana, minimizar o consultar el progreso sin retardos.
- **Cancelación Inmediata:** Si el usuario pulsa `🛑 Detener Proceso`, el evento `threading.Event` interrumpe las operaciones activas y termina de forma segura cualquier proceso hijo de `FFmpeg`.

---

## 📄 Licencia

Proyecto de código abierto desarrollado bajo la licencia MIT. Libre para uso personal, comercial y distribución portable.
