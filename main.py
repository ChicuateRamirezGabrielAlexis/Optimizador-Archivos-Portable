"""
Optimizador y Compresor Masivo Pro (Imágenes, PDFs y Videos)
Versión: 1.0.0 Portable
Diseñado para consumo ultra bajo de memoria (< 40 MB RAM),
interfaz en modo oscuro nativo (#121212 / #1E1E1E) y 100% portable para USB.
"""

from __future__ import annotations

import gc
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from typing import Optional

import customtkinter as ctk
import psutil

# ==============================================================================
# CONFIGURACIÓN Y CONSTANTES GLOBALES
# ==============================================================================

# Extensiones soportadas
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tiff", ".tif"}
PDF_EXTENSIONS = {".pdf"}
VIDEO_EXTENSIONS = {".mp4", ".mkv", ".avi", ".mov", ".wmv", ".flv", ".webm", ".m4v", ".ts"}
ALL_SUPPORTED = IMAGE_EXTENSIONS | PDF_EXTENSIONS | VIDEO_EXTENSIONS

# Paleta de Colores Modo Oscuro Minimalista (#121212 fondo, #1E1E1E contenedores)
COLOR_BG_DARK = "#121212"
COLOR_CONTAINER = "#1E1E1E"
COLOR_CONTAINER_ALT = "#252525"
COLOR_BORDER = "#2E2E2E"
COLOR_ACCENT = "#2563EB"
COLOR_ACCENT_HOVER = "#1D4ED8"
COLOR_SUCCESS = "#10B981"
COLOR_WARNING = "#F59E0B"
COLOR_DANGER = "#EF4444"
COLOR_TEXT_MAIN = "#FFFFFF"
COLOR_TEXT_MUTED = "#9CA3AF"
COLOR_ROW_EVEN = "#1A1A1A"
COLOR_ROW_ODD = "#202020"


# ==============================================================================
# OPTIMIZACIÓN DE MEMORIA RAM Y WORKING SET (< 40 MB)
# ==============================================================================

def trim_memory() -> None:
    """
    Fuerza la recolección de basura y libera el working set de Windows
    para mantener el consumo físico de RAM drásticamente bajo (< 40 MB).
    """
    gc.collect()
    if os.name == "nt":
        try:
            import ctypes
            import ctypes.wintypes

            kernel32 = ctypes.windll.kernel32
            psapi = ctypes.windll.psapi
            kernel32.GetCurrentProcess.restype = ctypes.wintypes.HANDLE
            psapi.EmptyWorkingSet.argtypes = [ctypes.wintypes.HANDLE]
            psapi.EmptyWorkingSet.restype = ctypes.wintypes.BOOL
            h_proc = kernel32.GetCurrentProcess()
            psapi.EmptyWorkingSet(h_proc)
        except Exception:
            pass


# ==============================================================================
# HELPERS DE PORTABILIDAD Y RUTAS USB
# ==============================================================================

def get_resource_path(relative_path: str) -> str:
    """
    Obtiene la ruta absoluta a un recurso dinámico.
    Compatible tanto en desarrollo (.py) como al compilar con PyInstaller (--onefile, sys._MEIPASS).
    """
    base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(base_path, relative_path)


def get_app_dir() -> str:
    """
    Obtiene el directorio base donde reside la aplicación.
    Garantiza que en una memoria USB las carpetas relativas se creen junto al ejecutable.
    """
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


def get_ffmpeg_location() -> Optional[str]:
    """
    Busca el binario portable de ffmpeg.exe en orden de prioridad:
    1. Recursos empaquetados por PyInstaller (_MEIPASS)
    2. Directorio raíz del ejecutable o script (memoria USB)
    3. Subdirectorios 'bin' o 'tools' en la USB
    4. PATH del sistema operativo
    """
    # 1. Empaquetado PyInstaller
    bundled = get_resource_path("ffmpeg.exe")
    if os.path.isfile(bundled):
        return bundled

    # 2. Mismo directorio de la app en la USB
    local_path = os.path.join(get_app_dir(), "ffmpeg.exe")
    if os.path.isfile(local_path):
        return local_path

    # 3. Subcarpetas típicas de utilitarios
    for sub in ("bin", "tools"):
        sub_path = os.path.join(get_app_dir(), sub, "ffmpeg.exe")
        if os.path.isfile(sub_path):
            return sub_path

    # 4. PATH del sistema
    system_ffmpeg = shutil.which("ffmpeg")
    if system_ffmpeg and os.path.isfile(system_ffmpeg):
        return system_ffmpeg

    return None


# ==============================================================================
# UTILIDADES DE ARCHIVO Y ESTIMACIÓN DE PESO
# ==============================================================================

def format_bytes(size_bytes: int) -> str:
    """Convierte bytes a representación legible (B, KB, MB, GB)."""
    if size_bytes < 0:
        return "0.00 B"
    units = ["B", "KB", "MB", "GB", "TB"]
    size = float(size_bytes)
    unit_index = 0
    while size >= 1024.0 and unit_index < len(units) - 1:
        size /= 1024.0
        unit_index += 1
    return f"{size:.2f} {units[unit_index]}"


def classify_file(filepath: str) -> Optional[str]:
    """Identifica la categoría del archivo: 'image', 'pdf', 'video' o None."""
    ext = os.path.splitext(filepath)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        return "image"
    if ext in PDF_EXTENSIONS:
        return "pdf"
    if ext in VIDEO_EXTENSIONS:
        return "video"
    return None


def calc_estimated_size(original_bytes: int, reduction_pct: int, category: str, preserve_quality: bool) -> int:
    """
    Calcula dinámicamente el peso final aproximado en la tabla antes de procesar
    según el porcentaje seleccionado y el conmutador de calidad visual sin pérdida.
    """
    if original_bytes <= 0:
        return 0

    pct = max(10, min(90, reduction_pct))

    if preserve_quality:
        # En modo sin pérdida perceptual, se aplican límites visuales equilibrados
        if category == "image":
            eff_pct = min(pct, 55)
        elif category == "pdf":
            eff_pct = min(pct, 50)
        elif category == "video":
            eff_pct = min(pct, 60)
        else:
            eff_pct = min(pct, 50)
    else:
        # Modo compresión agresiva directa
        eff_pct = pct

    factor = (100.0 - eff_pct) / 100.0
    est = int(original_bytes * factor)
    return max(512, est)


# ==============================================================================
# MOTORES DE COMPRESIÓN MASIVA (Lazy-Loaded para Consumo Mínimo de RAM)
# ==============================================================================

def optimize_image(in_path: str, out_path: str, reduction_pct: int, preserve_quality: bool) -> tuple[bool, int, str]:
    """
    Optimiza imágenes con Pillow: reoptimización de búferes, eliminación de
    metadatos redundantes y preservación de la resolución y calidad perceptual.
    """
    try:
        from PIL import Image, ImageOps

        orig_size = os.path.getsize(in_path)

        with Image.open(in_path) as raw_img:
            # Preservar orientación correcta basada en EXIF
            try:
                img = ImageOps.exif_transpose(raw_img)
            except Exception:
                img = raw_img.copy()

            out_ext = os.path.splitext(out_path)[1].lower()

            if out_ext in (".jpg", ".jpeg"):
                if img.mode in ("RGBA", "P"):
                    img = img.convert("RGB")

                if preserve_quality:
                    # Calidad perceptual alta (88 a 72)
                    quality = max(72, int(90 - (reduction_pct * 0.20)))
                else:
                    # Compresión agresiva (85 a 25)
                    quality = max(25, int(92 - (reduction_pct * 0.75)))

                img.save(out_path, format="JPEG", quality=quality, optimize=True, progressive=True)

            elif out_ext == ".png":
                if preserve_quality:
                    img.save(out_path, format="PNG", optimize=True, compress_level=9)
                else:
                    if reduction_pct >= 40 and img.mode in ("RGB", "RGBA"):
                        quantized = img.convert("P", palette=Image.Palette.ADAPTIVE, colors=256)
                        quantized.save(out_path, format="PNG", optimize=True, compress_level=9)
                        del quantized
                    else:
                        img.save(out_path, format="PNG", optimize=True, compress_level=9)

            elif out_ext == ".webp":
                if preserve_quality:
                    quality = max(75, int(92 - (reduction_pct * 0.20)))
                else:
                    quality = max(25, int(90 - (reduction_pct * 0.72)))
                img.save(out_path, format="WEBP", quality=quality, method=6)

            else:
                img.save(out_path, optimize=True)

            del img

        final_size = os.path.getsize(out_path)
        # Si el archivo comprimido resultó mayor al original, conservar el original
        if final_size >= orig_size:
            shutil.copy2(in_path, out_path)
            final_size = orig_size

        return True, final_size, ""
    except Exception as exc:
        return False, 0, str(exc)
    finally:
        trim_memory()


def optimize_pdf(in_path: str, out_path: str, reduction_pct: int, preserve_quality: bool) -> tuple[bool, int, str]:
    """
    Optimiza PDFs con pypdf: comprime flujos de contenido, deduplica objetos idénticos
    y reoptimiza imágenes internas.
    """
    try:
        import pypdf

        orig_size = os.path.getsize(in_path)
        reader = pypdf.PdfReader(in_path)
        writer = pypdf.PdfWriter(clone_from=in_path)

        # 1. Comprimir flujos de contenido en cada página
        for page in writer.pages:
            try:
                page.compress_content_streams(level=9)
            except Exception:
                pass

            # 2. Reoptimizar imágenes embebidas si la reducción es significativa
            if not preserve_quality or reduction_pct >= 40:
                try:
                    for img_obj in page.images:
                        if hasattr(img_obj, "replace") and not getattr(img_obj, "is_inline", False):
                            pil_img = img_obj.image
                            if pil_img:
                                q = max(35, int(85 - (reduction_pct * 0.50)))
                                img_obj.replace(pil_img, quality=q, optimize=True)
                except Exception:
                    pass

        # 3. Deduplicar objetos idénticos y limpiar referencias huérfanas
        try:
            writer.compress_identical_objects(remove_duplicates=True, remove_unreferenced=True)
        except TypeError:
            try:
                writer.compress_identical_objects(remove_identicals=True, remove_orphans=True)
            except Exception:
                writer.compress_identical_objects()

        with open(out_path, "wb") as f_out:
            writer.write(f_out)

        del writer
        del reader

        final_size = os.path.getsize(out_path)
        if final_size >= orig_size:
            shutil.copy2(in_path, out_path)
            final_size = orig_size

        return True, final_size, ""
    except Exception as exc:
        return False, 0, str(exc)
    finally:
        trim_memory()


def optimize_video(
    in_path: str,
    out_path: str,
    reduction_pct: int,
    preserve_quality: bool,
    ffmpeg_exe: str,
    cancel_event: threading.Event,
) -> tuple[bool, int, str]:
    """
    Optimiza videos mediante subprocesos de FFmpeg portable con parámetros
    altamente eficientes (-crf 26 -preset faster).
    """
    if not ffmpeg_exe or not os.path.isfile(ffmpeg_exe):
        return False, 0, "ffmpeg.exe no encontrado en memoria USB ni en sistema"

    try:
        orig_size = os.path.getsize(in_path)

        if preserve_quality:
            # Rango CRF 23 - 27 (equilibrio perceptual óptimo)
            crf = 23 + int((reduction_pct / 90.0) * 4)
        else:
            # Rango CRF 26 - 35 (compresión más agresiva)
            crf = 26 + int((reduction_pct / 90.0) * 9)

        cmd = [
            ffmpeg_exe,
            "-y",
            "-i",
            in_path,
            "-c:v",
            "libx264",
            "-crf",
            str(crf),
            "-preset",
            "faster",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            "-pix_fmt",
            "yuv420p",
            out_path,
        ]

        startupinfo = None
        creationflags = 0
        if os.name == "nt":
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            creationflags = subprocess.CREATE_NO_WINDOW

        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            startupinfo=startupinfo,
            creationflags=creationflags,
        )

        while proc.poll() is None:
            if cancel_event.is_set():
                proc.kill()
                if os.path.isfile(out_path):
                    try:
                        os.remove(out_path)
                    except OSError:
                        pass
                return False, 0, "Cancelado por el usuario"
            time.sleep(0.1)

        if proc.returncode != 0:
            return False, 0, f"Error FFmpeg (código {proc.returncode})"

        final_size = os.path.getsize(out_path)
        if final_size >= orig_size:
            shutil.copy2(in_path, out_path)
            final_size = orig_size

        return True, final_size, ""
    except Exception as exc:
        return False, 0, str(exc)
    finally:
        trim_memory()


# ==============================================================================
# MODELO DE DATOS DE ARCHIVO
# ==============================================================================

class BatchItem:
    """Representa un archivo individual en la cola de procesamiento."""

    def __init__(self, file_path: str):
        self.file_path = file_path
        self.filename = os.path.basename(file_path)
        self.ext = os.path.splitext(self.filename)[1].upper().replace(".", "")
        self.category = classify_file(file_path) or "unknown"
        self.original_size = os.path.getsize(file_path)
        self.chosen_pct = 40
        self.estimated_size = 0
        self.final_size: Optional[int] = None
        self.status = "Listo"
        self.error_detail = ""

        # Referencias a widgets en la tabla
        self.frame_row: Optional[ctk.CTkFrame] = None
        self.lbl_pct: Optional[ctk.CTkLabel] = None
        self.lbl_est: Optional[ctk.CTkLabel] = None
        self.lbl_status: Optional[ctk.CTkLabel] = None


# ==============================================================================
# INTERFAZ GRÁFICA PRINCIPAL (CustomTkinter)
# ==============================================================================

class ModernCompressorApp(ctk.CTk):
    """Aplicación de escritorio optimizada para bajo consumo de RAM (< 40 MB) y portabilidad USB."""

    def __init__(self):
        super().__init__()

        # Configuración estética base
        ctk.set_appearance_mode("Dark")
        ctk.set_default_color_theme("blue")

        self.title("Optimizador y Compresor Masivo Pro")
        self.geometry("1060x700")
        self.minsize(920, 600)
        self.configure(fg_color=COLOR_BG_DARK)

        # Carga de icono dinámico portable
        self._load_app_icon()

        # Variables de estado
        self.items: list[BatchItem] = []
        self.current_filter = "📋 Todos"
        self.reduction_pct_var = ctk.IntVar(value=40)
        self.preserve_quality_var = ctk.BooleanVar(value=True)

        default_output = os.path.join(get_app_dir(), "Optimizado")
        self.output_dir_var = ctk.StringVar(value=default_output)

        self.total_saved_bytes = 0
        self.total_processed_orig_bytes = 0
        self.is_processing = False
        self.cancel_event = threading.Event()
        self.msg_queue: queue.Queue = queue.Queue()

        # Construir Interfaz
        self._build_top_panel()
        self._build_central_panel()
        self._build_bottom_panel()

        # Liberar memoria inicial
        trim_memory()

        # Iniciar ciclo de eventos y monitor de memoria
        self.after(60, self._process_queue_events)
        self.after(1000, self._update_ram_monitor)

    def _load_app_icon(self) -> None:
        """Carga el icono portable usando iconbitmap y get_resource_path."""
        icon_path = get_resource_path("app_icon.ico")
        if os.path.isfile(icon_path):
            try:
                self.iconbitmap(icon_path)
            except Exception:
                pass

    # --------------------------------------------------------------------------
    # CONSTRUCCIÓN DE PANELES
    # --------------------------------------------------------------------------

    def _build_top_panel(self) -> None:
        """Panel Superior: SegmentedButton, Slider de reducción y Switch de Calidad."""
        top_card = ctk.CTkFrame(
            self,
            fg_color=COLOR_CONTAINER,
            corner_radius=10,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        top_card.pack(fill="x", padx=16, pady=(14, 8))

        # Encabezado superior con título y badge de consumo
        header_frame = ctk.CTkFrame(top_card, fg_color="transparent")
        header_frame.pack(fill="x", padx=16, pady=(10, 6))

        title_lbl = ctk.CTkLabel(
            header_frame,
            text="⚡ OPTIMIZADOR Y COMPRESOR MASIVO PRO",
            font=ctk.CTkFont(family="Segoe UI", size=16, weight="bold"),
            text_color=COLOR_TEXT_MAIN,
        )
        title_lbl.pack(side="left")

        usb_badge = ctk.CTkLabel(
            header_frame,
            text="100% PORTABLE USB  |  RAM < 40 MB",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#60A5FA",
            fg_color="#1E293B",
            corner_radius=6,
            padx=8,
            pady=2,
        )
        usb_badge.pack(side="right")

        # Fila de controles
        controls_frame = ctk.CTkFrame(top_card, fg_color="transparent")
        controls_frame.pack(fill="x", padx=16, pady=(4, 12))

        # 1. SegmentedButton de Categorías
        cat_box = ctk.CTkFrame(controls_frame, fg_color="transparent")
        cat_box.pack(side="left", padx=(0, 20))

        cat_lbl = ctk.CTkLabel(
            cat_box,
            text="Categoría:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_TEXT_MUTED,
        )
        cat_lbl.pack(anchor="w", pady=(0, 2))

        self.seg_button = ctk.CTkSegmentedButton(
            cat_box,
            values=["📋 Todos", "🖼️ Imágenes", "📄 PDFs", "🎬 Videos"],
            command=self._on_filter_changed,
            selected_color=COLOR_ACCENT,
            selected_hover_color=COLOR_ACCENT_HOVER,
            unselected_color="#2A2A2A",
            unselected_hover_color="#333333",
            font=ctk.CTkFont(family="Segoe UI", size=12),
        )
        self.seg_button.set("📋 Todos")
        self.seg_button.pack(anchor="w")

        # 2. Slider interactivo de porcentaje de reducción (10% a 90%)
        slider_box = ctk.CTkFrame(controls_frame, fg_color="transparent")
        slider_box.pack(side="left", fill="x", expand=True, padx=(0, 20))

        slider_header = ctk.CTkFrame(slider_box, fg_color="transparent")
        slider_header.pack(fill="x", pady=(0, 2))

        slider_title = ctk.CTkLabel(
            slider_header,
            text="Porcentaje de Reducción:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_TEXT_MUTED,
        )
        slider_title.pack(side="left")

        self.slider_val_lbl = ctk.CTkLabel(
            slider_header,
            text="40% (Equilibrado)",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color="#38BDF8",
        )
        self.slider_val_lbl.pack(side="right")

        self.slider = ctk.CTkSlider(
            slider_box,
            from_=10,
            to=90,
            number_of_steps=16,
            variable=self.reduction_pct_var,
            command=self._on_slider_moved,
            button_color=COLOR_ACCENT,
            button_hover_color=COLOR_ACCENT_HOVER,
            progress_color=COLOR_ACCENT,
            fg_color="#333333",
        )
        self.slider.pack(fill="x")

        # 3. Switch de Preservación de Calidad Visual Sin Pérdida
        switch_box = ctk.CTkFrame(controls_frame, fg_color="transparent")
        switch_box.pack(side="right", padx=(0, 0))

        switch_lbl = ctk.CTkLabel(
            switch_box,
            text="Calidad Visual:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_TEXT_MUTED,
        )
        switch_lbl.pack(anchor="w", pady=(0, 2))

        self.quality_switch = ctk.CTkSwitch(
            switch_box,
            text="Preservar Calidad Visual Sin Pérdida",
            variable=self.preserve_quality_var,
            command=self._on_switch_toggled,
            onvalue=True,
            offvalue=False,
            progress_color=COLOR_SUCCESS,
            font=ctk.CTkFont(family="Segoe UI", size=12),
        )
        self.quality_switch.pack(anchor="w")

    def _build_central_panel(self) -> None:
        """Panel Central: Botones de adición, barra de herramientas y tabla interactiva."""
        center_card = ctk.CTkFrame(
            self,
            fg_color=COLOR_CONTAINER,
            corner_radius=10,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        center_card.pack(fill="both", expand=True, padx=16, pady=4)

        # Barra de herramientas superior de la tabla
        toolbar = ctk.CTkFrame(center_card, fg_color="transparent")
        toolbar.pack(fill="x", padx=14, pady=(10, 8))

        btn_files = ctk.CTkButton(
            toolbar,
            text="📁 Agregar Archivos",
            command=self._add_files_dialog,
            fg_color="#2563EB",
            hover_color="#1D4ED8",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            height=32,
            width=150,
        )
        btn_files.pack(side="left", padx=(0, 8))

        btn_folder = ctk.CTkButton(
            toolbar,
            text="📂 Agregar Carpeta",
            command=self._add_folder_dialog,
            fg_color="#374151",
            hover_color="#4B5563",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            height=32,
            width=150,
        )
        btn_folder.pack(side="left", padx=(0, 8))

        btn_clear = ctk.CTkButton(
            toolbar,
            text="🗑️ Limpiar Lista",
            command=self._clear_list,
            fg_color="#1F2937",
            hover_color="#374151",
            text_color="#F87171",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            height=32,
            width=120,
        )
        btn_clear.pack(side="left")

        self.table_counter_lbl = ctk.CTkLabel(
            toolbar,
            text="0 archivos en lote (0.00 MB)",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLOR_TEXT_MUTED,
        )
        self.table_counter_lbl.pack(side="right", padx=6)

        # Cabecera de la tabla con columnas proporcionadas
        header_row = ctk.CTkFrame(center_card, fg_color=COLOR_CONTAINER_ALT, height=34, corner_radius=6)
        header_row.pack(fill="x", padx=12, pady=(0, 4))
        header_row.pack_propagate(False)

        col_weights = [
            ("Nombre de Archivo", 380, "w", 12),
            ("Formato", 90, "center", 0),
            ("Tamaño Original", 130, "e", 0),
            ("% Elegido", 90, "center", 0),
            ("Peso Estimado", 130, "e", 0),
            ("Estado", 150, "center", 12),
        ]

        for title, width, anchor, pad in col_weights:
            lbl = ctk.CTkLabel(
                header_row,
                text=title,
                font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
                text_color=COLOR_TEXT_MUTED,
                width=width,
                anchor=anchor,
            )
            lbl.pack(side="left", padx=pad, fill="y")

        # Contenedor desplazable de filas
        self.scroll_frame = ctk.CTkScrollableFrame(
            center_card,
            fg_color="#171717",
            corner_radius=6,
            border_width=1,
            border_color="#262626",
        )
        self.scroll_frame.pack(fill="both", expand=True, padx=12, pady=(0, 10))

        # Mensaje de lista vacía
        self.empty_lbl = ctk.CTkLabel(
            self.scroll_frame,
            text="📂 No hay archivos agregados al lote.\nHaz clic en '📁 Agregar Archivos' o '📂 Agregar Carpeta' para comenzar.",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="#6B7280",
            justify="center",
        )
        self.empty_lbl.pack(pady=60)

    def _build_bottom_panel(self) -> None:
        """Panel Inferior: Ruta de salida portable, métrica de ahorro, progreso y botón principal."""
        bottom_card = ctk.CTkFrame(
            self,
            fg_color=COLOR_CONTAINER,
            corner_radius=10,
            border_width=1,
            border_color=COLOR_BORDER,
        )
        bottom_card.pack(fill="x", padx=16, pady=(4, 14))

        # Fila 1: Selector de ruta de salida portable
        out_frame = ctk.CTkFrame(bottom_card, fg_color="transparent")
        out_frame.pack(fill="x", padx=14, pady=(10, 6))

        out_lbl = ctk.CTkLabel(
            out_frame,
            text="Ruta de Salida Portable:",
            font=ctk.CTkFont(family="Segoe UI", size=12, weight="bold"),
            text_color=COLOR_TEXT_MUTED,
        )
        out_lbl.pack(side="left", padx=(0, 10))

        self.out_entry = ctk.CTkEntry(
            out_frame,
            textvariable=self.output_dir_var,
            font=ctk.CTkFont(family="Consolas", size=11),
            fg_color="#181818",
            border_color="#333333",
            height=30,
        )
        self.out_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        btn_browse = ctk.CTkButton(
            out_frame,
            text="📂 Examinar",
            command=self._browse_output_dir,
            fg_color="#374151",
            hover_color="#4B5563",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            width=90,
            height=30,
        )
        btn_browse.pack(side="left", padx=(0, 6))

        btn_open = ctk.CTkButton(
            out_frame,
            text="📁 Abrir Carpeta",
            command=self._open_output_dir,
            fg_color="#1E293B",
            hover_color="#334155",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            width=100,
            height=30,
        )
        btn_open.pack(side="left")

        # Fila 2: Métricas de Ahorro y Monitor de Memoria RAM
        metrics_frame = ctk.CTkFrame(bottom_card, fg_color="transparent")
        metrics_frame.pack(fill="x", padx=14, pady=4)

        self.savings_lbl = ctk.CTkLabel(
            metrics_frame,
            text="Ahorro Total Acumulado: 0.00 MB (0.0%)",
            font=ctk.CTkFont(family="Segoe UI", size=13, weight="bold"),
            text_color=COLOR_SUCCESS,
        )
        self.savings_lbl.pack(side="left")

        self.ram_lbl = ctk.CTkLabel(
            metrics_frame,
            text="🟢 RAM: Calculando... (< 40 MB)",
            font=ctk.CTkFont(family="Segoe UI", size=11, weight="bold"),
            text_color="#34D399",
            fg_color="#064E3B",
            corner_radius=6,
            padx=8,
            pady=2,
        )
        self.ram_lbl.pack(side="right")

        self.processed_counter_lbl = ctk.CTkLabel(
            metrics_frame,
            text="Procesados: 0 / 0",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLOR_TEXT_MUTED,
        )
        self.processed_counter_lbl.pack(side="right", padx=16)

        # Fila 3: Barra de Progreso y Estado
        progress_frame = ctk.CTkFrame(bottom_card, fg_color="transparent")
        progress_frame.pack(fill="x", padx=14, pady=4)

        self.progress_bar = ctk.CTkProgressBar(
            progress_frame,
            fg_color="#2A2A2A",
            progress_color=COLOR_ACCENT,
            height=10,
        )
        self.progress_bar.set(0.0)
        self.progress_bar.pack(fill="x")

        # Fila 4: Etiqueta de estado y Botón de Acción Principal
        action_frame = ctk.CTkFrame(bottom_card, fg_color="transparent")
        action_frame.pack(fill="x", padx=14, pady=(6, 10))

        self.status_detail_lbl = ctk.CTkLabel(
            action_frame,
            text="Listo para optimizar lote.",
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLOR_TEXT_MUTED,
        )
        self.status_detail_lbl.pack(side="left")

        self.btn_action = ctk.CTkButton(
            action_frame,
            text="⚡ Reducir Peso",
            command=self._on_action_clicked,
            fg_color=COLOR_ACCENT,
            hover_color=COLOR_ACCENT_HOVER,
            font=ctk.CTkFont(family="Segoe UI", size=14, weight="bold"),
            height=38,
            width=180,
        )
        self.btn_action.pack(side="right")

    # --------------------------------------------------------------------------
    # EVENTOS Y GESTIÓN DE LA TABLA
    # --------------------------------------------------------------------------

    def _on_slider_moved(self, value: float) -> None:
        """Actualiza la etiqueta del slider y recalcula los pesos estimados."""
        pct = int(value)
        desc = "Ligero" if pct < 30 else ("Equilibrado" if pct <= 60 else "Máximo Ahorro")
        self.slider_val_lbl.configure(text=f"{pct}% ({desc})")
        self._recalculate_all_estimates()

    def _on_switch_toggled(self) -> None:
        """Recalcula estimaciones al activar o desactivar la calidad perceptual."""
        self._recalculate_all_estimates()

    def _on_filter_changed(self, value: str) -> None:
        """Filtra la visibilidad de los elementos de la tabla."""
        self.current_filter = value
        self._apply_category_filter()

    def _apply_category_filter(self) -> None:
        """Oculta o muestra filas según la categoría seleccionada."""
        category_map = {
            "🖼️ Imágenes": "image",
            "📄 PDFs": "pdf",
            "🎬 Videos": "video",
        }
        target_cat = category_map.get(self.current_filter)

        for item in self.items:
            if item.frame_row is None:
                continue
            if target_cat is None or item.category == target_cat:
                item.frame_row.pack(fill="x", padx=4, pady=2)
            else:
                item.frame_row.pack_forget()

    def _recalculate_all_estimates(self) -> None:
        """Recalcula dinámicamente el peso estimado para cada archivo del lote."""
        pct = self.reduction_pct_var.get()
        preserve = self.preserve_quality_var.get()

        for item in self.items:
            item.chosen_pct = pct
            item.estimated_size = calc_estimated_size(item.original_size, pct, item.category, preserve)

            if item.lbl_pct is not None:
                item.lbl_pct.configure(text=f"{pct}%")
            if item.lbl_est is not None:
                item.lbl_est.configure(text=format_bytes(item.estimated_size))

    def _add_files_dialog(self) -> None:
        """Abre diálogo para seleccionar archivos individuales."""
        from tkinter import filedialog

        filetypes = [
            ("Todos los compatibles", "*.jpg;*.jpeg;*.png;*.webp;*.pdf;*.mp4;*.mkv;*.avi;*.mov;*.wmv;*.flv;*.webm"),
            ("Imágenes (*.jpg, *.png, *.webp)", "*.jpg;*.jpeg;*.png;*.webp;*.bmp;*.tiff"),
            ("Documentos PDF (*.pdf)", "*.pdf"),
            ("Videos (*.mp4, *.mkv, *.avi, *.mov)", "*.mp4;*.mkv;*.avi;*.mov;*.wmv;*.flv;*.webm"),
            ("Todos los archivos", "*.*"),
        ]
        paths = filedialog.askopenfilenames(title="Seleccionar archivos a optimizar", filetypes=filetypes)
        if paths:
            self._add_files_to_batch(paths)

    def _add_folder_dialog(self) -> None:
        """Abre diálogo para agregar recursivamente todos los archivos de una carpeta."""
        from tkinter import filedialog

        folder = filedialog.askdirectory(title="Seleccionar carpeta a optimizar")
        if folder:
            collected = []
            for root, _, files in os.walk(folder):
                for f in files:
                    ext = os.path.splitext(f)[1].lower()
                    if ext in ALL_SUPPORTED:
                        collected.append(os.path.join(root, f))
            if collected:
                self._add_files_to_batch(collected)

    def _add_files_to_batch(self, paths: list[str]) -> None:
        """Agrega archivos validados a la lista y crea sus filas en la tabla."""
        existing_paths = {item.file_path for item in self.items}
        new_items = []

        pct = self.reduction_pct_var.get()
        preserve = self.preserve_quality_var.get()

        for p in paths:
            abs_path = os.path.abspath(p)
            if abs_path in existing_paths or not os.path.isfile(abs_path):
                continue
            cat = classify_file(abs_path)
            if not cat:
                continue

            item = BatchItem(abs_path)
            item.chosen_pct = pct
            item.estimated_size = calc_estimated_size(item.original_size, pct, item.category, preserve)
            new_items.append(item)
            existing_paths.add(abs_path)

        if not new_items:
            return

        # Ocultar placeholder si es la primera adición
        if not self.items:
            self.empty_lbl.pack_forget()

        for item in new_items:
            self.items.append(item)
            self._create_table_row(item)

        self._update_batch_counters()
        self._apply_category_filter()
        trim_memory()

    def _create_table_row(self, item: BatchItem) -> None:
        """Crea el widget de una fila individual en el scroll frame."""
        row_idx = len(self.items) % 2
        bg_color = COLOR_ROW_EVEN if row_idx == 0 else COLOR_ROW_ODD

        row = ctk.CTkFrame(self.scroll_frame, fg_color=bg_color, corner_radius=6, height=34)
        row.pack(fill="x", padx=4, pady=2)
        row.pack_propagate(False)
        item.frame_row = row

        # Columna 1: Nombre (truncado si excede el ancho visual)
        disp_name = item.filename
        if len(disp_name) > 42:
            disp_name = disp_name[:39] + "..."

        lbl_name = ctk.CTkLabel(
            row,
            text=disp_name,
            font=ctk.CTkFont(family="Segoe UI", size=12),
            text_color=COLOR_TEXT_MAIN,
            width=380,
            anchor="w",
        )
        lbl_name.pack(side="left", padx=12, fill="y")

        # Columna 2: Formato Badge
        badge_colors = {
            "image": ("#0284C7", "#E0F2FE"),
            "pdf": ("#B91C1C", "#FEE2E2"),
            "video": ("#7C3AED", "#EDE9FE"),
        }
        bg_badge, fg_badge = badge_colors.get(item.category, ("#374151", "#FFFFFF"))

        lbl_fmt = ctk.CTkLabel(
            row,
            text=item.ext,
            font=ctk.CTkFont(family="Segoe UI", size=10, weight="bold"),
            text_color=fg_badge,
            fg_color=bg_badge,
            corner_radius=4,
            width=70,
            height=20,
        )
        lbl_fmt.pack(side="left", padx=10)

        # Columna 3: Tamaño Original
        lbl_orig = ctk.CTkLabel(
            row,
            text=format_bytes(item.original_size),
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#D1D5DB",
            width=130,
            anchor="e",
        )
        lbl_orig.pack(side="left", padx=0, fill="y")

        # Columna 4: % Elegido
        item.lbl_pct = ctk.CTkLabel(
            row,
            text=f"{item.chosen_pct}%",
            font=ctk.CTkFont(family="Consolas", size=11, weight="bold"),
            text_color="#38BDF8",
            width=90,
            anchor="center",
        )
        item.lbl_pct.pack(side="left", padx=0, fill="y")

        # Columna 5: Peso Estimado (calculado automáticamente)
        item.lbl_est = ctk.CTkLabel(
            row,
            text=format_bytes(item.estimated_size),
            font=ctk.CTkFont(family="Consolas", size=11),
            text_color="#A7F3D0",
            width=130,
            anchor="e",
        )
        item.lbl_est.pack(side="left", padx=0, fill="y")

        # Columna 6: Estado
        item.lbl_status = ctk.CTkLabel(
            row,
            text="Listo",
            font=ctk.CTkFont(family="Segoe UI", size=11),
            text_color=COLOR_TEXT_MUTED,
            width=150,
            anchor="center",
        )
        item.lbl_status.pack(side="left", padx=12, fill="y")

    def _clear_list(self) -> None:
        """Limpia todos los elementos de la tabla si no hay proceso activo."""
        if self.is_processing:
            return

        for item in self.items:
            if item.frame_row:
                item.frame_row.destroy()

        self.items.clear()
        self.total_saved_bytes = 0
        self.total_processed_orig_bytes = 0
        self.progress_bar.set(0.0)
        self.empty_lbl.pack(pady=60)
        self._update_batch_counters()
        self.savings_lbl.configure(text="Ahorro Total Acumulado: 0.00 MB (0.0%)")
        self.processed_counter_lbl.configure(text="Procesados: 0 / 0")
        self.status_detail_lbl.configure(text="Lista vacía.")
        trim_memory()

    def _update_batch_counters(self) -> None:
        """Actualiza el contador superior de archivos cargados y su peso total."""
        count = len(self.items)
        total_size = sum(it.original_size for it in self.items)
        self.table_counter_lbl.configure(
            text=f"{count} {'archivo' if count == 1 else 'archivos'} en lote ({format_bytes(total_size)})"
        )

    # --------------------------------------------------------------------------
    # GESTIÓN DE RUTA DE SALIDA PORTABLE
    # --------------------------------------------------------------------------

    def _browse_output_dir(self) -> None:
        """Permite al usuario seleccionar una nueva carpeta de salida."""
        from tkinter import filedialog

        chosen = filedialog.askdirectory(
            title="Seleccionar carpeta de salida para optimizados",
            initialdir=self.output_dir_var.get(),
        )
        if chosen:
            self.output_dir_var.set(os.path.abspath(chosen))

    def _open_output_dir(self) -> None:
        """Abre la carpeta de salida en el explorador de archivos nativo."""
        out_dir = self.output_dir_var.get()
        os.makedirs(out_dir, exist_ok=True)
        if os.name == "nt":
            os.startfile(out_dir)
        else:
            subprocess.run(["xdg-open", out_dir])

    # --------------------------------------------------------------------------
    # CONTROL DE PROCESAMIENTO POR HILOS Y COLA
    # --------------------------------------------------------------------------

    def _on_action_clicked(self) -> None:
        """Maneja el clic en el botón principal (Iniciar / Cancelar)."""
        if self.is_processing:
            self._cancel_processing()
        else:
            self._start_processing()

    def _start_processing(self) -> None:
        """Inicia el procesamiento masivo en un hilo secundario."""
        pending_items = [it for it in self.items if it.status != "Completado"]
        if not pending_items:
            self.status_detail_lbl.configure(text="No hay archivos pendientes para procesar.")
            return

        out_dir = self.output_dir_var.get().strip()
        if not out_dir:
            out_dir = os.path.join(get_app_dir(), "Optimizado")
            self.output_dir_var.set(out_dir)

        try:
            os.makedirs(out_dir, exist_ok=True)
        except Exception as exc:
            self.status_detail_lbl.configure(text=f"Error creando carpeta de salida: {exc}")
            return

        self.is_processing = True
        self.cancel_event.clear()
        self.btn_action.configure(
            text="🛑 Detener Proceso",
            fg_color=COLOR_DANGER,
            hover_color="#DC2626",
        )
        self.status_detail_lbl.configure(text="Iniciando optimización...")

        # Iniciar hilo secundario
        worker_thread = threading.Thread(
            target=self._worker_loop,
            args=(pending_items, out_dir),
            daemon=True,
        )
        worker_thread.start()

    def _cancel_processing(self) -> None:
        """Solicita la cancelación inmediata del hilo secundario."""
        self.cancel_event.set()
        self.status_detail_lbl.configure(text="Deteniendo proceso...")
        self.btn_action.configure(state="disabled")

    def _worker_loop(self, items_to_process: list[BatchItem], output_dir: str) -> None:
        """Bucle ejecutado en hilo secundario para procesar archivos uno a uno."""
        ffmpeg_exe = get_ffmpeg_location()
        total_to_process = len(items_to_process)

        for idx, item in enumerate(items_to_process, start=1):
            if self.cancel_event.is_set():
                break

            # Notificar inicio de archivo
            self.msg_queue.put(("START_FILE", item, idx, total_to_process))

            # Preparar nombre y ruta destino
            base_name = item.filename
            out_file_path = os.path.join(output_dir, base_name)

            success = False
            final_size = item.original_size
            error_msg = ""

            try:
                if item.category == "image":
                    success, final_size, error_msg = optimize_image(
                        item.file_path,
                        out_file_path,
                        item.chosen_pct,
                        self.preserve_quality_var.get(),
                    )
                elif item.category == "pdf":
                    success, final_size, error_msg = optimize_pdf(
                        item.file_path,
                        out_file_path,
                        item.chosen_pct,
                        self.preserve_quality_var.get(),
                    )
                elif item.category == "video":
                    success, final_size, error_msg = optimize_video(
                        item.file_path,
                        out_file_path,
                        item.chosen_pct,
                        self.preserve_quality_var.get(),
                        ffmpeg_exe or "",
                        self.cancel_event,
                    )
                else:
                    success, final_size, error_msg = False, 0, "Formato no soportado"

            except Exception as exc:
                success = False
                error_msg = str(exc)

            # Notificar resultado del archivo
            self.msg_queue.put(("END_FILE", item, success, final_size, error_msg, idx, total_to_process))

            # FORZAR RECOLECCIÓN DE BASURA Y LIBERACIÓN DE MEMORIA TRAS CADA ARCHIVO (< 40 MB)
            trim_memory()

        # Notificar fin de lote completo
        self.msg_queue.put(("BATCH_FINISHED",))

    def _process_queue_events(self) -> None:
        """Procesa los eventos enviados desde el hilo de trabajo hacia la GUI."""
        try:
            while True:
                msg = self.msg_queue.get_nowait()
                ev_type = msg[0]

                if ev_type == "START_FILE":
                    _, item, idx, total = msg
                    item.status = "Procesando"
                    if item.lbl_status:
                        item.lbl_status.configure(text="⏳ Procesando...", text_color=COLOR_WARNING)
                    self.status_detail_lbl.configure(text=f"Procesando ({idx}/{total}): {item.filename}")
                    progress = (idx - 1) / max(1, total)
                    self.progress_bar.set(progress)

                elif ev_type == "END_FILE":
                    _, item, success, final_size, error_msg, idx, total = msg
                    if success:
                        item.status = "Completado"
                        item.final_size = final_size
                        saved = item.original_size - final_size
                        ratio = (saved / max(1, item.original_size)) * 100.0

                        if item.lbl_status:
                            item.lbl_status.configure(
                                text=f"✔ {format_bytes(final_size)} (-{ratio:.1f}%)",
                                text_color=COLOR_SUCCESS,
                            )

                        self.total_saved_bytes += max(0, saved)
                        self.total_processed_orig_bytes += item.original_size
                    else:
                        item.status = "Error"
                        item.error_detail = error_msg
                        if item.lbl_status:
                            item.lbl_status.configure(
                                text="✖ Error",
                                text_color=COLOR_DANGER,
                            )

                    # Actualizar métricas acumuladas
                    tot_saved_mb = self.total_saved_bytes
                    tot_orig = self.total_processed_orig_bytes
                    overall_ratio = (tot_saved_mb / max(1, tot_orig)) * 100.0 if tot_orig > 0 else 0.0

                    self.savings_lbl.configure(
                        text=f"Ahorro Total Acumulado: {format_bytes(tot_saved_mb)} ({overall_ratio:.1f}%)"
                    )

                    completed_count = sum(1 for it in self.items if it.status == "Completado")
                    self.processed_counter_lbl.configure(
                        text=f"Procesados: {completed_count} / {len(self.items)}"
                    )

                    progress = idx / max(1, total)
                    self.progress_bar.set(progress)

                elif ev_type == "BATCH_FINISHED":
                    self.is_processing = False
                    self.btn_action.configure(
                        text="⚡ Reducir Peso",
                        fg_color=COLOR_ACCENT,
                        hover_color=COLOR_ACCENT_HOVER,
                        state="normal",
                    )
                    self.progress_bar.set(1.0)
                    if self.cancel_event.is_set():
                        self.status_detail_lbl.configure(text="Proceso detenido por el usuario.")
                    else:
                        self.status_detail_lbl.configure(text="¡Lote completado con éxito!")
                    trim_memory()

                self.msg_queue.task_done()

        except queue.Empty:
            pass

        # Continuar escuchando la cola
        self.after(50, self._process_queue_events)

    # --------------------------------------------------------------------------
    # MONITOR DE MEMORIA RAM EN TIEMPO REAL (< 40 MB)
    # --------------------------------------------------------------------------

    def _update_ram_monitor(self) -> None:
        """Lee el uso de memoria RAM del proceso y lo muestra en la interfaz."""
        try:
            process = psutil.Process()
            mem_mb = process.memory_info().rss / (1024.0 * 1024.0)

            if mem_mb < 40.0:
                color_text = "#34D399"
                color_bg = "#064E3B"
                badge = f"🟢 RAM: {mem_mb:.1f} MB (< 40 MB)"
            else:
                color_text = "#FBBF24"
                color_bg = "#78350F"
                badge = f"🟡 RAM: {mem_mb:.1f} MB"

            self.ram_lbl.configure(text=badge, text_color=color_text, fg_color=color_bg)
        except Exception:
            pass

        # Forzar trim periódico si la app está en espera
        if not self.is_processing:
            trim_memory()

        self.after(1500, self._update_ram_monitor)


# ==============================================================================
# PUNTO DE ENTRADA PRINCIPAL
# ==============================================================================

def main() -> None:
    """Función de arranque de la aplicación."""
    trim_memory()
    app = ModernCompressorApp()
    app.mainloop()


if __name__ == "__main__":
    main()
