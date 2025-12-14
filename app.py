from flask import Flask, request
from datetime import datetime
import gspread
import json
import os
from google.oauth2.service_account import Credentials

app = Flask(__name__)

# === CONFIG ===
SPREADSHEET_ID = "1xdvTSP430mOdFmmT4jSlYdJAsxK_92oozURlmgfTdkU"      # <- pegá el ID real
WORKSHEET_NAME = "Movimientos"        # <- pestaña exacta

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

def get_worksheet():
    creds_json = os.environ.get("GOOGLE_CREDENTIALS_JSON")
    if not creds_json:
        raise Exception("No se encontró la variable GOOGLE_CREDENTIALS_JSON")

    creds_dict = json.loads(creds_json)
    credentials = Credentials.from_service_account_info(creds_dict, scopes=SCOPES)
    client = gspread.authorize(credentials)

    sh = client.open_by_key(SPREADSHEET_ID)
    ws = sh.worksheet(WORKSHEET_NAME)
    return ws

def parsear_mensaje(texto: str):
    parts = texto.strip().split()
    if len(parts) < 3 or parts[0].lower() != "gasto":
        raise ValueError("Usá: gasto <monto> <categoria> [detalle]. Ej: gasto 10000 supermercado")

    monto = int(parts[1].replace(".", "").replace(",", ""))
    categoria = parts[2]
    descripcion = " ".join(parts[3:]) if len(parts) > 3 else ""
    return monto, categoria, descripcion

def registrar_gasto(monto, categoria, descripcion, quien):
    ws = get_worksheet()
    fecha = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    ws.append_row([fecha, monto, categoria.lower(), descripcion, quien])

@app.route("/twilio", methods=["POST"])
def twilio_webhook():
    texto = request.form.get("Body", "")
    quien = request.form.get("From", "")

    try:
        monto, categoria, descripcion = parsear_mensaje(texto)
        registrar_gasto(monto, categoria, descripcion, quien)

        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Message>✅ Registrado: ${monto} en {categoria}. {('(' + descripcion + ')') if descripcion else ''}</Message>
</Response>""", 200, {"Content-Type": "application/xml"}

    except Exception as e:
        return f"""<?xml version="1.0" encoding="UTF-8"?>
<Response>
  <Message>❌ {str(e)}</Message>
</Response>""", 200, {"Content-Type": "application/xml"}
