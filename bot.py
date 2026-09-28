import os, json, time, html, urllib.request, urllib.parse

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]
ANTHROPIC_KEY = os.environ["ANTHROPIC_API_KEY"]

MODELO = "claude-haiku-4-5-20251001"  # barato y rápido
HORAS = 2                # cada cuánto corre (igual que el cron)
MAX_OFERTAS_RIVALES = 40 # si ya tiene más propuestas, no vale la pena
MAX_POR_TANDA = 40       # tope de proyectos por corrida (controla el costo)

BUSQUEDAS = [
    # Webs
    "website", "landing page", "wordpress", "shopify", "wix", "web design",
    "ecommerce", "página web", "sitio web",
    # Apps
    "web app", "mobile app", "flutter", "react", "next.js", "android", "ios app",
    "app development", "supabase", "firebase", "aplicación",
    # Automatización
    "automation", "n8n", "zapier", "make.com", "chatbot", "whatsapp bot",
    "telegram bot", "api integration", "python script", "web scraping",
    "ai agent", "automatización",
    # Diseño / Canva
    "canva", "graphic design", "logo", "flyer", "social media design",
    "instagram post", "presentation design", "banner", "diseño gráfico",
    # Redes
    "social media manager", "instagram", "twitter",
]

PERFIL = """Sos el asistente de Igna, desarrollador freelance de Argentina.
Qué hace: landing pages y webs para negocios, web apps y PWAs (Next.js, Supabase,
Mercado Pago), apps móviles con Flutter, bots de WhatsApp/Telegram y automatizaciones
(n8n, Zapier, Make, scripts en Python, integraciones de APIs, agentes de IA),
diseño gráfico (Canva: posts, flyers, logos, presentaciones),
y gestión de redes (Instagram y X/Twitter): contenido, diseño y publicación.
Trabajos reales: PWA de pedidos con Mercado Pago, bot de turnos para una clínica,
landings de e-commerce y de empresas.

Te paso un proyecto publicado por un cliente. Respondé SOLO un JSON:
{"sirve": true/false, "resumen": "1 línea en español de qué pide",
 "propuesta": "propuesta lista para enviar", "traduccion": "traducción al español si la propuesta no está en español, si no vacío"}

Reglas:
- Sé amplio: "sirve" es true para cualquier web, app, automatización, bot,
  integración, script, diseño gráfico/Canva o redes que Igna pueda resolver.
- "sirve" es false si claramente no encaja (ej: contabilidad, redacción larga, video 3D), si es sospechoso/estafa,
  o si pide cosas truchas (seguidores falsos, reseñas falsas, cuentas robadas).
- La propuesta va en el idioma del proyecto, corta (máx 120 palabras), personalizada:
  mencioná algo concreto del pedido, cómo lo resolverías y una pregunta al final.
- No inventes experiencia, reseñas ni plazos que no puedas cumplir.
- Dejá [PORTFOLIO] donde va el link al portfolio."""


def pedir(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def buscar_proyectos():
    desde = int(time.time()) - HORAS * 3600
    proyectos = {}
    for q in BUSQUEDAS:
        params = urllib.parse.urlencode({
            "query": q, "limit": 30, "from_time": desde,
            "full_description": "true", "job_details": "true",
        })
        url = f"https://www.freelancer.com/api/projects/0.1/projects/active/?{params}"
        try:
            data = pedir(url, headers={"User-Agent": "propuestas-bot"})
        except Exception as e:
            print(f"Error buscando '{q}': {e}")
            continue
        for p in data.get("result", {}).get("projects", []):
            ofertas = (p.get("bid_stats") or {}).get("bid_count", 0)
            if ofertas < MAX_OFERTAS_RIVALES:
                proyectos[p["id"]] = p
    return list(proyectos.values())[:MAX_POR_TANDA]


def evaluar(p):
    b = p.get("budget") or {}
    moneda = (p.get("currency") or {}).get("code", "")
    texto = (
        f"Título: {p.get('title')}\n"
        f"Presupuesto: {b.get('minimum')} - {b.get('maximum')} {moneda}\n"
        f"Descripción: {p.get('description') or p.get('preview_description', '')}"
    )
    body = json.dumps({
        "model": MODELO, "max_tokens": 900, "system": PERFIL,
        "messages": [{"role": "user", "content": texto}],
    }).encode()
    data = pedir("https://api.anthropic.com/v1/messages", data=body, headers={
        "x-api-key": ANTHROPIC_KEY,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    })
    t = data["content"][0]["text"]
    return json.loads(t[t.find("{"): t.rfind("}") + 1])


def enviar(texto):
    body = urllib.parse.urlencode({
        "chat_id": CHAT_ID, "text": texto[:4000],
        "parse_mode": "HTML", "disable_web_page_preview": "true",
    }).encode()
    pedir(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data=body)


def main():
    proyectos = buscar_proyectos()
    print(f"Encontrados: {len(proyectos)}")
    enviados = 0
    for p in proyectos:
        try:
            r = evaluar(p)
        except Exception as e:
            print(f"Error evaluando {p.get('id')}: {e}")
            continue
        if not r.get("sirve"):
            continue
        b = p.get("budget") or {}
        moneda = (p.get("currency") or {}).get("code", "")
        ofertas = (p.get("bid_stats") or {}).get("bid_count", 0)
        link = f"https://www.freelancer.com/projects/{p.get('seo_url', p['id'])}"
        e = html.escape
        msg = (
            f"🟢 <b>{e(p.get('title', ''))}</b>\n"
            f"💰 {b.get('minimum')} - {b.get('maximum')} {e(moneda)} · 👥 {ofertas} propuestas\n"
            f"📝 {e(r.get('resumen', ''))}\n\n"
            f"<b>Propuesta:</b>\n<code>{e(r.get('propuesta', ''))}</code>\n"
        )
        if r.get("traduccion"):
            msg += f"\n<b>Traducción:</b>\n<i>{e(r['traduccion'])}</i>\n"
        msg += f"\n🔗 {link}"
        enviar(msg)
        enviados += 1
    if enviados == 0 and os.environ.get("GITHUB_EVENT_NAME") == "workflow_dispatch":
        enviar(f"✅ Bot funcionando. Revisé {len(proyectos)} proyectos nuevos y ninguno encajaba esta vez.")
    print(f"Enviados a Telegram: {enviados}")


if __name__ == "__main__":
    main()
