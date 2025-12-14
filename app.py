from flask import Flask, request
from datetime import datetime
import gspread
import json
import os
from google.oauth2.service_account import Credentials

app = Flask(__name__)

SPREADSHEET_ID = "1xdvTSP430mOdFmmT4jSlYdJAsxK_92oozURlmgfTdkU"
WORKSHEET_NAME = "Movimientos"

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

HEADERS = ["fecha_hora", "año", "mes", "dia", "monto", "categoria", "descripcion", "quien"]

def gs_client():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not creds_json:
        raise Exception("No se encontró GOOGLE_CREDENTIALS_JSON en Render")

    creds_dict = json.loads(creds_json)
    credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    return gspread.authorize(credentials)

def get_or_create_ws():
    client = gs_client()
    sh = client.open_by_key(SPREADSHEET_ID)

    try:
        ws = sh.worksheet(WORKSHEET_NAME)
    except Exception:
        ws = sh.add_worksheet(title=WORKSHEET_NAME, rows=2000, cols=20)
        print(f"[OK] Worksheet '{WORKSHEET_NAME}' creada")

    # Si A1 está vacío, setear headers
    if ws.get("A1:H1") == [[]]:
        ws.update("A1:H1", [HEADERS])
        print("[OK] Headers creados")

    return sh, ws

def parsear_mensaje(texto: str):
    parts = texto.strip().split()
    if len(parts) < 3 or parts[0].lower() != "gasto":
        raise ValueError("Usá: gasto <monto> <categoria> [detalle]. Ej: gasto 10000 supermercado")

    monto = int(parts[1].replace(".", "").replace(",", ""))
    categoria = parts[2]
    descripcion = " ".join(parts[3:]) if len(parts) > 3 else ""
    return monto, categoria, descripcion

def registrar_gasto(monto, categoria, descripcion, quien):
    sh, ws = get_or_create_ws()
    now = datetime.now()

    fecha_hora = now.strftime("%Y-%m-%d %H:%M:%S")
    anio = now.year
    mes = now.month
    dia = now.day

    ws.append_row([fecha_hora, anio, mes, dia, monto, categoria.lower(), descripcion, quien])
    print(f"[OK] Escribí fila en '{sh.title}' / '{ws.title}': {fecha_hora} {monto} {categoria} {quien}")

def leer_movimientos(ws):
    # Devuelve lista de filas (sin headers). Maneja hoja vacía.
    values = ws.get_all_values()
    if len(values) <= 1:
        return []
    return values[1:]  # sin headers

def sumar_hoy(ws):
    rows = leer_movimientos(ws)
    now = datetime.now()
    anio, mes, dia = str(now.year), str(now.month), str(now.day)

    total = 0
    for r in rows:
        # índices: 0 fecha_hora, 1 año, 2 mes, 3 dia, 4 monto
        if len(r) >= 5 and r[1] == anio and r[2] == mes and r[3] == dia:
            try:
                total += float(r[4])
            except:
                pass
    return total

def sumar_mes(ws):
    rows = leer_movimientos(ws)
    now = datetime.now()
    anio, mes = str(now.year), str(now.month)

    total = 0
    for r in rows:
        if len(r) >= 5 and r[1] == anio and r[2] == mes:
            try:
                total += float(r[4])
            except:
                pass
    return total

@app.route("/twilio", methods=["POST"])
def twilio_webhook():
    texto = request.form.get("Body", "")
    quien = request.form.get("From", "")

    try:
        sh, ws = get_or_create_ws()
        cmd = texto.strip().lower()

        if cmd == "estado":
            filas = len(ws.get_all_values())
            msg = f"📌 Escribiendo en: {sh.title} / {ws.title}. Filas: {filas}"
        elif cmd == "hoy":
            total = sumar_hoy(ws)
            msg = f"💸 Total gastado hoy: ${int(total):,}".replace(",", ".")
        elif cmd == "mes":
            total = sumar_mes(ws)
            msg = f"📅 Total gastado este mes: ${int(total):,}".replace(",", ".")
        elif cmd == "resumen":
            th = sumar_hoy(ws)
            tm = sumar_mes(ws)
            msg = (
                f"📌 Resumen\n"
                f"Hoy: ${int(th):,}\n"
                f"Mes: ${int(tm):,}"
            ).replace(",", ".")
        else:
            monto, categoria, descripcion = parsear_mensaje(texto)
            registrar_gasto(monto, categoria, descripcion, quien)
            msg = f"✅ Registrado: ${monto} en {categoria}. {('(' + descripcion + ')') if descripcion else ''}"

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response><Message>{msg}</Message></Response>""", 200, {"Content-Type": "application/xml"}

    except Exception as e:
        print(f"[ERROR] {str(e)}")
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response><Message>❌ {str(e)}</Message></Response>""", 200, {"Content-Type": "application/xml"}
