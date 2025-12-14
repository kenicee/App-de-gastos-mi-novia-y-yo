from flask import Flask, request
from datetime import datetime
import gspread
import json
import os
from google.oauth2.service_account import Credentials

app = Flask(__name__)

# ================= CONFIG =================

SPREADSHEET_ID = "1xdvTSP430mOdFmmT4jSlYdJAsxK_92oozURlmgfTdkU"
WORKSHEET_NAME = "Movimientos"

# 👇 REEMPLAZÁ CON LOS NÚMEROS REALES
ALIAS = {
    "whatsapp:+54911XXXXXXXX": "Facu",
    "whatsapp:+54911YYYYYYYY": "Lu"
}

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

HEADERS = ["fecha_hora", "año", "mes", "dia", "monto", "categoria", "descripcion", "quien"]

# ================= GOOGLE SHEETS =================

def gs_client():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not creds_json:
        raise Exception("No se encontró GOOGLE_CREDENTIALS_JSON")

    creds_dict = json.loads(creds_json)
    credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(credentials)

def get_or_create_ws():
    client = gs_client()
    sh = client.open_by_key(SPREADSHEET_ID)

    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except Exception:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=3000, cols=20)

    if ws.get("A1:H1") == [[]]:
        ws.update("A1:H1", [HEADERS])

    return ws

# ================= LÓGICA =================

def parsear_mensaje(texto: str):
    parts = texto.strip().split()
    if len(parts) < 3 or parts[0].lower() != "gasto":
        raise ValueError("Usá: gasto <monto> <categoria> [detalle]")

    monto = int(parts[1].replace(".", "").replace(",", ""))
    categoria = parts[2]
    descripcion = " ".join(parts[3:]) if len(parts) > 3 else ""
    return monto, categoria, descripcion

def registrar_gasto(monto, categoria, descripcion, quien_raw):
    ws = get_or_create_ws()
    now = datetime.now()

    quien = ALIAS.get(quien_raw, quien_raw)

    ws.append_row([
        now.strftime("%Y-%m-%d %H:%M:%S"),
        now.year,
        now.month,
        now.day,
        monto,
        categoria.lower(),
        descripcion,
        quien
    ])

def leer_movimientos(ws):
    values = ws.get_all_values()
    return values[1:] if len(values) > 1 else []

def sumar(ws, persona=None):
    rows = leer_movimientos(ws)
    now = datetime.now()
    anio, mes, dia = str(now.year), str(now.month), str(now.day)

    hoy = 0
    mes_total = 0

    for r in rows:
        if len(r) < 8:
            continue

        _, a, m, d, monto, _, _, quien = r

        if persona and quien.lower() != persona.lower():
            continue

        try:
            monto = float(monto)
        except:
            continue

        if a == anio and m == mes:
            mes_total += monto
            if d == dia:
                hoy += monto

    return hoy, mes_total

# ================= WEBHOOK =================

@app.route("/twilio", methods=["POST"])
def twilio_webhook():
    texto = request.form.get("Body", "").strip().lower()
    quien_raw = request.form.get("From", "")

    ws = get_or_create_ws()

    try:
        if texto.startswith("resumen"):
            parts = texto.split()
            persona = parts[1] if len(parts) > 1 else None

            hoy, mes_total = sumar(ws, persona)

            titulo = f"📊 Resumen {persona.capitalize()}" if persona else "📊 Resumen total"
            msg = (
                f"{titulo}\n"
                f"Hoy: ${int(hoy):,}\n"
                f"Mes: ${int(mes_total):,}"
            ).replace(",", ".")

        elif texto == "hoy":
            hoy, _ = sumar(ws)
            msg = f"💸 Total hoy: ${int(hoy):,}".replace(",", ".")

        elif texto == "mes":
            _, mes_total = sumar(ws)
            msg = f"📅 Total mes: ${int(mes_total):,}".replace(",", ".")

        else:
            monto, categoria, descripcion = parsear_mensaje(texto)
            registrar_gasto(monto, categoria, descripcion, quien_raw)
            msg = f"✅ Registrado: ${monto} en {categoria}"

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response><Message>{msg}</Message></Response>""", 200, {"Content-Type": "application/xml"}

    except Exception as e:
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response><Message>❌ {str(e)}</Message></Response>""", 200, {"Content-Type": "application/xml"}
