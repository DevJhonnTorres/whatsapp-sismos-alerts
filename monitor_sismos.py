"""
monitor_sismos.py — MONITOR AUTÓNOMO de sismos de Colombia.

100% independiente del LLM: corre solo, consulta la API del SGC, y cuando
hay un sismo fuerte o sentido NUEVO, arma el mensaje y lo envía por WhatsApp.

Sin novedad -> no imprime nada (el cron no_agent entrega vacío = silencio).
Sismo nuevo -> imprime el mensaje enviado (el cron lo entrega al canal).

No requiere tokens de LLM. Solo Python + websocket-client + Chrome CDP.
"""
import json
import urllib.request
import datetime
import subprocess
import sys
import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATE_FILE = os.path.join(BASE_DIR, "state.json")          # IDs ya enviados
MSG_FILE = os.path.join(BASE_DIR, "message.txt")            # mensaje para WhatsApp
RECIPIENTS_FILE = os.path.join(BASE_DIR, "recipients.json") # contactos (privado)
SEND_SCRIPT = os.path.join(BASE_DIR, "send_whatsapp.py")

API = "https://api.sgc.gov.co/biweekly/biweekly_earthquakes"
MAG_FUERTE = 4.5        # umbral de magnitud fuerte
MAG_SENTIDO = 3.5       # umbral de sismo sentido
VENTANA_HORAS = 6       # solo miramos sismos de las ultimas N horas
PYTHON = sys.executable


def fetch_sismos():
    hoy = datetime.date.today()
    ayer = hoy - datetime.timedelta(days=1)
    url = f"{API}?startdate={ayer}&enddate={hoy}"
    req = urllib.request.Request(url, headers={
        "Accept": "application/json", "User-Agent": "Mozilla/5.0"})
    data = json.load(urllib.request.urlopen(req, timeout=30))
    return data.get("features", [])


def es_noticiable(prop):
    mag = prop.get("mag") or 0
    sent = bool(prop.get("felt"))
    return mag >= MAG_FUERTE or (sent and mag >= MAG_SENTIDO)


def en_ventana(utc, horas=VENTANA_HORAS):
    try:
        t = datetime.datetime.strptime(utc, "%Y-%m-%d %H:%M:%S")
        now = datetime.datetime.utcnow()
        return (now - t).total_seconds() <= horas * 3600
    except Exception:
        return True  # si no podemos parsear, lo consideramos para no perderlo


def load_state():
    if os.path.exists(STATE_FILE):
        try:
            with open(STATE_FILE) as f:
                return set(json.load(f))
        except Exception:
            return set()
    return set()


def save_state(ids):
    with open(STATE_FILE, "w") as f:
        json.dump(sorted(ids), f)


def fmt_fecha(utc):
    try:
        d = datetime.datetime.strptime(utc, "%Y-%m-%d %H:%M:%S")
        return d.strftime("%d/%m")
    except Exception:
        return utc[:10]


def armar_mensaje(noticiables):
    """Top 4 mas recientes primero, formato texto plano (sin enlaces)."""
    noticiables.sort(key=lambda x: x["properties"].get("utcTime") or "", reverse=True)
    lineas = ["🌋 *Alertas de sismo Colombia* (SGC)", ""]
    for i, f in enumerate(noticiables[:4], 1):
        p = f["properties"]
        mag = p.get("mag") or 0
        lugar = (p.get("place") or "").replace(", Colombia", "")
        prof = p.get("depth")
        prof_txt = f"{prof} km" if prof is not None else "—"
        sent = "⚠️ Sentido" if p.get("felt") else ""
        lineas.append(f"{i}️⃣ {mag} M — {lugar}")
        lineas.append(f"📅 {fmt_fecha(p.get('utcTime'))} · Prof {prof_txt} {sent}")
        lineas.append("")
    return "\n".join(lineas).strip()


def main():
    feats = fetch_sismos()
    # noticiables nuevos y dentro de la ventana
    nuevos = [f for f in feats
              if es_noticiable(f["properties"]) and en_ventana(f["properties"].get("utcTime"))]

    if not nuevos:
        return  # sin novedad -> stdout vacio -> cron silencioso

    vistos = load_state()
    ids_pendientes = [f for f in nuevos if f.get("id") not in vistos]
    if not ids_pendientes:
        return  # ya avisamos de estos -> no repetir

    msg = armar_mensaje(ids_pendientes)
    # escribir mensaje (UTF-16) para send_whatsapp.py
    with open(MSG_FILE, "w", encoding="utf-8-sig") as f:
        f.write(msg)

    # enviar por WhatsApp (CDP)
    r = subprocess.run([PYTHON, SEND_SCRIPT, MSG_FILE],
                       capture_output=True, text=True, timeout=120)
    envio = r.stdout.strip()

    # marcar como enviados SOLO si WhatsApp confirmo OK
    ok_destinos = [d for d in envio.split(";") if "OK" in d]
    if ok_destinos:
        vistos.update(f.get("id") for f in ids_pendientes)
        save_state(vistos)

    # imprimir el mensaje para que el cron lo entregue (reporte)
    print(msg)
    print("")
    print("Envío WhatsApp:", envio if envio else "(sin confirmación)")
    if r.returncode != 0:
        print("Error script:", r.stderr.strip()[:300])


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        # fallo externo: imprimir para alertar, no fallar en silencio
        print(f"⚠️ Error monitoreo sismos: {e}")
