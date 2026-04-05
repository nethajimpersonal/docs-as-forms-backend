"""Font constants used by template filling and UI dropdowns."""
from enum import Enum


class FontFamily(str, Enum):
    ARIAL = "Arial"
    CALIBRI = "Calibri"
    CAMBRIA = "Cambria"
    COURIER_NEW = "Courier New"
    GEORGIA = "Georgia"
    GARAMOND = "Garamond"
    HELVETICA = "Helvetica"
    TAHOMA = "Tahoma"
    TIMES_NEW_ROMAN = "Times New Roman"
    TREBUCHET_MS = "Trebuchet MS"
    VERDANA = "Verdana"
