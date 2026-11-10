"""
Script auxiliar para generar un icono profesional (.ico) multidisplay
para Optimizador y Compresor Masivo Pro.
"""

import os
from PIL import Image, ImageDraw


def generate_app_icon(output_path: str = "app_icon.ico") -> None:
    # Crear imagen base en alta resolución (256x256)
    size = (256, 256)
    img = Image.new("RGBA", size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Fondo redondeado oscuro estilo Dark Minimalista
    draw.rounded_rectangle([0, 0, 255, 255], radius=44, fill="#1E1E1E", outline="#3B82F6", width=8)

    # Símbolo de rayo / compresión ultra-rápida en cian eléctrico
    cx, cy = 128, 128
    pts = [
        (cx + 15, 38),
        (cx - 56, 134),
        (cx - 5, 134),
        (cx - 36, 218),
        (cx + 68, 112),
        (cx + 15, 112),
    ]
    draw.polygon(pts, fill="#00D2FF")

    # Guardar en formato ICO multidisplay con todas las resoluciones estándar de Windows
    icon_sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    img.save(output_path, format="ICO", sizes=icon_sizes)
    print(f"Icono multidisplay generado con éxito ({os.path.getsize(output_path)} bytes) en: {output_path}")


if __name__ == "__main__":
    generate_app_icon()
