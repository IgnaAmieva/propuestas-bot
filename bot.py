# Bot de propuestas — versión sin IA (costo $0).
# Busca proyectos nuevos en Freelancer.com, filtra y te los manda a Telegram.
import os, json, time, html, urllib.request, urllib.parse

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

HORAS = 2                 # cada cuánto corre (igual que el cron)
MIN_USD = 100             # presupuesto mínimo en dólares
MAX_OFERTAS_RIVALES = 20  # si ya tiene más propuestas, no vale la pena
MAX_POR_TANDA = 15        # tope de avisos por corrida (los mejores primero)

BUSQUEDAS = [
    # Webs
    "website", "landing page", "wordpress", "shopify", "web development",
    "ecommerce", "página web", "sitio web", "fix website", "website bug",
    # Apps
    "web app", "mobile app", "flutter", "react", "next.js", "node.js",
    "android app", "app development", "supabase", "firebase", "aplicación",
    "php", "laravel", "javascript", "typescript", "full stack",
    # Automatización / backend
    "automation", "n8n", "zapier", "make.com", "chatbot", "whatsapp bot",
    "telegram bot", "api integration", "api development", "python script",
    "web scraping", "ai agent", "openai api", "chrome extension",
    "automatización", "programador",
]

# Si el título o la descripción tienen alguna de estas, se descarta
PROHIBIDAS = [
    "fake review", "fake followers", "buy followers", "reseñas falsas",
    "seguidores falsos", "hack", "crack", "bypass", "casino", "betting",
    "adult", "onlyfans", "captcha solving", "account verification",
    # Proyectos que piden una ubicación específica (no aplica desde Argentina)
    "indian freelancer", "from india", "based in india", "only india",
    "must be located", "must be based", "local only", "only from",
    "us only", "usa only", "uk only", "native english", "indian freelance",
    "hindi", "bay area",
]


def pedir(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers=headers or {})
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


# El proyecto tiene que tener al menos una categoría de programación
CATEGORIAS_OK = [
    "web", "php", "javascript", "html", "css", "wordpress", "shopify", "woocommerce",
    "app", "android", "iphone", "ios", "flutter", "react", "node", "next.js",
    "python", "software", "api", "automation", "n8n", "zapier", "make.com",
    "chatbot", "bot", "scraping", "mobile", "full stack", "frontend", "backend",
    "database", "mysql", "postgres", "supabase", "firebase", "openai", "ai ",
    "artificial intelligence", "machine learning", "typescript", "laravel",
    "ecommerce", "e-commerce", "programming", "google apps script", "chrome",
    "gohighlevel", "go high level", "saas",
]
# Si tiene alguna de estas categorías, no es para nosotros
CATEGORIAS_NO = [
    "sales", "business development", "commission", "lead generation", "telemarketing",
    "video", "photography", "script writing", "architect", "building",
    "structural", "cad", "translation", "data entry", "article writing",
    "content writing", "voice", "animation", "motion graphics",
]


def es_de_programacion(p):
    cats = " | ".join(j.get("name", "").lower() for j in (p.get("jobs") or []))
    titulo = (p.get("title") or "").lower()
    if any(w in cats or w in titulo for w in CATEGORIAS_NO):
        return False
    return any(w in cats for w in CATEGORIAS_OK)


def presupuesto_usd(p):
    b = p.get("budget") or {}
    tasa = (p.get("currency") or {}).get("exchange_rate") or 1
    minimo = b.get("minimum") or 0
    maximo = b.get("maximum") or minimo
    return (minimo + maximo) / 2 * tasa


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
            texto = f"{p.get('title', '')} {p.get('preview_description', '')}".lower()
            ofertas = (p.get("bid_stats") or {}).get("bid_count", 0)
            if ofertas >= MAX_OFERTAS_RIVALES:
                continue
            if presupuesto_usd(p) < MIN_USD:
                continue
            if any(w in texto for w in PROHIBIDAS):
                continue
            if not es_de_programacion(p):
                continue
            proyectos[p["id"]] = p
    # Mejores primero: menos competencia y más plata
    orden = sorted(
        proyectos.values(),
        key=lambda p: ((p.get("bid_stats") or {}).get("bid_count", 0), -presupuesto_usd(p)),
    )
    return orden[:MAX_POR_TANDA], len(proyectos)


def traducir(texto):
    """Traduce al español gratis. Si falla, devuelve el texto original."""
    if not texto:
        return texto
    try:
        params = urllib.parse.urlencode({
            "client": "gtx", "sl": "auto", "tl": "es", "dt": "t", "q": texto,
        })
        req = urllib.request.Request(
            f"https://translate.googleapis.com/translate_a/single?{params}",
            headers={"User-Agent": "Mozilla/5.0"},
        )
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read().decode())
        return "".join(parte[0] for parte in data[0] if parte[0])
    except Exception as e:
        print(f"No se pudo traducir: {e}")
        return texto


def enviar(texto):
    body = urllib.parse.urlencode({
        "chat_id": CHAT_ID, "text": texto[:4000],
        "parse_mode": "HTML", "disable_web_page_preview": "true",
    }).encode()
    pedir(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", data=body)


def main():
    proyectos, total = buscar_proyectos()
    print(f"Pasaron el filtro: {total} · envío: {len(proyectos)}")
    e = html.escape
    for p in proyectos:
        b = p.get("budget") or {}
        moneda = (p.get("currency") or {}).get("code", "")
        ofertas = (p.get("bid_stats") or {}).get("bid_count", 0)
        desc = (p.get("description") or p.get("preview_description") or "").strip()
        if len(desc) > 700:
            desc = desc[:700] + "…"
        titulo = traducir(p.get("title", ""))
        desc = traducir(desc)
        link = f"https://www.freelancer.com/projects/{p.get('seo_url', p['id'])}"
        enviar(
            f"🟢 <b>{e(titulo)}</b>\n"
            f"💰 {b.get('minimum')} - {b.get('maximum')} {e(moneda)} "
            f"(~USD {presupuesto_usd(p):.0f}) · 👥 {ofertas} propuestas\n"
            f"🆔 {p['id']}\n\n"
            f"{e(desc)}\n\n🔗 {link}"
        )
    if not proyectos and os.environ.get("GITHUB_EVENT_NAME") in ("workflow_dispatch", "push"):
        enviar("✅ Bot funcionando. Esta vez no hubo proyectos que pasen el filtro.")


if __name__ == "__main__":
    main()
