# app/ai/ocr.py
from PIL import Image, ImageOps, ImageFilter
import pytesseract
from io import BytesIO

def preprocess(img: Image.Image) -> Image.Image:
    # Basit netleştirme/kontrast
    img = ImageOps.exif_transpose(img)
    img = img.convert("L")
    img = ImageOps.autocontrast(img)
    img = img.filter(ImageFilter.SHARPEN)
    return img

def image_bytes_to_text(content: bytes) -> str:
    img = Image.open(BytesIO(content))
    img = preprocess(img)
    text = pytesseract.image_to_string(img, lang="eng+tur")
    return text
