"""
whatsapp-alerts: envía un mensaje a una lista de contactos de WhatsApp Web
a través de Chrome DevTools Protocol (CDP).

Requiere:
- Chrome con WhatsApp Web vinculado, corriendo con --remote-debugging-port=9223
  y un perfil aislado (ver README).
- `websocket-client` instalado.

Los contactos se leen de recipients.json (no hardcodeados) para no exponer
nombres personales en el repo.

Uso:
    python send_whatsapp.py <archivo_mensaje.txt>
"""
import json, sys, os, urllib.request, websocket, time

CDP_PORT = 9223
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_MSG_FILE = os.path.join(BASE_DIR, "message.txt")
RECIPIENTS_FILE = os.path.join(BASE_DIR, "recipients.json")

def get_ws():
    """Selecciona la pestana de WhatsApp Web (no la primera pagina cualquiera)."""
    tabs = json.load(urllib.request.urlopen(f"http://127.0.0.1:{CDP_PORT}/json"))
    wa = [t for t in tabs if t.get('type') == 'page' and 'web.whatsapp.com' in t.get('url', '')]
    if wa:
        return wa[0]['webSocketDebuggerUrl']
    # si no hay pestana de whatsapp, abrir una
    target = {'url': 'https://web.whatsapp.com'}
    req = urllib.request.Request(f"http://127.0.0.1:{CDP_PORT}/json/new", data=json.dumps(target).encode(),
                                 headers={'Content-Type': 'application/json'})
    try:
        newtab = json.load(urllib.request.urlopen(req, timeout=15))
        return newtab['webSocketDebuggerUrl']
    except Exception:
        # fallback: primera pagina
        return next(t['webSocketDebuggerUrl'] for t in tabs if t.get('type') == 'page')

class WA:
    def __init__(self):
        self.ws = websocket.create_connection(get_ws(), timeout=25)
        self._id = [0]

    def send(self, m, p=None):
        self._id[0] += 1
        self.ws.send(json.dumps({"id": self._id[0], "method": m, "params": p or {}}))
        while True:
            r = json.loads(self.ws.recv())
            if r.get("id") == self._id[0]:
                return r

    def js(self, expr):
        r = self.send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
        return r.get("result", {}).get("result", {}).get("value")

    def press_key(self, key, code, vk):
        self.send("Input.dispatchKeyEvent", {"type": "keyDown", "key": key, "code": code,
                                             "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk})
        self.send("Input.dispatchKeyEvent", {"type": "keyUp", "key": key, "code": code,
                                             "windowsVirtualKeyCode": vk, "nativeVirtualKeyCode": vk})

    def clear_search(self):
        self.js("""(function(){var i=document.querySelector('input[type="text"]');if(i){i.focus();i.select();}return true;})()""")
        self.press_key("Backspace", "Backspace", 8); time.sleep(0.5)

    def search(self, contact):
        self.clear_search()
        for ch in contact:
            self.send("Input.dispatchKeyEvent", {"type": "char", "text": ch}); time.sleep(0.03)
        time.sleep(2.2)

    def click_result_index(self, query, index):
        """Busca query y hace clic en el enesimo list-item que coincide (nombres duplicados)."""
        self.search(query)
        expr = """(function(){var items=[];document.querySelectorAll('[data-testid^="list-item-"]').forEach(function(e){
          var t=e.querySelector('[data-testid="cell-frame-title"]');
          if(t && t.innerText.trim().toLowerCase().includes(%s)) items.push(e);
        });
        if(items.length<=%d) return 'NO';
        var el=items[%d].querySelector('[data-testid="cell-frame-title"]');
        var r=el.getBoundingClientRect();
        return JSON.stringify({x:r.x+r.width/2,y:r.y+r.height/2});
        })()""" % (json.dumps(query.lower()), index, index)
        c = self.js(expr)
        if c == 'NO':
            return False
        try:
            cc = json.loads(c)
            self.send("Input.dispatchMouseEvent", {"type": "mousePressed", "x": cc['x'], "y": cc['y'],
                                                    "button": "left", "clickCount": 1})
            self.send("Input.dispatchMouseEvent", {"type": "mouseReleased", "x": cc['x'], "y": cc['y'],
                                                    "button": "left", "clickCount": 1})
            time.sleep(2.5)
            return True
        except Exception:
            return False

    def send_msg(self, contact, msg, index=None):
        # usar SIEMPRE clic directo en el list-item (mas robusto que Enter)
        if index is None:
            index = 0
        if not self.click_result_index(contact, index):
            return f"ERROR: no se hallo {contact}#{index+1}"
        has_ed = self.js("""(function(){var p=document.querySelector('footer div[contenteditable="true"]');if(!p)return false;p.focus();return true;})()""")
        if not has_ed:
            return f"ERROR: no editor para {contact}"
        time.sleep(0.5)
        # Input.insertText -> dispara los eventos reales que React espera
        self.send("Input.insertText", {"text": msg})
        time.sleep(1.2)
        self.press_key("Enter", "Enter", 13); time.sleep(1.5)
        self.press_key("Escape", "Escape", 27); time.sleep(0.8)
        label = f"{contact}#{index+1}"
        return "OK " + label


def load_recipients():
    """Recipients: [{query, index}]. query es el texto a buscar, index el list-item
    (para nombres duplicados; omitir index para usar el primer resultado)."""
    with open(RECIPIENTS_FILE, encoding="utf-8") as f:
        return json.load(f)


if __name__ == "__main__":
    msg_file = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_MSG_FILE
    msg = open(msg_file, encoding="utf-8-sig").read().strip()
    recipients = load_recipients()

    wa = WA()
    results = []
    for r in recipients:
        results.append(wa.send_msg(r["query"], msg, r.get("index")))
        time.sleep(1)
    print("; ".join(results))
    wa.ws.close()
