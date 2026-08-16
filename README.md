# WhatsApp Sismos Alerts

Automatización que envía **alertas de sismos de Colombia a contactos de WhatsApp** de forma autónoma **sin usar un modelo de lenguaje (LLM)**. Un script de Python puro consulta al **Servicio Geológico Colombiano (SGC)** y, cuando registra un sismo fuerte o sentido, arma el mensaje y lo entrega por WhatsApp Web usando **Chrome DevTools Protocol (CDP)**.

> **Privacidad:** la lista de destinatarios se mantiene en `recipients.json` (NO se sube al repo — ver `recipients.example.json`). Aquí solo se documenta la mecánica.
>
> **Costo:** el monitoreo corre como un cron en modo `no_agent` (solo ejecuta el script, sin LLM) → **cero tokens** en el ciclo normal.

---

## 🔁 Cómo funciona

```mermaid
flowchart TD
    C[Cron cada 5 min - no_agent] -->|ejecuta| Mon[monitor_sismos.py - Python puro]
    Mon -->|consulta API| S[SGC api.sgc.gov.co]
    S -->|GeoJSON| F{Filtra sismos nuevos}
    F -->|sin sismo fuerte| Q[stdout vacio - silencio]
    F -->|sismo >=4.5M o sentido >=3.5M en 6h| M[Arma mensaje texto]
    M --> P[Escribe message.txt]
    P --> W[send_whatsapp.py - CDP]
    W -->|busca contacto + Enter| C2[Chrome WhatsApp Web]
    C2 -->|Input.insertText| E[Editor de mensaje]
    E -->|Enter| D[Envia a contactos]
    D -->|OK| St[Guarda IDs en state.json]
```

**Flujo de envío por contacto:**

```mermaid
sequenceDiagram
    participant C as Cron (no_agent)
    participant Mon as monitor_sismos.py
    participant W as send_whatsapp.py
    participant CH as Chrome (CDP :9223)

    C->>Mon: ejecuta cada 5 min (sin LLM)
    Mon->>Mon: consulta API SGC, filtra sismos nuevos
    Mon->>Mon: sin novedad → termina (stdout vacío)
    Mon->>W: hay sismo → escribe message.txt y ejecuta
    W->>CH: Runtime.evaluate → enfocar input de búsqueda
    W->>CH: Input.dispatchKeyEvent (chars del contacto)
    W->>CH: Enter → abre chat (o clic en list-item para duplicados)
    W->>CH: Input.insertText(msg) → pega en contenteditable
    W->>CH: Enter → envía
    CH-->>W: OK contacto
    W-->>Mon: "OK ..." por cada destino
    Mon->>Mon: guarda IDs enviados en state.json
```

---

## 📌 Por qué CDP y no pyautogui

La app de escritorio de WhatsApp **no se puede automatizar** con pyautogui: su ventana ignora el foco de teclado inyectado desde fuera (verificado: 0.00% de cambio al escribir). La vía fiable es **WhatsApp Web en un Chrome con CDP**, donde se controla el DOM/React directamente con eventos reales (`Input.dispatchKeyEvent` para buscar y `Input.insertText` para el editor — React ignora el setter virtual `input.value=`).

---

## 🚀 Setup

1. **Dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Lanzar Chrome con WhatsApp Web vinculado** (una sola vez, en la sesión interactiva del usuario):
   ```bash
   chrome --remote-debugging-port=9223 --remote-allow-origins=* \
          --user-data-dir="C:\Users\<user>\.chrome-wa" "https://web.whatsapp.com"
   ```
   Escanear el QR desde el cel (WhatsApp → Dispositivos vinculados → Vincular dispositivo). Queda vinculado a ese perfil permanentemente.

3. **Configurar destinatarios** — copiar `recipients.example.json` → `recipients.json` y poner los contactos:
   ```json
   [
     {"query": "Nombre Contacto", "index": 0},
     {"query": "Nombre Duplicado", "index": 1}
   ]
   ```
   - `query`: texto a buscar en WhatsApp.
   - `index`: list-item a abrir (0 = primer resultado; úsalo para nombres duplicados).

4. **Enviar:**
   ```bash
   python send_whatsapp.py message.txt
   ```
   El script lee `message.txt` y envía a todos los destinatarios, imprimiendo `OK ...` por cada uno.

---

## 📁 Estructura

```
whatsapp-sismos-alerts/
├── monitor_sismos.py        # Monitor autónomo (Python puro, sin LLM)
├── send_whatsapp.py         # Script de envío vía CDP
├── recipients.example.json  # Plantilla de destinatarios (sin datos reales)
├── requirements.txt         # websocket-client, pyautogui
└── README.md
```

**En producción (no subido):**
- `recipients.json` — lista real de contactos (privada)
- `message.txt` — mensaje generado por el monitor
- `state.json` — IDs de sismos ya enviados (evita repetir)
- `.chrome-wa` — perfil de Chrome de WhatsApp (vinculado)

---

## 🔒 Notas

- El envío requiere que el **Chrome de WhatsApp Web** esté corriendo. Si se cierra, el monitor reporta el error hasta reabrirlo.
- El monitor corre como cron en modo `no_agent` (sin LLM): con un sismo nuevo imprime el mensaje; sin novedad no imprime nada (silencio).
- El umbral de alerta (≥4.5 M o sentido ≥3.5 M, ventana 6 h) lo define `monitor_sismos.py`.
- Datos de sismos: propiedad del SGC, API público.
