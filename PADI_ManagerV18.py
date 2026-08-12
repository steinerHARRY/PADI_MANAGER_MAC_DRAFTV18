import tkinter as tk
from tkinter import filedialog, ttk, messagebox, simpledialog
import json
from pathlib import Path
from PIL import Image, ImageDraw, ImageTk, ImageOps
#from pdf2image import convert_from_path
import pypdfium2 as pdfium
from pypdf import PdfReader, PdfWriter
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import letter
import io
from reportlab.lib.utils import ImageReader
import re
import hashlib
from datetime import date

# Import tkcalendar for the date picker widget
from tkcalendar import DateEntry

editing_active = False
current_inline_entry = None

reopened_exported_pdf = False
loaded_pdf_values = {}
pdf_field_mapping = {}
pdf_field_rects = {}
tooltip_window = None
# ---------------- BASE DIRECTORY ----------------

import sys

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys.executable).resolve().parent
else:
    BASE_DIR = Path(__file__).resolve().parent

DB_FILE = BASE_DIR / "instructors.json"
SIGNATURE_DIR = BASE_DIR / "signatures"
FIELDS_FILE = BASE_DIR / "10056_OW_Records_mask.json"
print(FIELDS_FILE)
STATE_FILE = BASE_DIR / "state_padi.json"
# Comments are intentionally stored separately from the JSON mask file.
# This file contains only user comments associated with loaded PDFs.
COMMENTS_FILE = BASE_DIR / "comments.json"

SIGNATURE_DIR.mkdir(exist_ok=True)
print("BASE_DIR =", BASE_DIR)
print("FIELDS_FILE =", FIELDS_FILE)
print("EXISTS =", FIELDS_FILE.exists())
print("COMMENTS_FILE =", COMMENTS_FILE)
print("COMMENTS EXISTS =", COMMENTS_FILE.exists())
# ---------------- ZOOM SETTINGS ----------------

zoom_level_def = 0.50
ZOOM_STEP =0.1
MIN_ZOOM = 0.3
MAX_ZOOM = 3.0
zoom_level = zoom_level_def
show_json_names = False

# ---------------- Instructor Database ----------------

def load_instructors():
    if not DB_FILE.exists():
        return {"instructors": []}
    try:
        with DB_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
    except:
        return {"instructors": []}
    if "instructors" not in data:
        data["instructors"] = []
    return data

def save_instructors(data):
    with DB_FILE.open("w", encoding="utf-8") as f:
        json.dump(data, f, indent=4)

db = load_instructors()
instructor_list = db["instructors"]

# ---------------- PDF Comments ----------------
# Comments live in a separate comments.json file and NEVER modify the field mask.
comments_db = {}

def load_comments_db():
    if not COMMENTS_FILE.exists():
        return {}
    try:
        with COMMENTS_FILE.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception as e:
        print("COMMENT LOAD ERROR:", e)
        return {}

def save_comments_db(data):
    try:
        with COMMENTS_FILE.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=4, ensure_ascii=False)
        return True
    except Exception as e:
        messagebox.showerror("Comment Error", f"Failed to save comments:\n{e}")
        return False

def _comment_identity(pdf_file):
    """Return stable identifiers for a PDF without touching the mask JSON."""
    path = str(Path(pdf_file).resolve()) if pdf_file else ""
    filename = Path(pdf_file).name if pdf_file else ""
    path_key = hashlib.sha256(path.encode("utf-8")).hexdigest() if path else ""
    student = str(state.get("Student Name", "")).strip() if "state" in globals() else ""
    return path_key, filename, student

def get_saved_comment(pdf_file):
    if not pdf_file:
        return ""
    path_key, filename, student = _comment_identity(pdf_file)
    record = comments_db.get(path_key)
    if isinstance(record, dict):
        return str(record.get("comment", ""))

    # Fallback: if the PDF was moved/renamed, try filename + student name.
    for item in comments_db.values():
        if not isinstance(item, dict):
            continue
        if item.get("filename") == filename and student and item.get("student_name") == student:
            return str(item.get("comment", ""))
    return ""

def save_comment_for_pdf(pdf_file, comment):
    if not pdf_file:
        messagebox.showerror("Comment", "Load a PDF before saving a comment.")
        return False

    path_key, filename, student = _comment_identity(pdf_file)
    comments_db[path_key] = {
        "filename": filename,
        "student_name": student,
        "pdf_path": str(Path(pdf_file).resolve()),
        "comment": comment,
    }
    return save_comments_db(comments_db)

def display_comment(pdf_file):
    """Load the saved comment for a PDF into the main-menu textbox."""
    if "comment_text" not in globals():
        return

    comment_text.delete("1.0", "end")

    if pdf_file:
        saved = get_saved_comment(pdf_file)
        if saved:
            comment_text.insert("1.0", saved)

    comment_text.see("1.0")


def save_current_comment(pdf_file=None):
    """Save the text currently in the main-menu comment box."""
    target = pdf_file or globals().get("pdf_path")
    if not target or "comment_text" not in globals():
        return False

    comment = comment_text.get("1.0", "end-1c").strip()
    return save_comment_for_pdf(target, comment)


# PDF converter  
def convert_from_path(pdf_path, dpi=200):

    pdf = pdfium.PdfDocument(str(pdf_path))

    pages = []

    scale = dpi / 72.0

    try:

        for page_index in range(len(pdf)):

            page = pdf[page_index]

            bitmap = page.render(
                scale=scale
            )

            image = bitmap.to_pil().convert("RGB")

            pages.append(image)

            page.close()

    finally:

        pdf.close()

    return pages
# ---------------- Field Map + State ----------------

# ---------------- EMBEDDED MASTER MASK ----------------
# The application can recreate 10056_OW_Records_mask.json from this
# embedded definition. The external JSON is therefore not required for
# normal startup.
HARDCODED_MASK = {
    "fields": [
        {
            "name": "Student Name",
            "type": "text",
            "page": 0,
            "x1": 204,
            "y1": 177,
            "x2": 625,
            "y2": 206
        },
        {
            "name": "Birth Date",
            "type": "text",
            "page": 0,
            "x1": 160,
            "y1": 223,
            "x2": 222,
            "y2": 252
        },
        {
            "name": "undefined",
            "type": "text",
            "page": 0,
            "x1": 242,
            "y1": 223,
            "x2": 304,
            "y2": 252
        },
        {
            "name": "undefined_2",
            "type": "text",
            "page": 0,
            "x1": 324,
            "y1": 223,
            "x2": 386,
            "y2": 252
        },
        {
            "name": "Mailing address 1",
            "type": "text",
            "page": 0,
            "x1": 215,
            "y1": 284,
            "x2": 625,
            "y2": 314
        },
        {
            "name": "Mailing address 2",
            "type": "text",
            "page": 0,
            "x1": 75,
            "y1": 340,
            "x2": 315,
            "y2": 369
        },
        {
            "name": "Mailing address 3",
            "type": "text",
            "page": 0,
            "x1": 325,
            "y1": 340,
            "x2": 427,
            "y2": 369
        },
        {
            "name": "Mailing address 4",
            "type": "text",
            "page": 0,
            "x1": 436,
            "y1": 340,
            "x2": 502,
            "y2": 369
        },
        {
            "name": "Mailing address 5",
            "type": "text",
            "page": 0,
            "x1": 512,
            "y1": 340,
            "x2": 625,
            "y2": 369
        },
        {
            "name": "undefined_3",
            "type": "text",
            "page": 0,
            "x1": 277,
            "y1": 419,
            "x2": 337,
            "y2": 448
        },
        {
            "name": "undefined_4",
            "type": "text",
            "page": 0,
            "x1": 345,
            "y1": 419,
            "x2": 625,
            "y2": 448
        },
        {
            "name": "undefined_5",
            "type": "text",
            "page": 0,
            "x1": 277,
            "y1": 459,
            "x2": 337,
            "y2": 489
        },
        {
            "name": "undefined_6",
            "type": "text",
            "page": 0,
            "x1": 345,
            "y1": 459,
            "x2": 625,
            "y2": 489
        },
        {
            "name": "undefined_7",
            "type": "text",
            "page": 0,
            "x1": 277,
            "y1": 500,
            "x2": 337,
            "y2": 529
        },
        {
            "name": "undefined_8",
            "type": "text",
            "page": 0,
            "x1": 345,
            "y1": 500,
            "x2": 625,
            "y2": 529
        },
        {
            "name": "Email",
            "type": "text",
            "page": 0,
            "x1": 125,
            "y1": 540,
            "x2": 625,
            "y2": 569
        },
        {
            "name": "init_padi_instructor_1",
            "type": "text",
            "page": 0,
            "x1": 204,
            "y1": 691,
            "x2": 625,
            "y2": 720
        },
        {
            "name": "Init_Instructor_Signature_1",
            "type": "signature",
            "page": 0,
            "x1": 165,
            "y1": 731,
            "x2": 625,
            "y2": 760
        },
        {
            "name": "Init_PADI_no_1",
            "type": "text",
            "page": 0,
            "x1": 155,
            "y1": 772,
            "x2": 275,
            "y2": 801
        },
        {
            "name": "Init_Dive_Resort_No_1",
            "type": "text",
            "page": 0,
            "x1": 494,
            "y1": 772,
            "x2": 625,
            "y2": 801
        },
        {
            "name": "Init_day_1",
            "type": "text",
            "page": 0,
            "x1": 114,
            "y1": 817,
            "x2": 177,
            "y2": 846
        },
        {
            "name": "Init_month_1",
            "type": "text",
            "page": 0,
            "x1": 197,
            "y1": 817,
            "x2": 259,
            "y2": 846
        },
        {
            "name": "Init_year_1",
            "type": "text",
            "page": 0,
            "x1": 279,
            "y1": 817,
            "x2": 341,
            "y2": 846
        },
        {
            "name": "undefined_11",
            "type": "text",
            "page": 0,
            "x1": 277,
            "y1": 889,
            "x2": 337,
            "y2": 919
        },
        {
            "name": "Init_Phone_1",
            "type": "text",
            "page": 0,
            "x1": 345,
            "y1": 889,
            "x2": 625,
            "y2": 919
        },
        {
            "name": "undefined_13",
            "type": "text",
            "page": 0,
            "x1": 277,
            "y1": 930,
            "x2": 337,
            "y2": 959
        },
        {
            "name": "undefined_14",
            "type": "text",
            "page": 0,
            "x1": 345,
            "y1": 930,
            "x2": 625,
            "y2": 959
        },
        {
            "name": "Init_Email_1",
            "type": "text",
            "page": 0,
            "x1": 125,
            "y1": 970,
            "x2": 625,
            "y2": 1000
        },
        {
            "name": "Init_padi_instructor_2",
            "type": "text",
            "page": 0,
            "x1": 204,
            "y1": 1035,
            "x2": 625,
            "y2": 1065
        },
        {
            "name": "Init_Instructor_Signature_2",
            "type": "signature",
            "page": 0,
            "x1": 165,
            "y1": 1076,
            "x2": 625,
            "y2": 1105
        },
        {
            "name": "Init_PADI_no_2",
            "type": "text",
            "page": 0,
            "x1": 155,
            "y1": 1116,
            "x2": 275,
            "y2": 1145
        },
        {
            "name": "Init_Dive_Resort_No_2",
            "type": "text",
            "page": 0,
            "x1": 494,
            "y1": 1116,
            "x2": 625,
            "y2": 1145
        },
        {
            "name": "Init_day_2",
            "type": "text",
            "page": 0,
            "x1": 114,
            "y1": 1162,
            "x2": 177,
            "y2": 1191
        },
        {
            "name": "Init_month_2",
            "type": "text",
            "page": 0,
            "x1": 197,
            "y1": 1162,
            "x2": 259,
            "y2": 1191
        },
        {
            "name": "Init_year_2",
            "type": "text",
            "page": 0,
            "x1": 279,
            "y1": 1162,
            "x2": 341,
            "y2": 1191
        },
        {
            "name": "undefined_17",
            "type": "text",
            "page": 0,
            "x1": 277,
            "y1": 1229,
            "x2": 337,
            "y2": 1258
        },
        {
            "name": "Init_Phone_2",
            "type": "text",
            "page": 0,
            "x1": 345,
            "y1": 1229,
            "x2": 625,
            "y2": 1258
        },
        {
            "name": "undefined_19",
            "type": "text",
            "page": 0,
            "x1": 277,
            "y1": 1269,
            "x2": 337,
            "y2": 1298
        },
        {
            "name": "undefined_20",
            "type": "text",
            "page": 0,
            "x1": 345,
            "y1": 1269,
            "x2": 625,
            "y2": 1298
        },
        {
            "name": "Init_Email_2",
            "type": "text",
            "page": 0,
            "x1": 125,
            "y1": 1309,
            "x2": 625,
            "y2": 1338
        },
        {
            "name": "CW2_day",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 244,
            "x2": 803,
            "y2": 273
        },
        {
            "name": "CW2_month",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 244,
            "x2": 893,
            "y2": 273
        },
        {
            "name": "CW2_year",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 244,
            "x2": 985,
            "y2": 273
        },
        {
            "name": "CW3_day",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 277,
            "x2": 803,
            "y2": 306
        },
        {
            "name": "CW3_month",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 277,
            "x2": 893,
            "y2": 306
        },
        {
            "name": "CW3_year",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 277,
            "x2": 985,
            "y2": 306
        },
        {
            "name": "CW4_day",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 310,
            "x2": 803,
            "y2": 339
        },
        {
            "name": "CW4_month",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 310,
            "x2": 893,
            "y2": 339
        },
        {
            "name": "CW4_year",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 310,
            "x2": 985,
            "y2": 339
        },
        {
            "name": "CW1_initials",
            "type": "text",
            "page": 0,
            "x1": 1023,
            "y1": 210,
            "x2": 1086,
            "y2": 239
        },
        {
            "name": "CW2_initials",
            "type": "text",
            "page": 0,
            "x1": 1023,
            "y1": 244,
            "x2": 1086,
            "y2": 273
        },
        {
            "name": "CW3_initials",
            "type": "text",
            "page": 0,
            "x1": 1023,
            "y1": 277,
            "x2": 1086,
            "y2": 306
        },
        {
            "name": "CW4_initials",
            "type": "text",
            "page": 0,
            "x1": 1023,
            "y1": 310,
            "x2": 1086,
            "y2": 339
        },
        {
            "name": "CW1_day",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 210,
            "x2": 803,
            "y2": 239
        },
        {
            "name": "CW1_month",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 210,
            "x2": 893,
            "y2": 239
        },
        {
            "name": "CW1_year",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 210,
            "x2": 985,
            "y2": 239
        },
        {
            "name": "CW1_padi",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 210,
            "x2": 1192,
            "y2": 239
        },
        {
            "name": "CW15_day",
            "type": "text",
            "page": 0,
            "x1": 1336,
            "y1": 211,
            "x2": 1407,
            "y2": 239
        },
        {
            "name": "CW15_month",
            "type": "text",
            "page": 0,
            "x1": 1427,
            "y1": 211,
            "x2": 1498,
            "y2": 239
        },
        {
            "name": "CW15_year",
            "type": "text",
            "page": 0,
            "x1": 1518,
            "y1": 211,
            "x2": 1588,
            "y2": 239
        },
        {
            "name": "undefined_32",
            "type": "text",
            "page": 0,
            "x1": 1681,
            "y1": 211,
            "x2": 1761,
            "y2": 239
        },
        {
            "name": "CW15_initials",
            "type": "text",
            "page": 0,
            "x1": 1903,
            "y1": 211,
            "x2": 1983,
            "y2": 239
        },
        {
            "name": "CW15_padi",
            "type": "text",
            "page": 0,
            "x1": 2028,
            "y1": 211,
            "x2": 2117,
            "y2": 239
        },
        {
            "name": "CW2_padi",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 244,
            "x2": 1192,
            "y2": 273
        },
        {
            "name": "CW16_day",
            "type": "text",
            "page": 0,
            "x1": 1336,
            "y1": 240,
            "x2": 1407,
            "y2": 270
        },
        {
            "name": "CW16_month",
            "type": "text",
            "page": 0,
            "x1": 1427,
            "y1": 240,
            "x2": 1498,
            "y2": 270
        },
        {
            "name": "CW16_year",
            "type": "text",
            "page": 0,
            "x1": 1518,
            "y1": 240,
            "x2": 1588,
            "y2": 270
        },
        {
            "name": "undefined_38",
            "type": "text",
            "page": 0,
            "x1": 1681,
            "y1": 240,
            "x2": 1761,
            "y2": 270
        },
        {
            "name": "CW16_initials",
            "type": "text",
            "page": 0,
            "x1": 1903,
            "y1": 240,
            "x2": 1983,
            "y2": 270
        },
        {
            "name": "CW16_padi",
            "type": "text",
            "page": 0,
            "x1": 2028,
            "y1": 240,
            "x2": 2117,
            "y2": 270
        },
        {
            "name": "CW3_padi",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 277,
            "x2": 1192,
            "y2": 306
        },
        {
            "name": "CW17_day",
            "type": "text",
            "page": 0,
            "x1": 1336,
            "y1": 271,
            "x2": 1407,
            "y2": 300
        },
        {
            "name": "CW17_month",
            "type": "text",
            "page": 0,
            "x1": 1427,
            "y1": 271,
            "x2": 1498,
            "y2": 300
        },
        {
            "name": "CW17_year",
            "type": "text",
            "page": 0,
            "x1": 1518,
            "y1": 271,
            "x2": 1588,
            "y2": 300
        },
        {
            "name": "undefined_44",
            "type": "text",
            "page": 0,
            "x1": 1681,
            "y1": 271,
            "x2": 1761,
            "y2": 300
        },
        {
            "name": "CW17_initials",
            "type": "text",
            "page": 0,
            "x1": 1903,
            "y1": 271,
            "x2": 1983,
            "y2": 300
        },
        {
            "name": "CW17_padi",
            "type": "text",
            "page": 0,
            "x1": 2028,
            "y1": 271,
            "x2": 2117,
            "y2": 300
        },
        {
            "name": "CW4_padi",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 310,
            "x2": 1192,
            "y2": 339
        },
        {
            "name": "CW18_day",
            "type": "text",
            "page": 0,
            "x1": 1336,
            "y1": 302,
            "x2": 1407,
            "y2": 331
        },
        {
            "name": "CW18_month",
            "type": "text",
            "page": 0,
            "x1": 1427,
            "y1": 302,
            "x2": 1498,
            "y2": 331
        },
        {
            "name": "CW18_year",
            "type": "text",
            "page": 0,
            "x1": 1518,
            "y1": 302,
            "x2": 1588,
            "y2": 331
        },
        {
            "name": "undefined_50",
            "type": "text",
            "page": 0,
            "x1": 1681,
            "y1": 302,
            "x2": 1761,
            "y2": 331
        },
        {
            "name": "CW18_initials",
            "type": "text",
            "page": 0,
            "x1": 1903,
            "y1": 302,
            "x2": 1983,
            "y2": 331
        },
        {
            "name": "CW18_padi",
            "type": "text",
            "page": 0,
            "x1": 2028,
            "y1": 302,
            "x2": 2117,
            "y2": 331
        },
        {
            "name": "CW5_day",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 343,
            "x2": 803,
            "y2": 373
        },
        {
            "name": "CW5_month",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 343,
            "x2": 893,
            "y2": 373
        },
        {
            "name": "CW5_year",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 343,
            "x2": 985,
            "y2": 373
        },
        {
            "name": "CW5_initials",
            "type": "text",
            "page": 0,
            "x1": 1023,
            "y1": 343,
            "x2": 1086,
            "y2": 373
        },
        {
            "name": "CW5_padi",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 343,
            "x2": 1192,
            "y2": 373
        },
        {
            "name": "CW19_day",
            "type": "text",
            "page": 0,
            "x1": 1336,
            "y1": 332,
            "x2": 1407,
            "y2": 361
        },
        {
            "name": "CW19_month",
            "type": "text",
            "page": 0,
            "x1": 1427,
            "y1": 332,
            "x2": 1498,
            "y2": 361
        },
        {
            "name": "CW19_year",
            "type": "text",
            "page": 0,
            "x1": 1518,
            "y1": 332,
            "x2": 1588,
            "y2": 361
        },
        {
            "name": "undefined_58",
            "type": "text",
            "page": 0,
            "x1": 1681,
            "y1": 332,
            "x2": 1761,
            "y2": 361
        },
        {
            "name": "CW19_initials",
            "type": "text",
            "page": 0,
            "x1": 1903,
            "y1": 332,
            "x2": 1983,
            "y2": 361
        },
        {
            "name": "CW19_padi",
            "type": "text",
            "page": 0,
            "x1": 2028,
            "y1": 332,
            "x2": 2117,
            "y2": 361
        },
        {
            "name": "CW20_day",
            "type": "text",
            "page": 0,
            "x1": 1336,
            "y1": 375,
            "x2": 1407,
            "y2": 404
        },
        {
            "name": "CW20_month",
            "type": "text",
            "page": 0,
            "x1": 1427,
            "y1": 375,
            "x2": 1498,
            "y2": 404
        },
        {
            "name": "CW20_year",
            "type": "text",
            "page": 0,
            "x1": 1518,
            "y1": 375,
            "x2": 1588,
            "y2": 404
        },
        {
            "name": "CW20_quizz",
            "type": "text",
            "page": 0,
            "x1": 1681,
            "y1": 375,
            "x2": 1761,
            "y2": 404
        },
        {
            "name": "CW20_initials",
            "type": "text",
            "page": 0,
            "x1": 1903,
            "y1": 375,
            "x2": 1983,
            "y2": 404
        },
        {
            "name": "CW20_padi",
            "type": "text",
            "page": 0,
            "x1": 2028,
            "y1": 375,
            "x2": 2117,
            "y2": 404
        },
        {
            "name": "CW6_initials",
            "type": "text",
            "page": 0,
            "x1": 1023,
            "y1": 486,
            "x2": 1086,
            "y2": 516
        },
        {
            "name": "CW6_day",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 486,
            "x2": 803,
            "y2": 516
        },
        {
            "name": "CW6_month",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 486,
            "x2": 893,
            "y2": 516
        },
        {
            "name": "CW6_year",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 486,
            "x2": 985,
            "y2": 516
        },
        {
            "name": "CW6_padi",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 486,
            "x2": 1192,
            "y2": 516
        },
        {
            "name": "Instructor_signature_4",
            "type": "signature",
            "page": 0,
            "x1": 1379,
            "y1": 480,
            "x2": 1690,
            "y2": 509
        },
        {
            "name": "PADI_no_4",
            "type": "text",
            "page": 0,
            "x1": 1717,
            "y1": 480,
            "x2": 1832,
            "y2": 509
        },
        {
            "name": "day_4",
            "type": "text",
            "page": 0,
            "x1": 1888,
            "y1": 480,
            "x2": 1970,
            "y2": 509
        },
        {
            "name": "month_4",
            "type": "text",
            "page": 0,
            "x1": 1990,
            "y1": 480,
            "x2": 2043,
            "y2": 509
        },
        {
            "name": "year_4",
            "type": "text",
            "page": 0,
            "x1": 2063,
            "y1": 480,
            "x2": 2117,
            "y2": 509
        },
        {
            "name": "CW7_year",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 559,
            "x2": 985,
            "y2": 589
        },
        {
            "name": "CW7_initials",
            "type": "text",
            "page": 0,
            "x1": 1023,
            "y1": 559,
            "x2": 1086,
            "y2": 589
        },
        {
            "name": "CW7_padi",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 559,
            "x2": 1192,
            "y2": 589
        },
        {
            "name": "CW7_day",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 559,
            "x2": 803,
            "y2": 589
        },
        {
            "name": "CW7_month",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 559,
            "x2": 893,
            "y2": 589
        },
        {
            "name": "CW8_initials",
            "type": "text",
            "page": 0,
            "x1": 1024,
            "y1": 676,
            "x2": 1086,
            "y2": 705
        },
        {
            "name": "CW8_padi",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 676,
            "x2": 1192,
            "y2": 705
        },
        {
            "name": "CW22_day",
            "type": "text",
            "page": 0,
            "x1": 1275,
            "y1": 641,
            "x2": 1328,
            "y2": 671
        },
        {
            "name": "CW22_month",
            "type": "text",
            "page": 0,
            "x1": 1348,
            "y1": 641,
            "x2": 1402,
            "y2": 671
        },
        {
            "name": "CW22_year",
            "type": "text",
            "page": 0,
            "x1": 1421,
            "y1": 641,
            "x2": 1475,
            "y2": 671
        },
        {
            "name": "CW21_initials",
            "type": "text",
            "page": 0,
            "x1": 1494,
            "y1": 612,
            "x2": 1547,
            "y2": 637
        },
        {
            "name": "CW22_initials",
            "type": "text",
            "page": 0,
            "x1": 1494,
            "y1": 641,
            "x2": 1547,
            "y2": 671
        },
        {
            "name": "CW22_padi",
            "type": "text",
            "page": 0,
            "x1": 1583,
            "y1": 641,
            "x2": 1654,
            "y2": 671
        },
        {
            "name": "CW24_day",
            "type": "text",
            "page": 0,
            "x1": 1728,
            "y1": 641,
            "x2": 1781,
            "y2": 671
        },
        {
            "name": "CW24_month",
            "type": "text",
            "page": 0,
            "x1": 1801,
            "y1": 641,
            "x2": 1854,
            "y2": 671
        },
        {
            "name": "CW24_year",
            "type": "text",
            "page": 0,
            "x1": 1874,
            "y1": 641,
            "x2": 1928,
            "y2": 671
        },
        {
            "name": "CW23_initials",
            "type": "text",
            "page": 0,
            "x1": 1956,
            "y1": 612,
            "x2": 2010,
            "y2": 637
        },
        {
            "name": "CW24_initials",
            "type": "text",
            "page": 0,
            "x1": 1956,
            "y1": 641,
            "x2": 2010,
            "y2": 671
        },
        {
            "name": "CW21_day",
            "type": "text",
            "page": 0,
            "x1": 1275,
            "y1": 612,
            "x2": 1328,
            "y2": 637
        },
        {
            "name": "CW21_month",
            "type": "text",
            "page": 0,
            "x1": 1348,
            "y1": 612,
            "x2": 1401,
            "y2": 637
        },
        {
            "name": "CW21_year",
            "type": "text",
            "page": 0,
            "x1": 1421,
            "y1": 612,
            "x2": 1475,
            "y2": 637
        },
        {
            "name": "CW21_padi",
            "type": "text",
            "page": 0,
            "x1": 1583,
            "y1": 612,
            "x2": 1654,
            "y2": 637
        },
        {
            "name": "CW23_day",
            "type": "text",
            "page": 0,
            "x1": 1728,
            "y1": 612,
            "x2": 1781,
            "y2": 637
        },
        {
            "name": "CW23_month",
            "type": "text",
            "page": 0,
            "x1": 1801,
            "y1": 612,
            "x2": 1854,
            "y2": 637
        },
        {
            "name": "CW23_year",
            "type": "text",
            "page": 0,
            "x1": 1874,
            "y1": 612,
            "x2": 1928,
            "y2": 637
        },
        {
            "name": "CW23_padi",
            "type": "text",
            "page": 0,
            "x1": 2045,
            "y1": 612,
            "x2": 2117,
            "y2": 637
        },
        {
            "name": "CW24_padi",
            "type": "text",
            "page": 0,
            "x1": 2045,
            "y1": 641,
            "x2": 2117,
            "y2": 671
        },
        {
            "name": "CW8_day",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 676,
            "x2": 803,
            "y2": 705
        },
        {
            "name": "CW8_month",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 676,
            "x2": 893,
            "y2": 705
        },
        {
            "name": "CW8_year",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 676,
            "x2": 985,
            "y2": 705
        },
        {
            "name": "CW9_initials",
            "type": "text",
            "page": 0,
            "x1": 1023,
            "y1": 756,
            "x2": 1086,
            "y2": 785
        },
        {
            "name": "CW9_padi",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 756,
            "x2": 1192,
            "y2": 785
        },
        {
            "name": "CW9_day",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 756,
            "x2": 803,
            "y2": 785
        },
        {
            "name": "CW9_month",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 756,
            "x2": 893,
            "y2": 785
        },
        {
            "name": "CW9_year",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 756,
            "x2": 985,
            "y2": 785
        },
        {
            "name": "Dive_2",
            "type": "text",
            "page": 0,
            "x1": 1699,
            "y1": 773,
            "x2": 1779,
            "y2": 803
        },
        {
            "name": "CW10_day",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 835,
            "x2": 803,
            "y2": 864
        },
        {
            "name": "CW10_year",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 835,
            "x2": 985,
            "y2": 864
        },
        {
            "name": "CW10_initials",
            "type": "text",
            "page": 0,
            "x1": 1023,
            "y1": 835,
            "x2": 1086,
            "y2": 864
        },
        {
            "name": "CW10_padi",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 835,
            "x2": 1192,
            "y2": 864
        },
        {
            "name": "Dive_3",
            "type": "text",
            "page": 0,
            "x1": 1699,
            "y1": 804,
            "x2": 1779,
            "y2": 833
        },
        {
            "name": "CW10_month",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 835,
            "x2": 893,
            "y2": 864
        },
        {
            "name": "Dive_4",
            "type": "text",
            "page": 0,
            "x1": 1699,
            "y1": 835,
            "x2": 1779,
            "y2": 864
        },
        {
            "name": "CW11_padi",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 915,
            "x2": 1192,
            "y2": 944
        },
        {
            "name": "Dive_5",
            "type": "text",
            "page": 0,
            "x1": 1699,
            "y1": 865,
            "x2": 1779,
            "y2": 894
        },
        {
            "name": "CW11_day",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 915,
            "x2": 803,
            "y2": 944
        },
        {
            "name": "Dive_6",
            "type": "text",
            "page": 0,
            "x1": 1699,
            "y1": 896,
            "x2": 1779,
            "y2": 925
        },
        {
            "name": "CW11_month",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 915,
            "x2": 893,
            "y2": 944
        },
        {
            "name": "CW11_year",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 915,
            "x2": 985,
            "y2": 944
        },
        {
            "name": "CW11_initials",
            "type": "text",
            "page": 0,
            "x1": 1023,
            "y1": 915,
            "x2": 1086,
            "y2": 944
        },
        {
            "name": "Dive_7",
            "type": "text",
            "page": 0,
            "x1": 1699,
            "y1": 926,
            "x2": 1779,
            "y2": 956
        },
        {
            "name": "CW12_initials",
            "type": "text",
            "page": 0,
            "x1": 1023,
            "y1": 994,
            "x2": 1086,
            "y2": 1024
        },
        {
            "name": "CW12_padi",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 994,
            "x2": 1192,
            "y2": 1024
        },
        {
            "name": "Dive_8",
            "type": "text",
            "page": 0,
            "x1": 1699,
            "y1": 957,
            "x2": 1779,
            "y2": 986
        },
        {
            "name": "CW12_day",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 994,
            "x2": 803,
            "y2": 1024
        },
        {
            "name": "CW12_month",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 994,
            "x2": 893,
            "y2": 1024
        },
        {
            "name": "CW12_year",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 994,
            "x2": 985,
            "y2": 1024
        },
        {
            "name": "Dive_9",
            "type": "text",
            "page": 0,
            "x1": 1698,
            "y1": 988,
            "x2": 1778,
            "y2": 1017
        },
        {
            "name": "Dive_initials_1",
            "type": "text",
            "page": 0,
            "x1": 1850,
            "y1": 744,
            "x2": 1912,
            "y2": 772
        },
        {
            "name": "Dive_initials_2",
            "type": "text",
            "page": 0,
            "x1": 1850,
            "y1": 773,
            "x2": 1912,
            "y2": 803
        },
        {
            "name": "Dive_initials_3",
            "type": "text",
            "page": 0,
            "x1": 1850,
            "y1": 804,
            "x2": 1912,
            "y2": 833
        },
        {
            "name": "Dive_initials_4",
            "type": "text",
            "page": 0,
            "x1": 1850,
            "y1": 835,
            "x2": 1912,
            "y2": 864
        },
        {
            "name": "Dive_initials_5",
            "type": "text",
            "page": 0,
            "x1": 1850,
            "y1": 865,
            "x2": 1912,
            "y2": 894
        },
        {
            "name": "Dive_initials_6",
            "type": "text",
            "page": 0,
            "x1": 1850,
            "y1": 896,
            "x2": 1912,
            "y2": 925
        },
        {
            "name": "Dive_initials_7",
            "type": "text",
            "page": 0,
            "x1": 1850,
            "y1": 926,
            "x2": 1912,
            "y2": 956
        },
        {
            "name": "Dive_initials_8",
            "type": "text",
            "page": 0,
            "x1": 1850,
            "y1": 957,
            "x2": 1912,
            "y2": 986
        },
        {
            "name": "Dive_1",
            "type": "text",
            "page": 0,
            "x1": 1699,
            "y1": 744,
            "x2": 1779,
            "y2": 772
        },
        {
            "name": "Dive_padi_1",
            "type": "text",
            "page": 0,
            "x1": 1992,
            "y1": 744,
            "x2": 2081,
            "y2": 772
        },
        {
            "name": "Dive_padi_2",
            "type": "text",
            "page": 0,
            "x1": 1992,
            "y1": 773,
            "x2": 2081,
            "y2": 803
        },
        {
            "name": "Dive_padi_3",
            "type": "text",
            "page": 0,
            "x1": 1992,
            "y1": 804,
            "x2": 2081,
            "y2": 833
        },
        {
            "name": "Dive_padi_4",
            "type": "text",
            "page": 0,
            "x1": 1992,
            "y1": 835,
            "x2": 2081,
            "y2": 864
        },
        {
            "name": "Dive_padi_5",
            "type": "text",
            "page": 0,
            "x1": 1992,
            "y1": 865,
            "x2": 2081,
            "y2": 894
        },
        {
            "name": "Dive_padi_6",
            "type": "text",
            "page": 0,
            "x1": 1992,
            "y1": 896,
            "x2": 2081,
            "y2": 925
        },
        {
            "name": "Dive_padi_7",
            "type": "text",
            "page": 0,
            "x1": 1992,
            "y1": 926,
            "x2": 2081,
            "y2": 956
        },
        {
            "name": "Dive_padi_8",
            "type": "text",
            "page": 0,
            "x1": 1992,
            "y1": 957,
            "x2": 2081,
            "y2": 986
        },
        {
            "name": "Dive_padi_9",
            "type": "text",
            "page": 0,
            "x1": 1992,
            "y1": 988,
            "x2": 2081,
            "y2": 1017
        },
        {
            "name": "CW13_year",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 1083,
            "x2": 985,
            "y2": 1113
        },
        {
            "name": "CW13_initials",
            "type": "text",
            "page": 0,
            "x1": 1023,
            "y1": 1083,
            "x2": 1086,
            "y2": 1113
        },
        {
            "name": "CW13_padi",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 1083,
            "x2": 1192,
            "y2": 1113
        },
        {
            "name": "Dive_10",
            "type": "text",
            "page": 0,
            "x1": 1698,
            "y1": 1018,
            "x2": 1778,
            "y2": 1047
        },
        {
            "name": "Dive_padi_10",
            "type": "text",
            "page": 0,
            "x1": 1992,
            "y1": 1018,
            "x2": 2081,
            "y2": 1047
        },
        {
            "name": "CW13_day",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 1083,
            "x2": 803,
            "y2": 1113
        },
        {
            "name": "CW13_month",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 1083,
            "x2": 893,
            "y2": 1113
        },
        {
            "name": "CW14_year",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 1172,
            "x2": 985,
            "y2": 1202
        },
        {
            "name": "CW14_initials",
            "type": "text",
            "page": 0,
            "x1": 1023,
            "y1": 1172,
            "x2": 1086,
            "y2": 1202
        },
        {
            "name": "CW14_padi",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 1172,
            "x2": 1192,
            "y2": 1202
        },
        {
            "name": "Instructor_signature_5",
            "type": "signature",
            "page": 0,
            "x1": 1379,
            "y1": 1128,
            "x2": 1690,
            "y2": 1158
        },
        {
            "name": "PADI_no_5",
            "type": "text",
            "page": 0,
            "x1": 1708,
            "y1": 1128,
            "x2": 1814,
            "y2": 1158
        },
        {
            "name": "day_5",
            "type": "text",
            "page": 0,
            "x1": 1863,
            "y1": 1128,
            "x2": 1935,
            "y2": 1158
        },
        {
            "name": "month_5",
            "type": "text",
            "page": 0,
            "x1": 1954,
            "y1": 1128,
            "x2": 2026,
            "y2": 1158
        },
        {
            "name": "year_5",
            "type": "text",
            "page": 0,
            "x1": 2045,
            "y1": 1128,
            "x2": 2117,
            "y2": 1158
        },
        {
            "name": "CW14_day",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 1172,
            "x2": 803,
            "y2": 1202
        },
        {
            "name": "CW14_month",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 1172,
            "x2": 893,
            "y2": 1202
        },
        {
            "name": "student_signature",
            "type": "signature",
            "page": 0,
            "x1": 1370,
            "y1": 1316,
            "x2": 1814,
            "y2": 1345
        },
        {
            "name": "Stu_day",
            "type": "text",
            "page": 0,
            "x1": 1869,
            "y1": 1316,
            "x2": 1940,
            "y2": 1345
        },
        {
            "name": "Stu_month",
            "type": "text",
            "page": 0,
            "x1": 1960,
            "y1": 1316,
            "x2": 2030,
            "y2": 1345
        },
        {
            "name": "Stu_year",
            "type": "text",
            "page": 0,
            "x1": 2051,
            "y1": 1316,
            "x2": 2122,
            "y2": 1345
        },
        {
            "name": "Instructor_signature_3",
            "type": "signature",
            "page": 0,
            "x1": 819,
            "y1": 1353,
            "x2": 1192,
            "y2": 1383
        },
        {
            "name": "PADI_no_3",
            "type": "text",
            "page": 0,
            "x1": 721,
            "y1": 1409,
            "x2": 890,
            "y2": 1438
        },
        {
            "name": "day_3",
            "type": "text",
            "page": 0,
            "x1": 940,
            "y1": 1409,
            "x2": 1011,
            "y2": 1438
        },
        {
            "name": "month_3",
            "type": "text",
            "page": 0,
            "x1": 1031,
            "y1": 1409,
            "x2": 1102,
            "y2": 1438
        },
        {
            "name": "year_3",
            "type": "text",
            "page": 0,
            "x1": 1122,
            "y1": 1409,
            "x2": 1193,
            "y2": 1438
        },
        {
            "name": "Instructor_signature_6",
            "type": "signature",
            "page": 0,
            "x1": 1387,
            "y1": 1459,
            "x2": 1690,
            "y2": 1488
        },
        {
            "name": "PADI_no_6",
            "type": "text",
            "page": 0,
            "x1": 1708,
            "y1": 1459,
            "x2": 1814,
            "y2": 1488
        },
        {
            "name": "day_6",
            "type": "text",
            "page": 0,
            "x1": 1863,
            "y1": 1459,
            "x2": 1935,
            "y2": 1488
        },
        {
            "name": "month_6",
            "type": "text",
            "page": 0,
            "x1": 1954,
            "y1": 1459,
            "x2": 2026,
            "y2": 1488
        },
        {
            "name": "year_6",
            "type": "text",
            "page": 0,
            "x1": 2045,
            "y1": 1459,
            "x2": 2117,
            "y2": 1488
        },
        {
            "name": "Instructor_signature_7",
            "type": "signature",
            "page": 0,
            "x1": 1379,
            "y1": 1555,
            "x2": 1690,
            "y2": 1584
        },
        {
            "name": "PADI_no_7",
            "type": "text",
            "page": 0,
            "x1": 1708,
            "y1": 1555,
            "x2": 1814,
            "y2": 1584
        },
        {
            "name": "day_7",
            "type": "text",
            "page": 0,
            "x1": 1863,
            "y1": 1555,
            "x2": 1935,
            "y2": 1584
        },
        {
            "name": "month_7",
            "type": "text",
            "page": 0,
            "x1": 1954,
            "y1": 1555,
            "x2": 2026,
            "y2": 1584
        },
        {
            "name": "year_7",
            "type": "text",
            "page": 0,
            "x1": 2045,
            "y1": 1555,
            "x2": 2117,
            "y2": 1584
        },
        {
            "name": "Dive_initials_9",
            "type": "text",
            "page": 0,
            "x1": 1850,
            "y1": 988,
            "x2": 1912,
            "y2": 1017
        },
        {
            "name": "Dive_initials_10",
            "type": "text",
            "page": 0,
            "x1": 1850,
            "y1": 1018,
            "x2": 1912,
            "y2": 1046
        },
        {
            "name": "Check Box20",
            "type": "checkbox",
            "page": 0,
            "x1": 542,
            "y1": 232,
            "x2": 556,
            "y2": 250
        },
        {
            "name": "Check Box21",
            "type": "checkbox",
            "page": 0,
            "x1": 594,
            "y1": 232,
            "x2": 608,
            "y2": 250
        },
        {
            "name": "Check Box22",
            "type": "checkbox",
            "page": 0,
            "x1": 1942,
            "y1": 135,
            "x2": 1957,
            "y2": 151
        },
        {
            "name": "Check Box23",
            "type": "checkbox",
            "page": 0,
            "x1": 1850,
            "y1": 135,
            "x2": 1864,
            "y2": 151
        },
        {
            "name": "Check Box24",
            "type": "checkbox",
            "page": 0,
            "x1": 1742,
            "y1": 135,
            "x2": 1756,
            "y2": 151
        },
        {
            "name": "Check Box25",
            "type": "checkbox",
            "page": 0,
            "x1": 1623,
            "y1": 221,
            "x2": 1637,
            "y2": 237
        },
        {
            "name": "Check Box26",
            "type": "checkbox",
            "page": 0,
            "x1": 1826,
            "y1": 221,
            "x2": 1840,
            "y2": 237
        },
        {
            "name": "Check Box27",
            "type": "checkbox",
            "page": 0,
            "x1": 1623,
            "y1": 251,
            "x2": 1637,
            "y2": 267
        },
        {
            "name": "Check Box28",
            "type": "checkbox",
            "page": 0,
            "x1": 1826,
            "y1": 251,
            "x2": 1840,
            "y2": 267
        },
        {
            "name": "Check Box29",
            "type": "checkbox",
            "page": 0,
            "x1": 1623,
            "y1": 282,
            "x2": 1637,
            "y2": 298
        },
        {
            "name": "Check Box30",
            "type": "checkbox",
            "page": 0,
            "x1": 1826,
            "y1": 282,
            "x2": 1840,
            "y2": 298
        },
        {
            "name": "Check Box31",
            "type": "checkbox",
            "page": 0,
            "x1": 1623,
            "y1": 312,
            "x2": 1637,
            "y2": 329
        },
        {
            "name": "Check Box32",
            "type": "checkbox",
            "page": 0,
            "x1": 1826,
            "y1": 312,
            "x2": 1840,
            "y2": 329
        },
        {
            "name": "Check Box33",
            "type": "checkbox",
            "page": 0,
            "x1": 1623,
            "y1": 343,
            "x2": 1637,
            "y2": 359
        },
        {
            "name": "Check Box34",
            "type": "checkbox",
            "page": 0,
            "x1": 1826,
            "y1": 343,
            "x2": 1840,
            "y2": 359
        },
        {
            "name": "Check Box35",
            "type": "checkbox",
            "page": 0,
            "x1": 1623,
            "y1": 385,
            "x2": 1637,
            "y2": 401
        },
        {
            "name": "Check Box36",
            "type": "checkbox",
            "page": 0,
            "x1": 1826,
            "y1": 385,
            "x2": 1840,
            "y2": 401
        },
        {
            "name": "CW 2",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 244,
            "x2": 803,
            "y2": 273
        },
        {
            "name": "undefined_21",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 244,
            "x2": 893,
            "y2": 273
        },
        {
            "name": "undefined_22",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 244,
            "x2": 985,
            "y2": 273
        },
        {
            "name": "CW 3",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 277,
            "x2": 803,
            "y2": 306
        },
        {
            "name": "undefined_23",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 277,
            "x2": 893,
            "y2": 306
        },
        {
            "name": "undefined_24",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 277,
            "x2": 985,
            "y2": 306
        },
        {
            "name": "CW 4",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 310,
            "x2": 803,
            "y2": 339
        },
        {
            "name": "undefined_25",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 310,
            "x2": 893,
            "y2": 339
        },
        {
            "name": "undefined_26",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 310,
            "x2": 985,
            "y2": 339
        },
        {
            "name": "Initials 1",
            "type": "text",
            "page": 0,
            "x1": 1024,
            "y1": 210,
            "x2": 1085,
            "y2": 240
        },
        {
            "name": "Initials 2",
            "type": "text",
            "page": 0,
            "x1": 1024,
            "y1": 244,
            "x2": 1085,
            "y2": 273
        },
        {
            "name": "Initials 3",
            "type": "text",
            "page": 0,
            "x1": 1024,
            "y1": 277,
            "x2": 1085,
            "y2": 306
        },
        {
            "name": "Initials 4",
            "type": "text",
            "page": 0,
            "x1": 1024,
            "y1": 310,
            "x2": 1085,
            "y2": 339
        },
        {
            "name": "CW 1",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 210,
            "x2": 803,
            "y2": 240
        },
        {
            "name": "undefined_27",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 210,
            "x2": 893,
            "y2": 240
        },
        {
            "name": "undefined_28",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 210,
            "x2": 985,
            "y2": 240
        },
        {
            "name": "undefined_29",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 210,
            "x2": 1192,
            "y2": 240
        },
        {
            "name": "Section 1",
            "type": "text",
            "page": 0,
            "x1": 1336,
            "y1": 211,
            "x2": 1407,
            "y2": 239
        },
        {
            "name": "undefined_30",
            "type": "text",
            "page": 0,
            "x1": 1426,
            "y1": 211,
            "x2": 1498,
            "y2": 239
        },
        {
            "name": "undefined_31",
            "type": "text",
            "page": 0,
            "x1": 1517,
            "y1": 211,
            "x2": 1588,
            "y2": 239
        },
        {
            "name": "undefined_33",
            "type": "text",
            "page": 0,
            "x1": 1903,
            "y1": 211,
            "x2": 1983,
            "y2": 239
        },
        {
            "name": "undefined_34",
            "type": "text",
            "page": 0,
            "x1": 2028,
            "y1": 211,
            "x2": 2117,
            "y2": 239
        },
        {
            "name": "undefined_35",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 244,
            "x2": 1192,
            "y2": 273
        },
        {
            "name": "Section 2",
            "type": "text",
            "page": 0,
            "x1": 1336,
            "y1": 240,
            "x2": 1407,
            "y2": 270
        },
        {
            "name": "undefined_41",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 277,
            "x2": 1192,
            "y2": 306
        },
        {
            "name": "undefined_47",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 310,
            "x2": 1192,
            "y2": 339
        },
        {
            "name": "CW 5",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 343,
            "x2": 803,
            "y2": 373
        },
        {
            "name": "undefined_53",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 343,
            "x2": 893,
            "y2": 373
        },
        {
            "name": "undefined_54",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 343,
            "x2": 985,
            "y2": 373
        },
        {
            "name": "DSD with all CW Dive 1 skills  Open Water Diver CW Dive 1",
            "type": "text",
            "page": 0,
            "x1": 1024,
            "y1": 343,
            "x2": 1085,
            "y2": 373
        },
        {
            "name": "undefined_55",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 343,
            "x2": 1192,
            "y2": 373
        },
        {
            "name": "200 metreyard Swim OR 300 metreyard MaskSnorkelFin Swim",
            "type": "text",
            "page": 0,
            "x1": 1024,
            "y1": 487,
            "x2": 1085,
            "y2": 516
        },
        {
            "name": "10 Minute Survival Float",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 487,
            "x2": 803,
            "y2": 516
        },
        {
            "name": "undefined_66",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 487,
            "x2": 893,
            "y2": 516
        },
        {
            "name": "undefined_67",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 487,
            "x2": 985,
            "y2": 516
        },
        {
            "name": "undefined_68",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 487,
            "x2": 1192,
            "y2": 516
        },
        {
            "name": "undefined_72",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 559,
            "x2": 985,
            "y2": 589
        },
        {
            "name": "undefined_73",
            "type": "text",
            "page": 0,
            "x1": 1024,
            "y1": 559,
            "x2": 1085,
            "y2": 589
        },
        {
            "name": "undefined_74",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 559,
            "x2": 1192,
            "y2": 589
        },
        {
            "name": "undefined_75",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 559,
            "x2": 803,
            "y2": 589
        },
        {
            "name": "undefined_76",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 559,
            "x2": 893,
            "y2": 589
        },
        {
            "name": "undefined_77",
            "type": "text",
            "page": 0,
            "x1": 1024,
            "y1": 676,
            "x2": 1085,
            "y2": 705
        },
        {
            "name": "undefined_78",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 676,
            "x2": 1192,
            "y2": 705
        },
        {
            "name": "Equipment Preparation and Care",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 676,
            "x2": 803,
            "y2": 705
        },
        {
            "name": "undefined_91",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 676,
            "x2": 893,
            "y2": 705
        },
        {
            "name": "undefined_92",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 676,
            "x2": 985,
            "y2": 705
        },
        {
            "name": "undefined_93",
            "type": "text",
            "page": 0,
            "x1": 1024,
            "y1": 756,
            "x2": 1085,
            "y2": 785
        },
        {
            "name": "undefined_94",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 756,
            "x2": 1192,
            "y2": 785
        },
        {
            "name": "Disconnect Low Pressure Inflator Hose",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 756,
            "x2": 803,
            "y2": 785
        },
        {
            "name": "undefined_95",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 756,
            "x2": 893,
            "y2": 785
        },
        {
            "name": "undefined_96",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 756,
            "x2": 985,
            "y2": 785
        },
        {
            "name": "Loose Cylinder Band",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 835,
            "x2": 803,
            "y2": 864
        },
        {
            "name": "undefined_97",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 835,
            "x2": 985,
            "y2": 864
        },
        {
            "name": "undefined_98",
            "type": "text",
            "page": 0,
            "x1": 1024,
            "y1": 835,
            "x2": 1085,
            "y2": 864
        },
        {
            "name": "undefined_99",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 835,
            "x2": 1192,
            "y2": 864
        },
        {
            "name": "undefined_100",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 835,
            "x2": 893,
            "y2": 864
        },
        {
            "name": "undefined_101",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 915,
            "x2": 1192,
            "y2": 944
        },
        {
            "name": "Weight System Removal and Replacement surface",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 915,
            "x2": 803,
            "y2": 944
        },
        {
            "name": "undefined_102",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 915,
            "x2": 893,
            "y2": 944
        },
        {
            "name": "undefined_103",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 915,
            "x2": 985,
            "y2": 944
        },
        {
            "name": "undefined_104",
            "type": "text",
            "page": 0,
            "x1": 1024,
            "y1": 915,
            "x2": 1085,
            "y2": 944
        },
        {
            "name": "undefined_105",
            "type": "text",
            "page": 0,
            "x1": 1024,
            "y1": 994,
            "x2": 1085,
            "y2": 1024
        },
        {
            "name": "undefined_106",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 994,
            "x2": 1192,
            "y2": 1024
        },
        {
            "name": "Emergency Weight Drop or in OW",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 994,
            "x2": 803,
            "y2": 1024
        },
        {
            "name": "undefined_107",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 994,
            "x2": 893,
            "y2": 1024
        },
        {
            "name": "undefined_108",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 994,
            "x2": 985,
            "y2": 1024
        },
        {
            "name": "undefined_118",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 1083,
            "x2": 985,
            "y2": 1112
        },
        {
            "name": "undefined_119",
            "type": "text",
            "page": 0,
            "x1": 1024,
            "y1": 1083,
            "x2": 1085,
            "y2": 1112
        },
        {
            "name": "undefined_120",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 1083,
            "x2": 1192,
            "y2": 1112
        },
        {
            "name": "Skin Diving Skills",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 1083,
            "x2": 803,
            "y2": 1112
        },
        {
            "name": "undefined_122",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 1083,
            "x2": 893,
            "y2": 1112
        },
        {
            "name": "undefined_123",
            "type": "text",
            "page": 0,
            "x1": 914,
            "y1": 1172,
            "x2": 985,
            "y2": 1202
        },
        {
            "name": "undefined_124",
            "type": "text",
            "page": 0,
            "x1": 1024,
            "y1": 1172,
            "x2": 1085,
            "y2": 1202
        },
        {
            "name": "undefined_125",
            "type": "text",
            "page": 0,
            "x1": 1121,
            "y1": 1172,
            "x2": 1192,
            "y2": 1202
        },
        {
            "name": "Note If all Confined Water Dives Confined Water Dive Flexible Skills and Wa",
            "type": "text",
            "page": 0,
            "x1": 731,
            "y1": 1172,
            "x2": 803,
            "y2": 1202
        },
        {
            "name": "undefined_129",
            "type": "text",
            "page": 0,
            "x1": 822,
            "y1": 1172,
            "x2": 893,
            "y2": 1202
        },
        {
            "name": "undefined_36",
            "type": "text",
            "page": 0,
            "x1": 1427,
            "y1": 240,
            "x2": 1498,
            "y2": 270
        },
        {
            "name": "undefined_37",
            "type": "text",
            "page": 0,
            "x1": 1518,
            "y1": 240,
            "x2": 1588,
            "y2": 270
        },
        {
            "name": "undefined_39",
            "type": "text",
            "page": 0,
            "x1": 1903,
            "y1": 240,
            "x2": 1983,
            "y2": 270
        },
        {
            "name": "undefined_40",
            "type": "text",
            "page": 0,
            "x1": 2028,
            "y1": 240,
            "x2": 2117,
            "y2": 270
        },
        {
            "name": "Section 3",
            "type": "text",
            "page": 0,
            "x1": 1336,
            "y1": 271,
            "x2": 1407,
            "y2": 300
        },
        {
            "name": "undefined_42",
            "type": "text",
            "page": 0,
            "x1": 1427,
            "y1": 271,
            "x2": 1498,
            "y2": 300
        },
        {
            "name": "undefined_43",
            "type": "text",
            "page": 0,
            "x1": 1518,
            "y1": 271,
            "x2": 1588,
            "y2": 300
        },
        {
            "name": "undefined_45",
            "type": "text",
            "page": 0,
            "x1": 1903,
            "y1": 271,
            "x2": 1983,
            "y2": 300
        },
        {
            "name": "undefined_46",
            "type": "text",
            "page": 0,
            "x1": 2028,
            "y1": 271,
            "x2": 2117,
            "y2": 300
        },
        {
            "name": "Section 4",
            "type": "text",
            "page": 0,
            "x1": 1336,
            "y1": 302,
            "x2": 1407,
            "y2": 331
        },
        {
            "name": "undefined_48",
            "type": "text",
            "page": 0,
            "x1": 1427,
            "y1": 302,
            "x2": 1498,
            "y2": 331
        },
        {
            "name": "undefined_49",
            "type": "text",
            "page": 0,
            "x1": 1518,
            "y1": 302,
            "x2": 1588,
            "y2": 331
        },
        {
            "name": "undefined_51",
            "type": "text",
            "page": 0,
            "x1": 1903,
            "y1": 302,
            "x2": 1983,
            "y2": 331
        },
        {
            "name": "undefined_52",
            "type": "text",
            "page": 0,
            "x1": 2028,
            "y1": 302,
            "x2": 2117,
            "y2": 331
        },
        {
            "name": "Section 5",
            "type": "text",
            "page": 0,
            "x1": 1336,
            "y1": 332,
            "x2": 1407,
            "y2": 361
        },
        {
            "name": "undefined_56",
            "type": "text",
            "page": 0,
            "x1": 1427,
            "y1": 332,
            "x2": 1498,
            "y2": 361
        },
        {
            "name": "undefined_57",
            "type": "text",
            "page": 0,
            "x1": 1518,
            "y1": 332,
            "x2": 1588,
            "y2": 361
        },
        {
            "name": "undefined_59",
            "type": "text",
            "page": 0,
            "x1": 1903,
            "y1": 332,
            "x2": 1983,
            "y2": 361
        },
        {
            "name": "undefined_60",
            "type": "text",
            "page": 0,
            "x1": 2028,
            "y1": 332,
            "x2": 2117,
            "y2": 361
        },
        {
            "name": "Quick Review",
            "type": "text",
            "page": 0,
            "x1": 1336,
            "y1": 375,
            "x2": 1407,
            "y2": 404
        },
        {
            "name": "undefined_61",
            "type": "text",
            "page": 0,
            "x1": 1427,
            "y1": 375,
            "x2": 1498,
            "y2": 404
        },
        {
            "name": "undefined_62",
            "type": "text",
            "page": 0,
            "x1": 1518,
            "y1": 375,
            "x2": 1588,
            "y2": 404
        },
        {
            "name": "undefined_64",
            "type": "text",
            "page": 0,
            "x1": 1903,
            "y1": 375,
            "x2": 1983,
            "y2": 404
        },
        {
            "name": "undefined_65",
            "type": "text",
            "page": 0,
            "x1": 2028,
            "y1": 375,
            "x2": 2117,
            "y2": 404
        },
        {
            "name": "Dive 2",
            "type": "text",
            "page": 0,
            "x1": 1275,
            "y1": 641,
            "x2": 1328,
            "y2": 671
        },
        {
            "name": "undefined_79",
            "type": "text",
            "page": 0,
            "x1": 1348,
            "y1": 641,
            "x2": 1402,
            "y2": 671
        },
        {
            "name": "undefined_80",
            "type": "text",
            "page": 0,
            "x1": 1421,
            "y1": 641,
            "x2": 1475,
            "y2": 671
        },
        {
            "name": "Initials 1_2",
            "type": "text",
            "page": 0,
            "x1": 1494,
            "y1": 612,
            "x2": 1547,
            "y2": 637
        },
        {
            "name": "Initials 2_2",
            "type": "text",
            "page": 0,
            "x1": 1494,
            "y1": 641,
            "x2": 1547,
            "y2": 671
        },
        {
            "name": "undefined_81",
            "type": "text",
            "page": 0,
            "x1": 1583,
            "y1": 641,
            "x2": 1654,
            "y2": 671
        },
        {
            "name": "Dive 4",
            "type": "text",
            "page": 0,
            "x1": 1728,
            "y1": 641,
            "x2": 1781,
            "y2": 671
        },
        {
            "name": "undefined_82",
            "type": "text",
            "page": 0,
            "x1": 1801,
            "y1": 641,
            "x2": 1854,
            "y2": 671
        },
        {
            "name": "undefined_83",
            "type": "text",
            "page": 0,
            "x1": 1874,
            "y1": 641,
            "x2": 1928,
            "y2": 671
        },
        {
            "name": "Initials 1_3",
            "type": "text",
            "page": 0,
            "x1": 1956,
            "y1": 612,
            "x2": 2010,
            "y2": 637
        },
        {
            "name": "Initials 2_3",
            "type": "text",
            "page": 0,
            "x1": 1956,
            "y1": 641,
            "x2": 2010,
            "y2": 671
        },
        {
            "name": "Dive 1",
            "type": "text",
            "page": 0,
            "x1": 1275,
            "y1": 612,
            "x2": 1328,
            "y2": 637
        },
        {
            "name": "undefined_84",
            "type": "text",
            "page": 0,
            "x1": 1348,
            "y1": 612,
            "x2": 1401,
            "y2": 637
        },
        {
            "name": "undefined_85",
            "type": "text",
            "page": 0,
            "x1": 1421,
            "y1": 612,
            "x2": 1475,
            "y2": 637
        },
        {
            "name": "undefined_86",
            "type": "text",
            "page": 0,
            "x1": 1583,
            "y1": 612,
            "x2": 1654,
            "y2": 637
        },
        {
            "name": "Dive 3",
            "type": "text",
            "page": 0,
            "x1": 1728,
            "y1": 612,
            "x2": 1781,
            "y2": 637
        },
        {
            "name": "undefined_87",
            "type": "text",
            "page": 0,
            "x1": 1801,
            "y1": 612,
            "x2": 1854,
            "y2": 637
        },
        {
            "name": "undefined_88",
            "type": "text",
            "page": 0,
            "x1": 1874,
            "y1": 612,
            "x2": 1928,
            "y2": 637
        },
        {
            "name": "undefined_89",
            "type": "text",
            "page": 0,
            "x1": 2045,
            "y1": 612,
            "x2": 2117,
            "y2": 637
        },
        {
            "name": "undefined_90",
            "type": "text",
            "page": 0,
            "x1": 2045,
            "y1": 641,
            "x2": 2117,
            "y2": 671
        },
        {
            "name": "undefined_126",
            "type": "text",
            "page": 0,
            "x1": 1708,
            "y1": 1128,
            "x2": 1814,
            "y2": 1158
        }
    ]
}


def generate_master_mask_file(force=False):
    """Create the master mask JSON from the embedded hardcoded definition."""
    try:
        if FIELDS_FILE.exists() and not force:
            return True

        with FIELDS_FILE.open("w", encoding="utf-8") as f:
            json.dump(HARDCODED_MASK, f, indent=4, ensure_ascii=False)

        print("MASTER MASK GENERATED:", FIELDS_FILE)
        return True
    except Exception as e:
        print("MASTER MASK GENERATION ERROR:", e)
        return False


def load_fields():
    # Always use the embedded master definition. If the external JSON is
    # missing, recreate it automatically so other parts of the program
    # that expect the file can still use it.
    generate_master_mask_file(force=False)
    return json.loads(json.dumps(HARDCODED_MASK.get("fields", [])))

def save_fields(fields):
    with FIELDS_FILE.open("w", encoding="utf-8") as f:
        json.dump({"fields": fields}, f, indent=4)

def load_state():
    if not STATE_FILE.exists():
        return {}
    with STATE_FILE.open("r", encoding="utf-8") as f:
        return json.load(f)

def save_state_with_locations():
    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(state, f, indent=4)

fields = []
state = load_state()
comments_db = load_comments_db()

# SHow jason  mask
def toggle_json_names():

    global show_json_names

    show_json_names = not show_json_names

    update_button_colors()

    render_page()
def show_program_fields():

    fields_used = """
PROGRAM FIELD LOGIC (OW 10056 document)

Student:(Left block)
-----------
Student Name
student_signature (Right block at the end)
Stu_day
Stu_month
Stu_year

Init Instructor Blocks: (Left  block)
(Instructors involved)
-----------------------
init_padi_instructor_1
init_padi_instructor_2

Init_Instructor_Signature_1 (All PADI Instructors #1 who initial this document ... )
Init_Instructor_Signature_2 (All PADI Instructors #1 who initial this document ... )

Init_PADI_no_1
Init_PADI_no_2

Init_Dive_Resort_No_1
Init_Dive_Resort_No_2

Init_day_1
Init_month_1
Init_year_1

Init_day_2
Init_month_2
Init_year_2

Init_Phone_1
Init_Phone_2

Init_Email_1
Init_Email_2

Instructor Signoffs:
--------------------
Instructor_signature_3  (All Confined have been completed)
Instructor_signature_4  (All Knowledge Development sessions listed above have been completed, Quizzes/Exams passed)
Instructor_signature_5  (All Open Water Dive Flexible Skills listed above have been completed.)
Instructor_signature_6  (All requirements for certification as a PADI Scuba Diver have been met)
Instructor_signature_7  (All requirements for certification as a PADI Open Water Diver have been met.)

PADI_no_3 to PADI_no_7
day_3 to day_7
month_3 to month_7
year_3 to year_7

CW Auto-Populate Pattern:
-------------------------
CW1_day ... CW24_day  (Starts at CW 1*)
CW1_month ... CW24_month
CW1_year ... CW24_year
CW1_initials ... CW24_initials
CW1_padi ... CW24_padi (ends at the year for the final signoff)

Dive Logic:
-----------
Dive_1 ... Dive_10
Dive_initials_1 ... Dive_initials_10
Dive_padi_1 ... Dive_padi_10

Special Logic:
--------------
CW12 auto-fills Dive_4
"""

    win = tk.Toplevel(root)
    win.title("Program Field Logic")
    win.geometry("700x700")

    txt = tk.Text(win, wrap="word")
    txt.pack(fill="both", expand=True)

    txt.insert("1.0", fields_used)
    txt.config(state="disabled")

# ---------------- Signature Drawing Window ----------------

def draw_student_signature_window(field_name):

    win = tk.Toplevel(root)
    win.title("Student Signature")
    win.geometry("620x320")

    width, height = 600, 120

    canvas_sig = tk.Canvas(
        win,
        bg="#E6E6E6",
        width=width,
        height=height
    )
    canvas_sig.pack(pady=10)

    img = Image.new("RGB", (width, height), "white")
    draw_obj = ImageDraw.Draw(img)

    last = {"x": None, "y": None}

    def start_draw(event):
        last["x"], last["y"] = event.x, event.y

    def draw_line(event):
        if last["x"] is not None:
            canvas_sig.create_line(
                last["x"], last["y"], event.x, event.y,
                fill="black", width=3
            )
            draw_obj.line(
                (last["x"], last["y"], event.x, event.y),
                fill="black", width=3
            )
        last["x"], last["y"] = event.x, event.y

    canvas_sig.bind("<Button-1>", start_draw)
    canvas_sig.bind("<B1-Motion>", draw_line)

    def clear_canvas():
        canvas_sig.delete("all")
        draw_obj.rectangle((0, 0, width, height), fill="white")

    def save_signature():

        filename = SIGNATURE_DIR / f"{field_name}_student.png"
        img.save(filename)

        state[field_name] = str(filename)

        d = date_picker.get_date()

        state["Stu_day"] = str(d.day)
        state["Stu_month"] = [
            "Jan","Feb","Mar","Apr","May","Jun",
            "Jul","Aug","Sep","Oct","Nov","Dec"
        ][d.month - 1]
        state["Stu_year"] = str(d.year)

        save_state_with_locations()

        redraw_all_text_fields()
        redraw_all_signatures()

        win.destroy()

    def delete_signature():
        if field_name in state:
            del state[field_name]
            save_state_with_locations()
            redraw_all_signatures()
        win.destroy()

    # Buttons
    tk.Button(
        win,
        text="Clear",
        command=clear_canvas
    ).pack(side="left", padx=20)

    tk.Button(
        win,
        text="Save Signature",
        command=save_signature
    ).pack(side="right", padx=20)

    tk.Button(
        win,
        text="Delete Signature",
        command=delete_signature
    ).pack(side="left", padx=20)

def draw_signature_window(name, padi_number, signature_var):

    win = tk.Toplevel(root)
    win.title(f"Draw Signature for {name}")
    win.geometry("620x320")

    width, height = 600, 120

    canvas_sig = tk.Canvas(
        win,
        bg="#E6E6E6",
        width=width,
        height=height
    )
    canvas_sig.pack(pady=10)

    img = Image.new("RGB", (width, height), "white")
    draw_obj = ImageDraw.Draw(img)

    last = {"x": None, "y": None}

    def start_draw(event):
        last["x"], last["y"] = event.x, event.y

    def draw_line(event):

        if last["x"] is not None:

            canvas_sig.create_line(
                last["x"],
                last["y"],
                event.x,
                event.y,
                fill="black",
                width=3
            )

            draw_obj.line(
                (last["x"], last["y"], event.x, event.y),
                fill="black",
                width=3
            )

        last["x"], last["y"] = event.x, event.y

    canvas_sig.bind("<Button-1>", start_draw)
    canvas_sig.bind("<B1-Motion>", draw_line)

    def clear_canvas():
        canvas_sig.delete("all")
        draw_obj.rectangle(
            (0, 0, width, height),
            fill="white"
        )

    def save_signature():

        safe_padi = re.sub(
            r"[^A-Za-z0-9_-]",
            "_",
            str(padi_number)
        )

        filename = SIGNATURE_DIR / f"{safe_padi}.png"

        img.save(filename)

        signature_var.set(str(filename))

        messagebox.showinfo(
            "Saved",
            f"Signature saved as:\n{filename}"
        )

        win.destroy()

        try:
            instructor_window.lift()
            instructor_window.focus_force()
        except:
            pass

    tk.Button(
        win,
        text="Clear",
        command=clear_canvas
    ).pack(side="left", padx=20, pady=5)

    tk.Button(
        win,
        text="Save Signature",
        command=save_signature
    ).pack(side="right", padx=20, pady=5)

# ---------------- PDF Viewer ----------------

pdf_path = None
pages = []
current_page = 0

def render_page():

    global zoom_level

    if not pages:
        return

    #
    # HARD RESET OF CANVAS
    #
    canvas_pdf.delete("all")

    for child in canvas_pdf.winfo_children():
        child.destroy()

    canvas_pdf.image = None

    if hasattr(canvas_pdf, "signature_images"):
        canvas_pdf.signature_images.clear()

    root.update()

    print(
        "AFTER DELETE ALL =",
        canvas_pdf.find_all()
    )

    #
    # RENDER CURRENT PAGE
    #
    page = pages[current_page]

    w, h = page.size

    new_w = int(w * zoom_level)
    new_h = int(h * zoom_level)

    resized = page.resize(
        (new_w, new_h),
        Image.LANCZOS
    )

    tk_img = ImageTk.PhotoImage(resized)

    canvas_pdf.image = tk_img

    image_id = canvas_pdf.create_image(
        0,
        0,
        anchor="nw",
        image=tk_img
    )

    print(
        "AFTER CREATE IMAGE =",
        canvas_pdf.find_all()
    )

    print(
        "IMAGE ID =",
        image_id
    )

    canvas_pdf.config(
        scrollregion=(0, 0, new_w, new_h)
    )

    draw_all_field_boxes()
    redraw_all_text_fields()
    redraw_all_signatures()
    redraw_all_checkboxes()

    #
    # MAKE SURE OVERLAYS ARE ON TOP
    #
    canvas_pdf.tag_raise("text_drawn")
    canvas_pdf.tag_raise("signature_drawn")
    canvas_pdf.tag_raise("checkbox_drawn")
    canvas_pdf.tag_raise("field_box")


# ---------------- Advanced Field Detection ----------------

def detect_acroform_fields(pdf_path, pages):
    reader = PdfReader(pdf_path)
    root = reader.trailer.get("/Root", {})
    if "/AcroForm" not in root:
        return []

    form = root["/AcroForm"]
    fields_raw = form.get("/Fields", [])

    detected = []

    for field_ref in fields_raw:
        field = field_ref.get_object()

        ftype = field.get("/FT")
        rect = field.get("/Rect")
        page_ref = field.get("/P")

        if not rect or not page_ref:
            continue

        try:
            page_obj = page_ref.get_object()
        except:
            page_obj = page_ref

        page_index = None
        for i, p in enumerate(reader.pages):
            if p.indirect_reference.idnum == page_obj.indirect_reference.idnum:
                page_index = i
                break

        if page_index is None:
            print("WARNING: Could not resolve page for field:", field)
            continue

        x1_pdf, y1_pdf, x2_pdf, y2_pdf = rect

        pdf_page = reader.pages[page_index]
        pdf_w = float(pdf_page.mediabox.width)
        pdf_h = float(pdf_page.mediabox.height)

        img_w, img_h = pages[page_index].size

        scale_x = img_w / pdf_w
        scale_y = img_h / pdf_h

        x1_img = int(x1_pdf * scale_x)
        x2_img = int(x2_pdf * scale_x)
        y1_img = int((pdf_h - y2_pdf) * scale_y)
        y2_img = int((pdf_h - y1_pdf) * scale_y)

        if ftype == "/Sig":
            my_type = "signature"
        elif ftype == "/Tx":
            my_type = "text"
        elif ftype == "/Btn":
            my_type = "checkbox"
        else:
            my_type = "unknown"

        detected.append({
            "name": field.get("/T", f"{my_type}_field_{len(detected)+1}"),
            "type": my_type,
            "page": page_index,
            "x1": x1_img,
            "y1": y1_img,
            "x2": x2_img,
            "y2": y2_img
        })

    return detected
def build_pdf_field_mapping():
    """
    Map application/mask fields to the real AcroForm widgets.

    The mask coordinates are 200-DPI image coordinates, while the PDF stores
    widget rectangles in PDF points.  The PADI PDF also uses many generic
    field names (for example "CW 2", "PADI No", "undefined_9") while the
    application uses semantic names such as "CW2_day".

    Therefore mapping is based primarily on page + rectangle position.
    Exact names are preferred only when they occur at the same location.
    Each real PDF widget is claimed once so duplicate OCR/mask entries do
    not overwrite one another.
    """
    global pdf_field_mapping, pdf_field_rects

    pdf_field_mapping = {}
    pdf_field_rects = {}

    if not pdf_path:
        return

    try:
        reader = PdfReader(pdf_path)
    except Exception as e:
        print("Error reading PDF fields:", e)
        return

    render_sizes = {
        page_index: page_image.size
        for page_index, page_image in enumerate(pages)
    }

    actual_widgets = []

    for page_index, page in enumerate(reader.pages):
        pdf_w = float(page.mediabox.width)
        pdf_h = float(page.mediabox.height)

        if page_index in render_sizes:
            img_w, img_h = render_sizes[page_index]
            scale_x = img_w / pdf_w
            scale_y = img_h / pdf_h
        else:
            scale_x = 200.0 / 72.0
            scale_y = 200.0 / 72.0

        annots_ref = page.get("/Annots")
        if not annots_ref:
            continue

        try:
            annots = annots_ref.get_object()
        except Exception:
            annots = annots_ref

        for annot_ref in annots:
            try:
                annot = annot_ref.get_object()
            except Exception:
                annot = annot_ref

            if annot.get("/Subtype") != "/Widget":
                continue

            name_obj = annot.get("/T")
            rect = annot.get("/Rect")
            ftype = annot.get("/FT")

            if not name_obj or not rect:
                continue

            if not ftype and annot.get("/Parent"):
                try:
                    parent = annot["/Parent"].get_object()
                    ftype = parent.get("/FT")
                except Exception:
                    pass

            name = str(name_obj)

            x1_pdf, y1_pdf, x2_pdf, y2_pdf = [float(v) for v in rect]

            x1_img = x1_pdf * scale_x
            x2_img = x2_pdf * scale_x
            y1_img = (pdf_h - y2_pdf) * scale_y
            y2_img = (pdf_h - y1_pdf) * scale_y

            if ftype == "/Sig":
                widget_type = "signature"
            elif ftype == "/Tx":
                widget_type = "text"
            elif ftype == "/Btn":
                widget_type = "checkbox"
            else:
                widget_type = "unknown"

            actual_widgets.append({
                "name": name,
                "type": widget_type,
                "page": page_index,
                "x1": x1_img,
                "y1": y1_img,
                "x2": x2_img,
                "y2": y2_img,
            })

    claimed = set()

    def box_score(mask_field, widget):
        return (
            abs(float(mask_field["x1"]) - widget["x1"]) +
            abs(float(mask_field["y1"]) - widget["y1"]) +
            abs(float(mask_field["x2"]) - widget["x2"]) +
            abs(float(mask_field["y2"]) - widget["y2"])
        )

    for mask_field in fields:
        mask_name = mask_field["name"]
        page_index = mask_field["page"]

        candidates = [
            w for w in actual_widgets
            if w["page"] == page_index and w["name"] not in claimed
        ]

        if not candidates:
            pdf_field_mapping[mask_name] = None
            continue

        best = min(candidates, key=lambda w: box_score(mask_field, w))
        best_score = box_score(mask_field, best)

        if best_score > 10:
            pdf_field_mapping[mask_name] = None
            continue

        exact_candidates = [
            w for w in candidates
            if w["name"] == mask_name and box_score(mask_field, w) <= 10
        ]
        if exact_candidates:
            best = min(exact_candidates, key=lambda w: box_score(mask_field, w))

        claimed.add(best["name"])
        pdf_field_mapping[mask_name] = best["name"]

        pdf_field_rects[best["name"]] = (
            best["page"],
            best["x1"],
            best["y1"],
            best["x2"],
            best["y2"],
        )

    print("PDF FIELD MAPPING (coordinate based):")
    mapped_count = 0
    for app_name, pdf_name in pdf_field_mapping.items():
        if pdf_name:
            mapped_count += 1
            print(f"{app_name} -> {pdf_name}")

    print(
        f"Mapped {mapped_count} of {len(fields)} mask fields "
        f"to {len(claimed)} real PDF widgets."
    )

def heuristic_signature_boxes(page_image, page_index):
    w, h = page_image.size
    gray = ImageOps.grayscale(page_image)
    pixels = gray.load()

    candidates = []
    min_length = int(w * 0.2)
    threshold = 60

    for y in range(int(h * 0.2), int(h * 0.9)):
        dark_run = 0
        start_x = None
        for x in range(int(w * 0.05), int(w * 0.95)):
            if pixels[x, y] < threshold:
                if dark_run == 0:
                    start_x = x
                dark_run += 1
            else:
                if dark_run >= min_length:
                    candidates.append({
                        "name": f"signature_heuristic_{len(candidates)+1}",
                        "type": "signature",
                        "page": page_index,
                        "x1": start_x,
                        "y1": y - 10,
                        "x2": x,
                        "y2": y + 10
                    })
                dark_run = 0
                start_x = None

    return candidates

def save_state_with_locations():

    save_data = {}

    for f in fields:

        name = f["name"]

        if name not in state:
            continue

        save_data[name] = {
        "value": state[name],
        "page": f["page"],
        "x1": f["x1"],
        "y1": f["y1"],
        "x2": f["x2"],
        "y2": f["y2"],
        "type": f["type"]
        }


    with STATE_FILE.open("w", encoding="utf-8") as f:
        json.dump(save_data, f, indent=4)

def clear_signature(field_name):
    if field_name in state:
        del state[field_name]
    save_state_with_locations()
    redraw_all_signatures()


def load_state_by_location():

    if not STATE_FILE.exists():
        return {}

    try:
        with STATE_FILE.open("r", encoding="utf-8") as f:
            old_data = json.load(f)

    except Exception:
        return {}

    new_state = {}

    for current_field in fields:

        best_match = None
        best_score = 999999

        for old_name, old_info in old_data.items():

            if not isinstance(old_info, dict):
                continue

            #
            # FIRST TRY EXACT FIELD NAME MATCH
            #
            if old_name == current_field["name"]:

                print(
                    "NAME MATCH:",
                    current_field["name"],
                    "<--",
                    old_info.get("value")
                )

                new_state[current_field["name"]] = (
                    old_info.get("value")
                )

                best_match = None
                break

            #
            # OTHERWISE FALL BACK TO LOCATION MATCHING
            #
            if current_field["page"] != old_info.get("page"):
                continue

            score = (
                abs(current_field["x1"] - old_info["x1"]) +
                abs(current_field["y1"] - old_info["y1"]) +
                abs(current_field["x2"] - old_info["x2"]) +
                abs(current_field["y2"] - old_info["y2"])
            )

            if score < best_score:
                best_score = score
                best_match = old_info

        #
        # ONLY USE LOCATION MATCH IF
        # NAME MATCH DID NOT ALREADY HAPPEN
        #
        if (
            current_field["name"] not in new_state
            and best_match
            and best_score < 10
        ):

            print(
                "LOCATION MATCH:",
                current_field["name"],
                "<--",
                best_match.get("value"),
                "score=",
                best_score
            )

            new_state[current_field["name"]] = (
                best_match.get("value")
            )

    print("new_state =", new_state)
    print("LOADED STATE COUNT =", len(new_state))

    return new_state


def load_pdf_field_values(pdf_file):

    values = {}

    try:

        reader = PdfReader(pdf_file)

        pdf_fields = reader.get_fields()

        print("\n========================")
        print("ACTUAL PDF FIELD NAMES")
        print("========================")

        for name in sorted(pdf_fields.keys()):
            print(repr(name))

        print("========================\n")

        for name, info in pdf_fields.items():

            if info.get("/FT") == "/Btn":

                print("\nCHECKBOX FIELD:", name)

                for k, v in info.items():
                    print("   ", k, "=", v)

        print("================================")
        print("PDF FIELDS FROM EXPORTED FILE")
        print("================================")
        print(pdf_fields)

        if not pdf_fields:
            print("NO FIELDS FOUND")
            return values

        for field_name, info in pdf_fields.items():

            print("\n================================")
            print("FIELD:", field_name)
            print("================================")

            for k, v in info.items():
                print(k, "=", v)

            value = info.get("/V")

            print("VALUE =", value)
            print("FT    =", info.get("/FT"))

            if value is not None:
                values[field_name] = str(value)

        print("LOADED VALUES =", values)

    except Exception as e:

        print("FIELD LOAD ERROR:", e)

    return values


def pdf_values_to_state(pdf_values):
    """
    Convert raw PDF AcroForm values into the application's state dictionary.
    Signature fields in PDFs contain only metadata and must be ignored.
    """

    loaded_state = {}

    for app_name, pdf_name in pdf_field_mapping.items():

        # Skip if PDF field not present
        if pdf_name not in pdf_values:
            continue

        value = pdf_values[pdf_name]

        # Find field info from mask
        field_info = next((f for f in fields if f["name"] == app_name), None)
        if not field_info:
            continue

        # ⭐ SIGNATURE FIX ⭐
        # Ignore ALL signature fields from PDF
        if field_info["type"] == "signature":
            continue

        # Checkbox handling
        if field_info["type"] == "checkbox":
            loaded_state[app_name] = (
                str(value).lower() not in ("/off", "off", "", "false")
            )
            continue

        # Normal text fields
        loaded_state[app_name] = value

    return loaded_state


def load_pdf():

    global pdf_path
    global pages
    global current_page
    global zoom_level
    global state
    global reopened_exported_pdf
    global loaded_pdf_values

    pdf_path = filedialog.askopenfilename(
        filetypes=[("PDF Files", "*.pdf")],
        title="Select a PADI PDF"
    )

    if not pdf_path:
        pdf_label.config(text="No PDF loaded")
        return

    #
    # INSPECT PDF
    #
    try:

        reader = PdfReader(pdf_path)

        pdf_fields = reader.get_fields()

        print("")
        print("================================")
        print("PDF FIELD TEST")
        print("================================")

        if pdf_fields:

            for name, info in pdf_fields.items():

                value = info.get("/V")

                print(
                    "FIELD:",
                    name,
                    "VALUE:",
                    value
                )

        else:

            print("NO ACROFORM FIELDS FOUND")

        print("================================")
        print("")

    except Exception as e:

        print("FIELD TEST ERROR:", e)

    pdf_label.config(
        text=f"Loaded: {Path(pdf_path).name}"
    )

    # Load the saved comment into the main-menu textbox.
    display_comment(pdf_path)

    #
    # DETECT WHETHER PDF ALREADY HAS DATA
    #
    reopened_exported_pdf = False

    try:

        reader = PdfReader(pdf_path)
        pdf_fields = reader.get_fields()

        if pdf_fields:

            for field_name, info in pdf_fields.items():

                value = info.get("/V")

                if value not in (None, ""):

                    reopened_exported_pdf = True
                    break

    except Exception as e:

        print("PDF DETECTION ERROR:", e)

    print(
        "REOPENED EXPORTED PDF =",
        reopened_exported_pdf
    )

    auto_mask = BASE_DIR / "10056_OW_Records_mask.json"

    fields.clear()

    if auto_mask.exists():

        try:

            with auto_mask.open(
                "r",
                encoding="utf-8"
            ) as f:

                data = json.load(f)

            fields.extend(
                data.get("fields", [])
            )

            # Remove duplicate OCR-generated fields
            #fields[:] = [
            #    f for f in fields
            #    if not (
            #        f["name"].startswith("undefined")
            #        or re.fullmatch(r"CW \d+", f["name"])
            #        or re.fullmatch(r"Initials .*", f["name"])
            #        or re.fullmatch(r"Section .*", f["name"])
            #        or re.fullmatch(r"Dive \d+", f["name"])
            #    )
#]

            print("FIELDS AFTER CLEANUP =", len(fields))


            #
            # BUILD FIELD MAPPING
            #
            #build_pdf_field_mapping()
            if reopened_exported_pdf:

                pages = convert_from_path(
                    str(BASE_DIR / "ow_report.pdf")
                )

            else:

                pages = convert_from_path(pdf_path)
            #
            # LOAD FORM VALUES FROM EXPORTED PDF
            #
            build_pdf_field_mapping()
            print("\n========= DUPLICATE TEST =========")

            seen = {}

            for app_field, pdf_field in pdf_field_mapping.items():

                print(app_field, "->", pdf_field)

                seen.setdefault(pdf_field, []).append(app_field)

            for pdf_field, apps in seen.items():

                if len(apps) > 1:
                    print("DUPLICATE PDF FIELD:", pdf_field)
                    print("USED BY:", apps)

            print("==================================")

            if reopened_exported_pdf:

                print(
                    "READING VALUES FROM EXPORTED PDF"
                )

                pdf_values = load_pdf_field_values(
                    pdf_path
                )

                print(
                    "PDF_VALUES =",
                    pdf_values
                )

                state = pdf_values_to_state(
                    pdf_values
                )

                #
                # Restore signatures from saved state file
                #
                saved_state = load_state_by_location()

                for field in fields:
                    if field["type"] != "signature":
                        continue

                    name = field["name"]

                    pdf_val = state.get(name)
                    json_val = saved_state.get(name)

                    # Restore JSON signature ONLY if PDF has no signature AND no new signature was drawn
                    if pdf_val in (None, "", "/Sig") and json_val:
                        state[name] = json_val



                print(
                    "Student Name in PDF =",
                    pdf_values.get("Student Name")
                )

                print(
                    "Student Name mapping =",
                    pdf_field_mapping.get("Student Name")
                )

                print(
                    "STATE LOADED FROM PDF =",
                    state
                )

            else:

                print(
                    "BLANK TEMPLATE PDF"
                )

                state = {}

            loaded_pdf_values = dict(state)

            print(
                "STATE AFTER LOAD =",
                state
            )

            print(
                "STUDENT NAME AFTER LOAD =",
                state.get("Student Name")
            )

        except Exception as e:

            messagebox.showerror(
                "Error",
                f"Failed to load mask file:\n{e}"
            )

            state = {}

    else:

        messagebox.showwarning(
            "Mask File Missing",
            f"No mask file found:\n{auto_mask.name}"
        )

        load_mask_file()

        state = {}


    for k, v in pdf_field_mapping.items():

        print(k, "=>", v)

    current_page = 0
    zoom_level = zoom_level_def

    root.update_idletasks()
    render_page()



def close_pdf():

    global pdf_path
    global pages
    global current_page
    global state
    global fields
    global loaded_pdf_values
    global pdf_field_mapping
    global reopened_exported_pdf

    pdf_path = None
    pages = []
    current_page = 0

    state = {}
    fields.clear()

    loaded_pdf_values = {}
    pdf_field_mapping = {}
    reopened_exported_pdf = False

    canvas_pdf.delete("all")

    canvas_pdf.config(
        scrollregion=(0, 0, 0, 0)
    )

    if hasattr(canvas_pdf, "signature_images"):
        canvas_pdf.signature_images.clear()

    pdf_label.config(
        text="No PDF loaded"
    )

    if "comment_text" in globals():
        comment_text.delete("1.0", "end")

    status_label.config(
        text="PDF and Mask Closed"
    )


def next_page():
    global current_page
    if not pages:
        return
    if current_page < len(pages) - 1:
        current_page += 1
        render_page()

def prev_page():
    global current_page
    if not pages:
        return
    if current_page > 0:
        current_page -= 1
        render_page()

# ---------------- Zoom Controls ----------------

def zoom_in():
    global zoom_level
    if zoom_level < MAX_ZOOM:
        zoom_level += ZOOM_STEP
        render_page()

def zoom_out():
    global zoom_level
    if zoom_level > MIN_ZOOM:
        zoom_level -= ZOOM_STEP
        render_page()

def zoom_fit():
    global zoom_level
    if not pages:
        return

    page = pages[current_page]
    w, h = page.size

    canvas_w = canvas_pdf.winfo_width()
    canvas_h = canvas_pdf.winfo_height()

    zoom_w = canvas_w / w
    zoom_h = canvas_h / h

    zoom_level = min(zoom_w, zoom_h)
    render_page()

# ---------------- Field Detection ----------------

def find_field(x, y, page_index):
    for f in fields:
        if f.get("page", 0) != page_index:
            continue
        if f["x1"] <= x <= f["x2"] and f["y1"] <= y <= f["y2"]:
            return f
    return None


def populate_cw_row(prefix):
    """Populate day, month, year, initials, and PADI# for a CW row."""

    # Date fields
    d = date_picker.get_date()

    state[f"{prefix}_day"] = str(d.day)
    state[f"{prefix}_month"] = [
        "Jan","Feb","Mar","Apr","May","Jun",
        "Jul","Aug","Sep","Oct","Nov","Dec"
    ][d.month - 1]

    state[f"{prefix}_year"] = str(d.year)

    # Instructor fields
    selected_name = instructor_var.get()

    instructor = next(
        (
            i for i in instructor_list
            if i["name"] == selected_name
        ),
        None
    )

    if instructor:

        state[f"{prefix}_initials"] = instructor.get(
            "initials",
            ""
        )

        state[f"{prefix}_padi"] = instructor.get(
            "padi_number",
            ""
        )

        # Auto-credit Confined Dive 4 when CW12 is completed
        if prefix == "CW12":

            state["Dive_4"] = "CONF"

            state["Dive_initials_4"] = instructor.get(
                "initials",
                ""
            )

            state["Dive_padi_4"] = instructor.get(
                "padi_number",
                ""
            )

    redraw_all_text_fields()
    redraw_all_signatures()

def redraw_all_text_fields():

    print(
        "ALL ITEMS BEFORE DELETE =",
        canvas_pdf.find_all()
    )

    print(
        "TEXT ITEMS BEFORE DELETE =",
        canvas_pdf.find_withtag("text_drawn")
    )

    canvas_pdf.delete("text_drawn")

    print(
        "TEXT ITEMS AFTER DELETE =",
        canvas_pdf.find_withtag("text_drawn")
    )

    canvas_pdf.delete("text_drawn") 

    if state is None:
        print("ERROR: state is None")
        return

    for f in fields:

        if f.get("page", 0) != current_page:
            continue

        if f["type"] not in ("day", "month", "year", "text"):
            continue

        if f["name"] == "Student Name":
            print(
                "DRAW STUDENT NAME:",
                repr(state.get(f["name"])),
                f["x1"],
                f["y1"]
            )

        value = state.get(f["name"])

        print(
            "DRAW:",
            repr(f["name"]),
            "=",
            repr(value)
        )

        if not value:
            continue

        x = int(f["x1"] * zoom_level)
        y = int(f["y1"] * zoom_level)

        print(
            "COORD:",
            f["name"],
            f["x1"],
            f["y1"]
        )
        item = canvas_pdf.create_text(
            x,
            y,
            anchor="nw",
            text=str(value),
            fill="black",
            font=("Helvetica", 10),
            tags="text_drawn"
        )


    # force text above image
    canvas_pdf.tag_raise("text_drawn")

    # keep boxes above text
    canvas_pdf.tag_raise("field_box")


def start_inline_edit(field):

    print("********************************")
    print("START_INLINE_EDIT CALLED")
    print("FIELD =", field["name"])
    print("STATE VALUE =", state.get(field["name"]))
    print("********************************")

    global editing_active
    global current_inline_entry

    if editing_active:
        return

    # Destroy any previous editor
    if current_inline_entry:
        try:
            current_inline_entry.destroy()
        except:
            pass

        current_inline_entry = None

    editing_active = True

    canvas_pdf.unbind("<Button-1>")

    current_value = state.get(field["name"], "")

    print("CURRENT VALUE =", repr(current_value))

    entry_var = tk.StringVar(value=current_value)

    entry = tk.Entry(
        canvas_pdf,
        textvariable=entry_var,
        width=20
    )

    current_inline_entry = entry

    x = int(field["x1"] * zoom_level)
    y = int(field["y1"] * zoom_level)

    # hide existing drawn text while editing
    #canvas_pdf.delete("text_drawn")

    entry_window = canvas_pdf.create_window(
        x,
        y,
        anchor="nw",
        window=entry
    )

    def save_inline(event=None):

        global editing_active
        global current_inline_entry

        new_value = entry_var.get()

        print("ENTRY VALUE =", repr(new_value))

        state[field["name"]] = new_value

        print(
            "SAVED:",
            field["name"],
            "=",
            state[field["name"]]
        )

        canvas_pdf.delete(entry_window)

        if entry.winfo_exists():
            entry.destroy()

        current_inline_entry = None
        editing_active = False

        canvas_pdf.bind("<Button-1>", on_pdf_click)

        #redraw_all_text_fields()
        #save_state_with_locations()
        render_page()
        save_state_with_locations()

    def cancel_inline(event=None):

        global editing_active
        global current_inline_entry

        canvas_pdf.delete(entry_window)

        if entry.winfo_exists():
            entry.destroy()

        current_inline_entry = None
        editing_active = False

        canvas_pdf.bind("<Button-1>", on_pdf_click)

        #redraw_all_text_fields()
        render_page()

    entry.bind("<Return>", save_inline)
    entry.bind("<Escape>", cancel_inline)

    entry.focus_set()
    entry.select_range(0, tk.END)



def redraw_all_checkboxes():

    canvas_pdf.delete("checkbox_drawn")

    for f in fields:

        if f.get("page", 0) != current_page:
            continue

        if f["type"] != "checkbox":
            continue

        checked = bool(state.get(f["name"], False))

        if not checked:
            continue

        x1 = int(f["x1"] * zoom_level)
        y1 = int(f["y1"] * zoom_level)
        x2 = int(f["x2"] * zoom_level)
        y2 = int(f["y2"] * zoom_level)

        canvas_pdf.create_text(
            (x1 + x2) // 2,
            (y1 + y2) // 2,
            text="✓",
            fill="black",
            font=("Arial", 14, "bold"),
            tags="checkbox_drawn"
        )
   

def on_pdf_click(event):
    global editing_active

    if editing_active:
        return

    if not pages:
        return

    canvas_x = canvas_pdf.canvasx(event.x)
    canvas_y = canvas_pdf.canvasy(event.y)

    scaled_x = int(canvas_x / zoom_level)
    scaled_y = int(canvas_y / zoom_level)

    field = find_field(scaled_x, scaled_y, current_page)

    if not field:
        return

    global identify_mode, rename_mode

    print(
        "CLICKED:",
        field["name"],
        "rename_mode=",
        rename_mode
    )

    # ---------------------------
    # IDENTIFY MODE
    # ---------------------------

    if identify_mode:

        info = (
            f"Field Name: {field['name']}\n"
            f"Type: {field['type']}\n"
            f"Page: {field['page']}\n"
            f"Coordinates:\n"
            f"  x1={field['x1']}, y1={field['y1']}\n"
            f"  x2={field['x2']}, y2={field['y2']}"
        )

        messagebox.showinfo(
            "Field Info",
            info
        )

        print("FIELD JSON ENTRY:", field)

        return

    # ---------------------------
    # RENAME MODE
    # ---------------------------

    if rename_mode:

        new_name = simpledialog.askstring(
            "Rename Field",
            f"Enter new name for field '{field['name']}':",
            initialvalue=field["name"]
        )

        if new_name:

            field["name"] = new_name

            save_fields(fields)

            draw_all_field_boxes()
            redraw_all_text_fields()
            redraw_all_signatures()

            messagebox.showinfo(
                "Renamed",
                f"Field renamed to '{new_name}'"
            )

        return

    # ---------------------------
    # DIVE COUNTER
    # ---------------------------

    m = re.fullmatch(
        r"dive_(\d+)",
        field["name"].lower()
    )

    if m:

        dive_num = m.group(1)

        instructor = next(
            (
                i for i in instructor_list
                if i["name"] == instructor_var.get()
            ),
            None
        )

        current_value = state.get(
            field["name"],
            ""
        )

        if current_value == "":
            current_value = "1"
        elif current_value == "1":
            current_value = "2"
        elif current_value == "2":
            current_value = "3"
        elif current_value == "3":
            current_value = "4"
        else:
            current_value = ""

        state[field["name"]] = current_value

        if current_value == "":

            state[f"Dive_initials_{dive_num}"] = ""
            state[f"Dive_padi_{dive_num}"] = ""

        elif instructor:

            state[f"Dive_initials_{dive_num}"] = (
                instructor.get("initials", "")
            )

            state[f"Dive_padi_{dive_num}"] = (
                instructor.get("padi_number", "")
            )

        redraw_all_text_fields()
        save_state_with_locations()

        return

    # ---------------------------
    # CHECKBOX
    # ---------------------------

    if field["type"] == "checkbox":

        current_value = bool(
            state.get(field["name"], False)
        )

        state[field["name"]] = (
            not current_value
        )

        redraw_all_checkboxes()
        save_state_with_locations()

        return

    # ---------------------------
    # CW AUTO POPULATE
    # ---------------------------

    if field["name"].lower().endswith("_day"):

        name = field["name"].lower()

        m = re.search(
            r"(cw\d+)",
            name
        )

        if m:

            prefix = m.group(1).upper()

            populate_cw_row(prefix)

            return

    # ---------------------------
    # STUDENT SIGNATURE
    # ---------------------------

    if (
        field["name"]
        .strip()
        .lower()
        == "student_signature"
    ):

        existing_sig = state.get(
            field["name"]
        )

        if (
            existing_sig
            and Path(existing_sig).exists()
        ):

            answer = messagebox.askyesno(
                "Warning",
                "This student signature already exists.\n\n"
                "Replacing a signature may invalidate a previously "
                "signed training record.\n\n"
                "Do you want to continue?"
            )

            if not answer:
                return

        draw_student_signature_window(
            field["name"]
        )

        return

    # ---------------------------
    # INIT PADI INSTRUCTOR
    # ---------------------------

    m = re.fullmatch(
    r"init_padi_instructor_(\d+)",
    field["name"].strip().lower()
)

    if m:

        instructor_num = m.group(1)

        selected_name = instructor_var.get()

        if not selected_name:
            messagebox.showerror(
                "Error",
                "Select an instructor first."
            )
            return

        instructor = next(
            (i for i in instructor_list
            if i["name"] == selected_name),
            None
        )

        # Toggle OFF
        if state.get(field["name"]):

            state.pop(field["name"], None)

            state.pop(f"Init_PADI_no_{instructor_num}", None)
            state.pop(f"Init_Dive_Resort_No_{instructor_num}", None)
            state.pop(f"Init_Email_{instructor_num}", None)
            state.pop(f"Init_Phone_{instructor_num}", None)

            state.pop(
                f"Init_Instructor_Signature_{instructor_num}",
                None
            )

            state.pop(f"Init_day_{instructor_num}", None)
            state.pop(f"Init_month_{instructor_num}", None)
            state.pop(f"Init_year_{instructor_num}", None)

        # Toggle ON
        else:

            state[field["name"]] = selected_name

            if instructor:

                state[f"Init_PADI_no_{instructor_num}"] = \
                    instructor.get("padi_number", "")

                state[f"Init_Dive_Resort_No_{instructor_num}"] = \
                    instructor.get("store_number", "")

                state[f"Init_Email_{instructor_num}"] = \
                    instructor.get("email", "")

                state[f"Init_Phone_{instructor_num}"] = \
                    instructor.get("phone", "")

                sig_path = instructor.get("signature")

                if sig_path and Path(sig_path).exists():
                    state[
                        f"Init_Instructor_Signature_{instructor_num}"
                    ] = sig_path

            d = date_picker.get_date()

            state[f"Init_day_{instructor_num}"] = str(d.day)

            state[f"Init_month_{instructor_num}"] = [
                "Jan","Feb","Mar","Apr",
                "May","Jun","Jul","Aug",
                "Sep","Oct","Nov","Dec"
            ][d.month - 1]

            state[f"Init_year_{instructor_num}"] = str(d.year)

        redraw_all_text_fields()
        redraw_all_signatures()
        save_state_with_locations()

        return 

    # ---------------------------
    # INSTRUCTOR SIGNATURE
    # ---------------------------

    # ---------------------------
# INSTRUCTOR SIGNATURE
# ---------------------------

    m = re.fullmatch(
        r"instructor_signature_(\d+)",
        field["name"].strip().lower()
    )

    if m:

        selected_name = instructor_var.get()

        if not selected_name:
            messagebox.showerror(
                "Error",
                "Select an instructor first."
            )
            return

        instructor = next(
            (
                i for i in instructor_list
                if i["name"] == selected_name
            ),
            None
        )

        if not instructor:
            return

        signoff_num = m.group(1)

        # Toggle OFF
        if state.get(field["name"]):

            state.pop(field["name"], None)

            state.pop(f"PADI_no_{signoff_num}", None)
            state.pop(f"day_{signoff_num}", None)
            state.pop(f"month_{signoff_num}", None)
            state.pop(f"year_{signoff_num}", None)

        # Toggle ON
        else:

            sig_path = instructor.get("signature")

            if sig_path and Path(sig_path).exists():

                state[field["name"]] = sig_path

                state[f"PADI_no_{signoff_num}"] = (
                    instructor.get("padi_number", "")
                )

                d = date_picker.get_date()

                state[f"day_{signoff_num}"] = str(d.day)

                state[f"month_{signoff_num}"] = [
                    "Jan","Feb","Mar","Apr",
                    "May","Jun","Jul","Aug",
                    "Sep","Oct","Nov","Dec"
                ][d.month - 1]

                state[f"year_{signoff_num}"] = str(d.year)

        redraw_all_text_fields()
        redraw_all_signatures()
        save_state_with_locations()

        return

    # ---------------------------
    # NORMAL TEXT EDIT
    # ---------------------------

    start_inline_edit(field)


def on_pdf_right_click_normal(event):
    global editing_active
    if editing_active:
        return

    if not pages:
        return

    canvas_x = canvas_pdf.canvasx(event.x)
    canvas_y = canvas_pdf.canvasy(event.y)

    scaled_x = int(canvas_x / zoom_level)
    scaled_y = int(canvas_y / zoom_level)

    field = find_field(scaled_x, scaled_y, current_page)
    if not field:
        return

    if field["type"] in ("text", "day", "month", "year"):

        for child in canvas_pdf.place_slaves():
            child.destroy()

        entry_var = tk.StringVar(value=state.get(field["name"], ""))

        entry = tk.Entry(canvas_pdf, textvariable=entry_var, width=20)

        x = int(field["x1"] * zoom_level)
        y = int(field["y1"] * zoom_level)
        
        entry_window = canvas_pdf.create_window(
            x,
            y,
            anchor="nw",
            window=entry
        )

        
        
        def save_entry(event=None):
            state[field["name"]] = entry_var.get()
            save_state_with_locations()

            print("ENTRY EXISTS BEFORE =", entry.winfo_exists())
            entry.destroy()
            print("ENTRY EXISTS AFTER =", entry.winfo_exists())

            redraw_all_text_fields()
            
        entry.bind("<Return>", save_entry)
        entry.focus_set()




# ---------------- Hover Highlight ----------------

hover_field = None

def on_pdf_motion(event):
    global editing_active, zoom_level
    if editing_active:
        return

    canvas_x = canvas_pdf.canvasx(event.x)
    canvas_y = canvas_pdf.canvasy(event.y)

    scaled_x = int(canvas_x / zoom_level)
    scaled_y = int(canvas_y / zoom_level)

    global hover_field
    new_field = find_field(scaled_x, scaled_y, current_page)

    #
    # SHOW TOOLTIP FOR DIVE FIELDS
    #
    global tooltip_window

    if new_field and new_field["name"].startswith("Dive_"):

        if tooltip_window is None:

            tooltip_window = tk.Toplevel(root)
            tooltip_window.overrideredirect(True)

            label = tk.Label(
                tooltip_window,
                text=(
                    "Dive Counter\n"
                    "Click repeatedly:\n"
                    "Blank → 1 → 2 → 3 → 4 → Blank"
                ),
                bg="lightyellow",
                relief="solid",
                borderwidth=1,
                justify="left"
            )

            label.pack()

        tooltip_window.geometry(
            f"+{event.x_root + 15}+{event.y_root + 15}"
        )

    else:

        if tooltip_window:
            tooltip_window.destroy()
            tooltip_window = None

    if new_field is hover_field:
        return

    hover_field = new_field

    draw_all_field_boxes()

    #if new_field:
   #  print("HOVER:", repr(new_field["name"]))

def on_pdf_leave(event):

    global tooltip_window

    if tooltip_window:
        tooltip_window.destroy()
        tooltip_window = None


def draw_all_field_boxes():

    global editing_active
    global zoom_level
    global show_json_names

    if editing_active:
        return

    canvas_pdf.delete("field_box")

    for f in fields:

        if f.get("page", 0) != current_page:
            continue

        x1 = int(f["x1"] * zoom_level)
        y1 = int(f["y1"] * zoom_level)
        x2 = int(f["x2"] * zoom_level)
        y2 = int(f["y2"] * zoom_level)

        outline_color = "blue"
        width = 1

        if hover_field is f:
            outline_color = "red"
            width = 2

        canvas_pdf.create_rectangle(
            x1,
            y1,
            x2,
            y2,
            outline=outline_color,
            width=width,
            tags="field_box"
        )

        #
        # ONLY SHOW FIELD NAMES
        # WHEN THE TOGGLE IS ON
        #
        if show_json_names:

            canvas_pdf.create_text(
                x1 + 2,
                y1 + 2,
                anchor="nw",
                width=max(20, x2 - x1 - 4),
                text=f["name"],
                fill="blue",
                font=("Arial", 6),
                tags="field_box"
            )

# ---------------- Mask Editor ----------------

mask_edit_mode = False
drag_start = None
identify_mode = False
rename_mode = False


def bind_mask_edit_events():
    canvas_pdf.bind("<ButtonPress-3>", on_pdf_button_press)
    canvas_pdf.bind("<ButtonRelease-3>", on_pdf_button_release)

def unbind_mask_edit_events():
    canvas_pdf.unbind("<ButtonPress-3>")
    canvas_pdf.unbind("<ButtonRelease-3>")
    canvas_pdf.unbind("<Button-3>")




def toggle_mask_edit():
    global mask_edit_mode, identify_mode, rename_mode

    mask_edit_mode = not mask_edit_mode

    if mask_edit_mode:
        identify_mode = False
        rename_mode = False

        bind_mask_edit_events()

        status_label.config(
            text="Mask Edit Mode: ON (left drag=create field, right click=delete field)"
        )

    else:
        unbind_mask_edit_events()

        # Restore normal handlers
        canvas_pdf.bind("<Button-1>", on_pdf_click)
        canvas_pdf.bind("<Button-3>", on_pdf_right_click_normal)

        status_label.config(text="Mask Edit Mode: OFF")
    update_button_colors()


def toggle_rename_mode():
    global rename_mode, identify_mode, mask_edit_mode

    rename_mode = not rename_mode
    print("RENAME MODE =", rename_mode)
    
    if rename_mode:
        # Disable other modes
        identify_mode = False
        mask_edit_mode = False
        unbind_mask_edit_events()

        # Restore left-click handler for rename mode
        canvas_pdf.bind("<Button-1>", on_pdf_click)

        # Remove right-click text entry
        canvas_pdf.unbind("<Button-3>")

        status_label.config(text="Rename Mode: Click a field to rename it")

    else:
        # Restore normal right-click behavior
        canvas_pdf.bind("<Button-3>", on_pdf_right_click_normal, add="+")
        status_label.config(text="Rename Mode: OFF")

    update_button_colors()



def on_pdf_button_press(event):
    global drag_start

    global editing_active
    if editing_active:
        return

    if not mask_edit_mode or not pages:
        return


    canvas_x = canvas_pdf.canvasx(event.x)
    canvas_y = canvas_pdf.canvasy(event.y)

    drag_start = (canvas_x, canvas_y)

def on_pdf_button_release(event):
    global editing_active
    if editing_active:
        return

    if not mask_edit_mode or not pages or drag_start is None:
        return


    canvas_x = canvas_pdf.canvasx(event.x)
    canvas_y = canvas_pdf.canvasy(event.y)

    x1_canvas, y1_canvas = drag_start
    x2_canvas, y2_canvas = canvas_x, canvas_y

    if abs(x2_canvas - x1_canvas) < 5 or abs(y2_canvas - y1_canvas) < 5:
        drag_start = None
        return

    x1 = int(min(x1_canvas, x2_canvas) / zoom_level)
    y1 = int(min(y1_canvas, y2_canvas) / zoom_level)
    x2 = int(max(x1_canvas, x2_canvas) / zoom_level)
    y2 = int(max(y1_canvas, y2_canvas) / zoom_level)

    new_field = {
        "name": f"field_{len(fields)+1}",
        "type": "signature",
        "page": current_page,
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2
    }

    fields.append(new_field)
    messagebox.showinfo("Field Created", "Field added. Click 'Save Mask File' to write changes.")

    #save_fields(fields)  
    draw_all_field_boxes()

    messagebox.showinfo(
        "Field Created",
        f"New signature field created:\n{new_field['name']}\nPage {current_page}"
    )

    drag_start = None

def load_mask_file():
    global fields

    # Ask user to choose a mask JSON file
    mask_path = filedialog.askopenfilename(
        title="Select Mask File",
        filetypes=[("JSON Files", "*.json"), ("All Files", "*.*")]
    )

    if not mask_path:
        return  # user cancelled

    try:
        with open(mask_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        # Expecting {"fields": [...]}
        fields = data.get("fields", [])

        # Warn if mask dimensions do not match PDF
        if pages:
            img_w, img_h = pages[0].size

            for f in fields:
                if (f["x1"] > img_w or f["y1"] > img_h or
                    f["x2"] > img_w or f["y2"] > img_h):
                    messagebox.showwarning(
                        "Mask Warning",
                        "Mask field coordinates do not match this PDF.\n"
                        "Fields may appear in incorrect locations."
                    )
                    break


        draw_all_field_boxes()
        redraw_all_signatures()

        messagebox.showinfo("Mask Loaded", f"Loaded mask file:\n{mask_path}")

    except Exception as e:
        messagebox.showerror("Error", f"Failed to load mask file:\n{e}")

import shutil

def regenerate_master_mask():
    """Explicitly regenerate the protected master mask from hardcoded data."""
    if not messagebox.askyesno(
        "Regenerate Master Mask",
        "This will replace 10056_OW_Records_mask.json with the embedded master mask.\n\n"
        "Any manual changes made to that JSON file will be lost.\n\n"
        "Continue?"
    ):
        return

    if generate_master_mask_file(force=True):
        messagebox.showinfo(
            "Master Mask",
            f"Master mask regenerated from the embedded definition:\n{FIELDS_FILE}"
        )


def save_mask_file():

    if not pdf_path:
        messagebox.showerror(
            "Error",
            "Load a PDF first."
        )
        return

    pdf_name = Path(pdf_path).stem
    default_name = f"{pdf_name}_mask.json"

    save_path = filedialog.asksaveasfilename(
        title="Save Mask File",
        initialdir=str(BASE_DIR),
        initialfile=default_name,
        defaultextension=".json",
        filetypes=[
            ("JSON Files", "*.json"),
            ("All Files", "*.*")
        ]
    )

    if not save_path:
        return

    try:

        #
        # PROTECT MASTER MASK
        #
        if Path(save_path).resolve() == FIELDS_FILE.resolve():

            messagebox.showwarning(
                "Protected File",
                "10056_OW_Records_mask.json is the protected master mask.\n\n"
                "Choose a different filename."
            )

            return

        #
        # AUTO BACKUP EXISTING FILE
        #
        save_file = Path(save_path)

        if save_file.exists():

            backup_file = save_file.with_suffix(".bak.json")

            shutil.copy2(
                save_file,
                backup_file
            )

            print(
                "BACKUP CREATED:",
                backup_file
            )

        #
        # SAVE MASK
        #
        with open(
            save_path,
            "w",
            encoding="utf-8"
        ) as f:

            json.dump(
                {"fields": fields},
                f,
                indent=4
            )

        messagebox.showinfo(
            "Saved",
            f"Mask file saved:\n{save_path}"
        )

    except Exception as e:

        messagebox.showerror(
            "Error",
            f"Failed to save mask file:\n{e}"
        )

def redraw_all_signatures():
    canvas_pdf.delete("signature_drawn")
    canvas_pdf.signature_images = []   # ⭐ REQUIRED FIX

    for f in fields:
        if f.get("page", 0) != current_page:
            continue
        if f["type"] != "signature":
            continue

        sig_path = state.get(f["name"])
        if not isinstance(sig_path, str):
            continue

        if not Path(sig_path).exists():
            continue


        img = Image.open(sig_path)
        w = int((f["x2"] - f["x1"]) * zoom_level)
        h = int((f["y2"] - f["y1"]) * zoom_level)
        img = img.resize((w, h), Image.LANCZOS)

        tk_img = ImageTk.PhotoImage(img)
        canvas_pdf.signature_images.append(tk_img)

        x = int(f["x1"] * zoom_level)
        y = int(f["y1"] * zoom_level)

        canvas_pdf.create_image(x, y, anchor="nw", image=tk_img, tags="signature_drawn")


# ---------------- Date Control Handler ----------------

def on_date_changed(event):
    """Fires automatically when a date context gets updated inside the dropdown calendar."""
    current_date = date_picker.get_date()
    state["global_selected_date"] = current_date.strftime("%Y-%m-%d")


def on_date_changed(event):
    current_date = date_picker.get_date()

    print("DATE PICKER =", current_date)

    state["global_selected_date"] = current_date.strftime("%Y-%m-%d")

# ---------------- Dynamic Widgets ----------------

def show_field_widget(field):
    for child in widget_frame.winfo_children():
        child.destroy()

    ftype = field["type"]
    name = field["name"]

    selected_name = instructor_var.get()
    instructor = next((i for i in instructor_list if i["name"] == selected_name), None)

    # Automatically sync granular date items using the top menu selection fallback context
    if ftype == "day":
        default_day = str(date_picker.get_date().day)
        values = [str(i) for i in range(1, 32)]
        var = tk.StringVar(value=state.get(name, default_day))
        cb = ttk.Combobox(widget_frame, values=values, textvariable=var, width=4)
        cb.pack(side="left")
        set_field_value(name, var.get())
        cb.bind("<<ComboboxSelected>>", lambda e: set_field_value(name, var.get()))

    elif ftype == "month":
        months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"]
        default_month = months[date_picker.get_date().month - 1]
        var = tk.StringVar(value=state.get(name, default_month))
        cb = ttk.Combobox(widget_frame, values=months, textvariable=var, width=6)
        cb.pack(side="left")
        set_field_value(name, var.get())
        cb.bind("<<ComboboxSelected>>", lambda e: set_field_value(name, var.get()))

    elif ftype == "year":
        default_year = str(date_picker.get_date().year)
        values = [str(y) for y in range(2020, 2035)]
        var = tk.StringVar(value=state.get(name, default_year))
        cb = ttk.Combobox(widget_frame, values=values, textvariable=var, width=6)
        cb.pack(side="left")
        set_field_value(name, var.get())
        cb.bind("<<ComboboxSelected>>", lambda e: set_field_value(name, var.get()))

    elif ftype == "text":
        var = tk.StringVar(value=state.get(name, ""))
        entry = tk.Entry(widget_frame, textvariable=var, width=40)
        entry.pack(side="left")
        entry.bind("<Return>", lambda e: set_field_value(name, var.get()))

    elif ftype == "checkbox":
        var = tk.BooleanVar(value=bool(state.get(name, False)))
        cb = tk.Checkbutton(widget_frame, text=name, variable=var,
                            command=lambda: set_field_value(name, var.get()))
        cb.pack(side="left")

    elif ftype == "signature":
        if not instructor:
            messagebox.showerror("Error", "Select an instructor first.")
            return

        sig_path = instructor.get("signature")
        if not sig_path or not Path(sig_path).exists():
            messagebox.showerror("Error", "Instructor has no saved signature or file missing.")
            return

        set_field_value(name, sig_path)
        place_signature_on_canvas(field, sig_path)

def set_field_value(name, value):
    state[name] = value

# ---------------- PDF Export ----------------
from pypdf.generic import NameObject, BooleanObject, NumberObject

def _fit_font_size(text, box_width, box_height, start_size=9.0, min_size=4.5):
    if not text:
        return start_size

    size = start_size
    estimated_width = max(1.0, len(text) * 0.52)

    if estimated_width * size > box_width:
        size = box_width / estimated_width

    return max(min_size, min(start_size, size))


def _draw_static_form_values(page_canvas, page_index, pdf_values):
    """
    Draw form values directly into the PDF page.

    This is necessary because some PDF viewers/renderers do not display
    AcroForm appearance streams generated by pypdf.  The AcroForm values are
    still retained for later retrieval by the application.
    """
    for pdf_name, value in pdf_values.items():
        rect_info = pdf_field_rects.get(pdf_name)
        if not rect_info:
            continue

        field_page, x1_img, y1_img, x2_img, y2_img = rect_info
        if field_page != page_index:
            continue

        field_type = "text"

        for app_name, mapped_name in pdf_field_mapping.items():
            if mapped_name == pdf_name:
                info = next(
                    (f for f in fields if f["name"] == app_name),
                    None
                )
                if info:
                    field_type = info.get("type", "text")
                break

        scale = 200.0 / 72.0
        page_w, page_h = page_canvas._pagesize

        x1 = float(x1_img) / scale
        x2 = float(x2_img) / scale
        y_bottom = page_h - (float(y2_img) / scale)
        y_top = page_h - (float(y1_img) / scale)

        width = max(1.0, x2 - x1)
        height = max(1.0, y_top - y_bottom)

        if field_type == "signature":
            continue

        if field_type == "checkbox":
            if str(value) in ("/Yes", "Yes", "True", "true", "1"):
                page_canvas.setLineWidth(
                    max(0.8, min(1.5, height * 0.12))
                )
                page_canvas.line(
                    x1 + width * 0.18,
                    y_bottom + height * 0.48,
                    x1 + width * 0.42,
                    y_bottom + height * 0.20
                )
                page_canvas.line(
                    x1 + width * 0.42,
                    y_bottom + height * 0.20,
                    x1 + width * 0.82,
                    y_bottom + height * 0.80
                )
            continue

        text = str(value)
        if not text:
            continue

        font_size = _fit_font_size(
            text,
            width - 2,
            height - 1,
            start_size=min(9.0, max(6.0, height * 0.70))
        )

        page_canvas.setFont("Helvetica", font_size)
        page_canvas.setFillColorRGB(0, 0, 0)

        baseline = y_bottom + max(
            1.0,
            (height - font_size) / 2.0
        )

        page_canvas.drawString(
            x1 + 1,
            baseline,
            text
        )


def overlay_pdf_with_state(
    input_pdf,
    output_pdf,
    fields,
    state
):
    for f in fields:

        if f["type"] == "signature":

            print(
                "SIGNATURE FIELD:",
                f["name"],
                "=",
                state.get(f["name"])
            )

    reader = PdfReader(input_pdf)

    writer = PdfWriter()
    writer.clone_document_from_reader(reader)

    if "/AcroForm" in writer._root_object:
        acro = writer._root_object["/AcroForm"]
        acro.update({
            NameObject("/NeedAppearances"):
            BooleanObject(False)
        })

    print("\n==============================")
    print("SIGNATURES BEFORE EXPORT")
    print("==============================")

    for f in fields:

        if f["type"] == "signature":

            print(
                f["name"],
                "=",
                repr(state.get(f["name"]))
            )

    print("==============================\n")
    
    pdf_values = {}

    for f in fields:

        value = state.get(f["name"])

        if value in (None, ""):
            continue

        #
        # Signature PNGs are handled later
        #
        if f["type"] == "signature":
            continue

        pdf_name = pdf_field_mapping.get(f["name"])

        if pdf_name:
            if f["type"] == "checkbox":

                if value:
                    pdf_values[pdf_name] = "/Yes"
                else:
                    pdf_values[pdf_name] = "/Off"

            else:

                pdf_values[pdf_name] = str(value)

    print("PDF VALUES =", pdf_values)
    print("\n===== EXPORT VALUES =====")

    for k, v in pdf_values.items():
        print(k, "=", repr(v))

    print("=========================\n")
    # IMPORTANT: update every page explicitly.  Passing None here does not
    # reliably write the AcroForm values in current pypdf versions.
    # This was the reason exported PDFs could contain the signature image
    # while losing the other entered form information.
    for page in writer.pages:
        writer.update_page_form_field_values(
            page,
            pdf_values,
            auto_regenerate=True
        )

    #
    # STAMP SIGNATURE IMAGES
    #
    for page_num, page in enumerate(writer.pages):

        packet = io.BytesIO()

        pdf_page = reader.pages[page_num]

        page_w = float(pdf_page.mediabox.width)
        page_h = float(pdf_page.mediabox.height)

        c = canvas.Canvas(
            packet,
            pagesize=(page_w, page_h)
        )

        _draw_static_form_values(
            c,
            page_num,
            pdf_values
        )

        for f in fields:

            if f.get("page", 0) != page_num:
                continue

            if f["type"] != "signature":
                continue

            sig_path = state.get(f["name"])

            if not sig_path:
                continue

            if not Path(sig_path).exists():
                continue

            print(
                "STAMPING:",
                f["name"],
                "=",
                sig_path
            )

            img_w, img_h = pages[page_num].size

            scale_x = page_w / img_w
            scale_y = page_h / img_h

            x = f["x1"] * scale_x

            y = page_h - (
                f["y2"] * scale_y
            )

            width = (
                f["x2"] - f["x1"]
            ) * scale_x

            height = (
                f["y2"] - f["y1"]
            ) * scale_y

            c.drawImage(
                ImageReader(sig_path),
                x,
                y,
                width=width,
                height=height,
                mask="auto"
            )

        c.save()

        packet.seek(0)

        overlay_reader = PdfReader(packet)

        page.merge_page(
            overlay_reader.pages[0]
        )

        # Keep /V values in the AcroForm for application retrieval, but hide
        # the widgets so they cannot draw a second copy over the static text.
        annots_ref = page.get("/Annots")
        if annots_ref:
            try:
                annots = annots_ref.get_object()
            except Exception:
                annots = annots_ref

            for annot_ref in annots:
                try:
                    annot = annot_ref.get_object()
                except Exception:
                    annot = annot_ref

                if annot.get("/Subtype") == "/Widget":
                    annot[NameObject("/F")] = NumberObject(2)

    with open(output_pdf, "wb") as fp:
        writer.write(fp)

    print("INPUT PDF =", input_pdf)
    print("INPUT PDF =", input_pdf)


#def save_progress():
 #   save_state_with_locations()
  #  messagebox.showinfo("Saved", "Progress saved.")

def export_pdf():
    """Export the current PDF while preserving all AcroForm values and signatures."""

    if not pdf_path:
        messagebox.showerror("Error", "No PDF loaded.")
        return

    student_name = state.get("Student Name", "").strip()

    if student_name:
        safe_name = student_name.replace("/", "_").replace("\\", "_")
        default_filename = f"{safe_name}_PADI_Record.pdf"
    else:
        default_filename = "PADI_Record.pdf"

    output = filedialog.asksaveasfilename(
        title="Export PDF",
        initialfile=default_filename,
        defaultextension=".pdf",
        filetypes=[("PDF files", "*.pdf")]
    )

    if not output:
        return

    try:
        # Rebuild against the PDF currently being exported so mappings cannot
        # become stale after opening more than one PDF in a session.
        build_pdf_field_mapping()

        overlay_pdf_with_state(
            pdf_path,
            output,
            fields,
            state
        )

        # Save the comment against the exported PDF as well as the source PDF.
        # Comments are kept in comments.json and never added to the mask file.
        save_current_comment(output)

        messagebox.showinfo(
            "Exported",
            f"PDF exported:\n{output}"
        )

    except Exception as e:
        messagebox.showerror(
            "Error",
            str(e)
        )


# ---------------- Add New Instructor ----------------

def add_instructor_window():
    global instructor_window
    instructor_window = tk.Toplevel(root)
    win = instructor_window
    win.title("Instructor Manager")
    win.geometry("400x650")

    # Force window to front
    win.lift()
    win.focus_force()

    # ---------------- Existing Instructor ----------------

    tk.Label(win, text="Existing Instructor").pack(pady=5)

    existing_var = tk.StringVar()

    existing_combo = ttk.Combobox(
        win,
        textvariable=existing_var,
        values=[i["name"] for i in instructor_list],
        width=30
    )
    existing_combo.pack(pady=5)

    # ---------------- Instructor Details ----------------

    tk.Label(win, text="Name:").pack(pady=5)
    name_var = tk.StringVar()
    tk.Entry(win, textvariable=name_var).pack()

    tk.Label(win, text="Email:").pack(pady=5)
    email_var = tk.StringVar()
    tk.Entry(win, textvariable=email_var).pack()

    tk.Label(win, text="Phone Number:").pack(pady=5)
    phone_var = tk.StringVar()
    tk.Entry(win, textvariable=phone_var).pack()

    tk.Label(win, text="PADI Number:").pack(pady=5)
    padi_var = tk.StringVar()
    tk.Entry(win, textvariable=padi_var).pack()

    tk.Label(win, text="PADI Store Number:").pack(pady=5)
    store_var = tk.StringVar(value="4491")
    tk.Entry(win, textvariable=store_var).pack()

    tk.Label(win, text="Initials:").pack(pady=5)
    initials_var = tk.StringVar()
    tk.Entry(win, textvariable=initials_var).pack()

    tk.Label(win, text="Signature (draw inside app):").pack(pady=5)
    signature_var = tk.StringVar()

    
    

    def open_signature_draw():

        name = name_var.get()
        padi = padi_var.get()

        if not name:
            messagebox.showerror(
                "Error",
                "Enter name first."
            )
            return

        if not padi:
            messagebox.showerror(
                "Error",
                "Enter PADI number first."
            )
            return

        draw_signature_window(
            name,
            padi,
            signature_var
        )

    tk.Button(win, text="Draw Signature", command=open_signature_draw).pack(pady=10)

    def delete_instructor():
        name = name_var.get()

        if not name:
            messagebox.showerror("Error", "Enter or select an instructor name.")
            return

        instructor = next(
            (i for i in instructor_list if i["name"] == name),
            None
        )

        if not instructor:
            messagebox.showerror("Error", f"Instructor '{name}' not found.")
            return

        if not messagebox.askyesno(
            "Delete Instructor",
            f"Delete instructor '{name}'?"
        ):
            return

        instructor_list.remove(instructor)
        save_instructors({"instructors": instructor_list})

        instructor_dropdown["values"] = [
            i["name"] for i in instructor_list
        ]

        instructor_var.set("")

        messagebox.showinfo(
            "Deleted",
            f"Instructor '{name}' removed."
        )

        win.destroy()

    def load_selected(event=None):
        
        name = existing_var.get()

        instructor = next(
            (i for i in instructor_list if i["name"] == name),
            None
        )

        if not instructor:
            return

        name_var.set(instructor.get("name", ""))
        email_var.set(instructor.get("email", ""))
        phone_var.set(instructor.get("phone", ""))
        padi_var.set(instructor.get("padi_number", ""))
        store_var.set(instructor.get("store_number", "4491"))
        initials_var.set(instructor.get("initials", ""))
        signature_var.set(instructor.get("signature", ""))
        
    existing_combo.bind("<<ComboboxSelected>>", load_selected)

    def save_new():
        name = name_var.get()
        email = email_var.get()
        phone = phone_var.get()
        padi = padi_var.get()
        store = store_var.get()
        initials = initials_var.get()
        signature = signature_var.get()
        print("DEBUG signature_var =", signature)

        if not signature or not Path(signature).exists():
            messagebox.showerror("Error", "Signature must be drawn and saved.")
            return

        if not name or not email or not phone or not padi or not store or not initials:
            messagebox.showerror("Error", "All fields are required.")
            return

        new_inst = {
            "name": name,
            "email": email,
            "phone": phone,
            "padi_number": padi,
            "store_number": store,
            "initials": initials,
            "signature": signature
        }

        instructor_list.append(new_inst)
        save_instructors({"instructors": instructor_list})

        instructor_dropdown["values"] = [i["name"] for i in instructor_list]
        instructor_var.set(name)
        update_instructor_info()


        messagebox.showinfo("Saved", "Instructor added successfully.")
        
        win.destroy()

    btn_frame = tk.Frame(win)
    
    btn_frame = tk.Frame(win)
    btn_frame.pack(pady=10)


    tk.Button(
        btn_frame,
        text="Save Instructor",
        command=save_new
    ).pack(side="left", padx=10)

    tk.Button(
        btn_frame,
        text="Delete Instructor",
        command=delete_instructor,
        bg="tomato"
    ).pack(side="left", padx=10)


# ---------------- Instructor Info Display ----------------

def update_instructor_info(*args):
    name = instructor_var.get()
    instructor = next((i for i in instructor_list if i["name"] == name), None)

    if not instructor:
        instructor_info.config(text="No instructor selected")
        return

    sig_path = instructor.get("signature")
    if sig_path and Path(sig_path).exists():
        sig_status = "✔ Signature saved"
    elif sig_path:
        sig_status = "✘ Signature path set but file missing"
    else:
        sig_status = "✘ No signature path set"

    info_text = (
        f"Name: {instructor['name']}   "
        f"Email: {instructor['email']}   "
        f"Phone: {instructor['phone']}\n"
        f"PADI#: {instructor['padi_number']}   "
        f"Store#: {instructor.get('store_number', '4491')}   "
        f"Initials: {instructor.get('initials', 'N/A')}   "
        f"{sig_status}"
    )


    instructor_info.config(text=info_text)

def toggle_identify_mode():
    global identify_mode, mask_edit_mode
    identify_mode = not identify_mode
    canvas_pdf.unbind("<Button-3>")


    if identify_mode:
        mask_edit_mode = False

        # Unbind ALL right-click handlers from mask edit mode
        canvas_pdf.unbind("<ButtonPress-3>")
        canvas_pdf.unbind("<ButtonRelease-3>")
        canvas_pdf.unbind("<Button-3>")   # ← REQUIRED

        # Bind identify-mode delete handler


        status_label.config(text="Identify Mode: Left-click to inspect, Right-click to delete")
        update_button_colors()

    else:
        canvas_pdf.bind("<Button-3>", on_pdf_right_click_normal, add="+")

        status_label.config(text="Identify Mode: OFF")
        update_button_colors()




def auto_detect_fields():
    global fields

    if not pdf_path or not pages:
        messagebox.showerror("Error", "Load a PDF first.")
        return

    # Run AcroForm detection
    auto_fields = detect_acroform_fields(pdf_path, pages)

    # Run heuristic detection
    heuristic_fields = []
    for idx, img in enumerate(pages):
        heuristic_fields.extend(heuristic_signature_boxes(img, idx))

    # Merge results
    new_fields = auto_fields + heuristic_fields

    if not new_fields:
        messagebox.showinfo("Auto-Detect Fields", "No fields detected.")
        return

    # Filter out duplicates by name
    existing_names = {f["name"] for f in fields}
    unique_new_fields = [f for f in new_fields if f["name"] not in existing_names]

    if not unique_new_fields:
        messagebox.showinfo("Auto-Detect Fields", "All detected fields already exist.")
        return

    # Append only unique fields
    fields.extend(unique_new_fields)

    draw_all_field_boxes()
    redraw_all_signatures()

    messagebox.showinfo(
        "Auto-Detect Fields",
        f"Added {len(unique_new_fields)} new fields.\n\n"
        "Changes are currently in memory only.\n"
        "Use 'Save Mask File' to write them to a JSON file."
    )

    messagebox.showinfo("Auto-Detect Fields", f"Added {len(unique_new_fields)} new fields.")

def on_pdf_right_click(event):
    if not pages:
        return

    global identify_mode
    if not identify_mode:
        return  # only delete in identify mode

    canvas_x = canvas_pdf.canvasx(event.x)
    canvas_y = canvas_pdf.canvasy(event.y)

    scaled_x = int(canvas_x / zoom_level)
    scaled_y = int(canvas_y / zoom_level)

    field = find_field(scaled_x, scaled_y, current_page)
    if not field:
        return

    print("CLICKED FIELD =", repr(field["name"]))

    if messagebox.askyesno("Delete Field", f"Delete field '{field['name']}'?"):
        fields.remove(field)
        #save_fields(fields)

        # ⭐ REQUIRED FIX — clear hover state
        global hover_field
        hover_field = None

        draw_all_field_boxes()
        redraw_all_signatures()

        messagebox.showinfo("Field Deleted", f"Field '{field['name']}' removed and mask saved.")

 
def update_button_colors():

    if mask_edit_mode:
        btn_mask_edit.config(bg="orange")
    else:
        btn_mask_edit.config(bg=root.cget("bg"))

    if identify_mode:
        btn_identify.config(bg="lightgreen")
    else:
        btn_identify.config(bg=root.cget("bg"))

    if rename_mode:
        btn_rename.config(bg="lightgreen")
    else:
        btn_rename.config(bg=root.cget("bg"))

    if show_json_names:
        btn_json_names.config(bg="lightgreen")
    else:
        btn_json_names.config(bg=root.cget("bg"))


# ---------------- GUI SETUP ----------------

root = tk.Tk()
root.title("PADI Manager (Interactive PDF)")
root.geometry("1200x800")

hover_info_label = tk.Label(
    root,
    text="",
    bg="lightyellow",
    relief="solid",
    borderwidth=1,
    justify="left"
)

top_frame = ttk.Frame(root)
top_frame.pack(fill="x", pady=5)

tk.Label(top_frame, text="Instructor:").pack(side="left", padx=5)
instructor_var = tk.StringVar()
instructor_dropdown = ttk.Combobox(
    top_frame,
    textvariable=instructor_var,
    values=[i["name"] for i in instructor_list],
    width=25
)
instructor_dropdown.pack(side="left")

tk.Button(top_frame, text="Add/Manage Instructor", command=add_instructor_window).pack(side="left", padx=10)
#tk.Button(top_frame, text="Save Mask File", command=save_mask_file).pack(side="left", padx=5)


# --- Integrated Date Picker Widget ---
tk.Label(top_frame, text="Select Date:").pack(side="left", padx=(15, 2))


date_picker = DateEntry(
    top_frame,
    width=12,
    background='darkblue',
    foreground='white',
    borderwidth=2,
    date_pattern='yyyy-mm-dd'
)

date_picker.configure(state="readonly")
date_picker.set_date(date.today())

date_picker.pack(side="left", padx=5)
date_picker.bind("<<DateEntrySelected>>", on_date_changed)

instructor_info = tk.Label(top_frame, text="No instructor selected", anchor="w", justify="left")
instructor_info.pack(side="left", padx=20)

instructor_var.trace_add("write", update_instructor_info)


mid_frame = ttk.Frame(root)
mid_frame.pack(fill="x", pady=5)

tk.Button(mid_frame, text="Load PDF", command=load_pdf).pack(side="left", padx=5)
pdf_label = tk.Label(mid_frame, text="No PDF loaded")
pdf_label.pack(side="left", padx=10)

tk.Button(mid_frame, text="Prev Page", command=prev_page).pack(side="left", padx=5)
tk.Button(mid_frame, text="Next Page", command=next_page).pack(side="left", padx=5)

tk.Button(mid_frame, text="Zoom +", command=zoom_in).pack(side="left", padx=5)
tk.Button(mid_frame, text="Zoom -", command=zoom_out).pack(side="left", padx=5)
tk.Button(mid_frame, text="Fit Page", command=zoom_fit).pack(side="left", padx=5)

#tk.Button(mid_frame, text="Save Progress", command=save_progress).pack(side="left", padx=10)
tk.Button(
    mid_frame,
    text="Save/Update PDF",
    command=export_pdf
).pack(side="left", padx=5)

# ------------------------------------------------------------
# Main-menu comment box
# ------------------------------------------------------------
# No separate Comment button/window.  The textbox is always visible
# beside Save/Update PDF and reads/writes comments.json.
comment_frame = tk.Frame(mid_frame)
comment_frame.pack(
    side="left",
    padx=(6, 10),
    pady=0,
    fill="y"
)

comment_text = tk.Text(
    comment_frame,
    width=34,
    height=2,
    wrap="word",
    undo=True,
    font=("Arial", 9)
)

comment_scrollbar = tk.Scrollbar(
    comment_frame,
    orient="vertical",
    command=comment_text.yview
)

comment_text.configure(
    yscrollcommand=comment_scrollbar.set
)

comment_text.pack(
    side="left",
    fill="both",
    expand=True
)

comment_scrollbar.pack(
    side="right",
    fill="y"
)

#tk.Button(mid_frame, text="Save Mask File", command=save_mask_file).pack(side="left", padx=5)
#tk.Button(mid_frame, text="Load Mask File", command=load_mask_file).pack(side="left", padx=5)
#tk.Button(mid_frame, text="Close PDF", command=close_pdf).pack(side="left", padx=5)


status_label = tk.Label(root, text="Mask Edit Mode: OFF")
status_label.pack(pady=5)

#
# Main area = PDF viewer + right tools panel
#
main_view_frame = tk.Frame(root)
main_view_frame.pack(fill="both", expand=True)

#
# PDF Viewer Area
#
pdf_frame = tk.Frame(main_view_frame)
pdf_frame.pack(side="left", fill="both", expand=True)

#
# Right Tools Panel
#
tools_frame = tk.Frame(
    main_view_frame,
    width=110,
    relief="groove",
    bd=2
)

tools_frame.pack(
    side="right",
    fill="y",
    padx=5,
    pady=5
)
weite=10
tools_frame.pack_propagate(False)

btn_mask_edit = tk.Button(
    tools_frame,
    text="Toggle Mask Edit",
    command=toggle_mask_edit,
    width=weite
)

btn_identify = tk.Button(
    tools_frame,
    text="Identify Field",
    command=toggle_identify_mode,
    width=weite
)

btn_rename = tk.Button(
    tools_frame,
    text="Rename Field",
    command=toggle_rename_mode,
    width=weite
)

btn_json_names = tk.Button(
    tools_frame,
    text="Show JSON Names",
    command=toggle_json_names,
    width=weite
)

btn_save_mask = tk.Button(
    tools_frame,
    text="Save Mask File",
    command=save_mask_file,
    width=weite
)

btn_load_mask = tk.Button(
    tools_frame,
    text="Load Mask File",
    command=load_mask_file,
    width=weite
)

btn_close_pdf = tk.Button(
    tools_frame,
    text="Close PDF",
    command=close_pdf,
    width=weite
)

btn_regenerate_master = tk.Button(
    tools_frame,
    text="Regenerate Master Mask",
    command=regenerate_master_mask,
    width=weite
)
#
# Right-side tool buttons
#
btn_mask_edit.pack(
    fill="x",
    pady=2
)

btn_identify.pack(
    fill="x",
    pady=2
)

btn_rename.pack(
    fill="x",
    pady=2
)

tk.Button(
    tools_frame,
    text="Auto-Detect Fields",
    command=auto_detect_fields
).pack(
    fill="x",
    pady=2
)

btn_json_names.pack(
    fill="x",
    pady=2
)

btn_save_mask.pack(
    fill="x",
    pady=2
)

btn_load_mask.pack(
    fill="x",
    pady=2
)

btn_regenerate_master.pack(
    fill="x",
    pady=2
)

btn_close_pdf.pack(
    fill="x",
    pady=2
)

tk.Button(
    tools_frame,
    text="Field Logic 10056",
    command=show_program_fields
).pack(
    fill="x",
    pady=2
)

update_button_colors()
update_button_colors()

v_scroll = tk.Scrollbar(pdf_frame, orient="vertical")
h_scroll = tk.Scrollbar(pdf_frame, orient="horizontal")

canvas_pdf = tk.Canvas(
    pdf_frame,
    bg="grey",
    width=900,
    height=600,
    scrollregion=(0, 0, 2000, 2000),
    yscrollcommand=v_scroll.set,
    xscrollcommand=h_scroll.set
)
canvas_pdf.bind("<Button-3>", on_pdf_right_click_normal, add="+")

canvas_pdf.focus_set()

v_scroll.config(command=canvas_pdf.yview)
h_scroll.config(command=canvas_pdf.xview)

v_scroll.pack(side="right", fill="y")
h_scroll.pack(side="bottom", fill="x")
canvas_pdf.pack(side="left", fill="both", expand=True)

def _on_mousewheel(event):
    canvas_pdf.yview_scroll(int(-1*(event.delta/120)), "units")

canvas_pdf.bind("<Button-1>", on_pdf_click)
canvas_pdf.bind("<Motion>", on_pdf_motion)
canvas_pdf.bind("<Leave>", on_pdf_leave)



def bind_mask_edit_events():
    # LEFT CLICK = create field
    canvas_pdf.bind("<ButtonPress-1>", on_mask_left_press)
    canvas_pdf.bind("<ButtonRelease-1>", on_mask_left_release)

    # RIGHT CLICK = delete field
    canvas_pdf.bind("<Button-3>", on_mask_right_click)


def unbind_mask_edit_events():
    canvas_pdf.unbind("<ButtonPress-1>")
    canvas_pdf.unbind("<ButtonRelease-1>")
    canvas_pdf.unbind("<Button-3>")

    canvas_pdf.bind("<Button-1>", on_pdf_click)
    canvas_pdf.bind("<Button-3>", on_pdf_right_click_normal)

# ---------------- Mask Edit: LEFT CLICK = Create Field ----------------

def on_mask_left_press(event):
    global drag_start
    if not mask_edit_mode or not pages:
        return

    canvas_x = canvas_pdf.canvasx(event.x)
    canvas_y = canvas_pdf.canvasy(event.y)
    drag_start = (canvas_x, canvas_y)


def on_mask_left_release(event):
    global drag_start
    if not mask_edit_mode or not pages or drag_start is None:
        return

    canvas_x = canvas_pdf.canvasx(event.x)
    canvas_y = canvas_pdf.canvasy(event.y)

    x1_canvas, y1_canvas = drag_start
    x2_canvas, y2_canvas = canvas_x, canvas_y

    # Ignore tiny drags
    if abs(x2_canvas - x1_canvas) < 5 or abs(y2_canvas - y1_canvas) < 5:
        drag_start = None
        return

    x1 = int(min(x1_canvas, x2_canvas) / zoom_level)
    y1 = int(min(y1_canvas, y2_canvas) / zoom_level)
    x2 = int(max(x1_canvas, x2_canvas) / zoom_level)
    y2 = int(max(y1_canvas, y2_canvas) / zoom_level)

    new_field = {
        "name": f"field_{len(fields)+1}",
        "type": "text",
        "page": current_page,
        "x1": x1,
        "y1": y1,
        "x2": x2,
        "y2": y2
    }

    fields.append(new_field)
    draw_all_field_boxes()
    messagebox.showinfo("Field Created", f"New field created:\n{new_field['name']}")

    drag_start = None


# ---------------- Mask Edit: RIGHT CLICK = Delete Field ----------------

def on_mask_right_click(event):
    if not mask_edit_mode or not pages:
        return

    canvas_x = canvas_pdf.canvasx(event.x)
    canvas_y = canvas_pdf.canvasy(event.y)

    scaled_x = int(canvas_x / zoom_level)
    scaled_y = int(canvas_y / zoom_level)

    field = find_field(scaled_x, scaled_y, current_page)
    if not field:
        return

    if messagebox.askyesno("Delete Field", f"Delete field '{field['name']}'?"):
        fields.remove(field)
        draw_all_field_boxes()
        redraw_all_signatures()



canvas_pdf.bind("<ButtonPress-2>", on_pdf_button_press)
canvas_pdf.bind("<ButtonRelease-2>", on_pdf_button_release)

canvas_pdf.bind("<B3-Motion>", lambda e: None)
canvas_pdf.bind("<B2-Motion>", lambda e: None)

widget_frame = ttk.Frame(root)
widget_frame.pack(fill="x", pady=5)

if __name__ == "__main__":
    # Delay first render so canvas dimensions are correct
    # Only render after Tk finishes drawing the window
    root.after(200, lambda: render_page() if pages else None)
    root.mainloop()

