# Bot de propuestas — versión sin IA (costo $0).
# Busca proyectos nuevos en Freelancer.com, filtra y te los manda a Telegram.
import os, json, time, html, urllib.request, urllib.parse

TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
CHAT_ID = os.environ["TELEGRAM_CHAT_ID"]

HORAS = 12                # mira proyectos publicados en las últimas 12 h (no repite: guarda los enviados)
MIN_USD = 50              # presupuesto mínimo (promedio del rango) en dólares
MAX_OFERTAS_RIVALES = 40  # si ya tiene más propuestas, no vale la pena
MAX_POR_TANDA = 15        # tope de avisos por corrida (los mejores primero)
ARCHIVO_ENVIADOS = "enviados.json"
ESTADISTICAS = {}

# Categorías oficiales de Freelancer (las mismas habilidades de tu perfil y afines).
# El bot busca sus IDs solo, así trae proyectos de esas categorías y no por palabra suelta.
CATEGORIAS_FREELANCER = [
    "PHP", "Website Design", "Javascript", "HTML", "Node.js", "React.js", "Next.js",
    "Flutter", "Android", "iPhone", "Mobile App Development", "React Native",
    "Python", "Software Development", "API", "API Development", "API Integration",
    "Automation", "n8n", "Zapier", "Make.com", "Web Development", "Website Development",
    "Full Stack Development", "Frontend Development", "Backend Development",
    "WordPress", "Shopify", "eCommerce", "Chatbot", "Web Scraping", "MySQL",
    "Laravel", "Firebase", "Supabase", "TypeScript", "OpenAI", "AI Development",
    "Google Apps Script", "GoHighLevel",
]

# Refuerzo por palabra clave (sobre todo para proyectos en español)
BUSQUEDAS = [
    "página web", "sitio web", "aplicación", "automatización", "programador",
    "desarrollador", "bot whatsapp", "tienda online",
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
    "ai art", "photoshop", "image editing", "illustration", "sap",
    "regression testing", "erp", "salesforce",
    "music", "audio", "mixing", "mastering", "sound", "producer", "singing",
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


def ids_de_categorias():
    ids = []
    for i in range(0, len(CATEGORIAS_FREELANCER), 15):
        params = urllib.parse.urlencode(
            [("job_names[]", n) for n in CATEGORIAS_FREELANCER[i:i + 15]]
        )
        try:
            data = pedir(f"https://www.freelancer.com/api/projects/0.1/jobs/?{params}",
                         headers={"User-Agent": "propuestas-bot"})
            ids += [j["id"] for j in data.get("result", [])]
        except Exception as e:
            print(f"Error buscando categorías: {e}")
    print(f"Categorías encontradas: {len(ids)}")
    ESTADISTICAS["categorias"] = len(ids)
    return ids


def traer_proyectos(extra):
    desde = int(time.time()) - HORAS * 3600
    params = [("limit", 100), ("from_time", desde), ("full_description", "true"),
              ("job_details", "true"), ("sort_field", "time_updated")] + extra
    url = ("https://www.freelancer.com/api/projects/0.1/projects/active/?"
           + urllib.parse.urlencode(params))
    try:
        return pedir(url, headers={"User-Agent": "propuestas-bot"}) \
            .get("result", {}).get("projects", [])
    except Exception as e:
        print(f"Error trayendo proyectos: {e}")
        return []


def cargar_enviados():
    try:
        with open(ARCHIVO_ENVIADOS) as f:
            return set(json.load(f))
    except Exception:
        return set()


def guardar_enviados(ids):
    with open(ARCHIVO_ENVIADOS, "w") as f:
        json.dump(sorted(ids)[-2000:], f)


def buscar_proyectos(enviados):
    crudos = {}
    ids = ids_de_categorias()
    # Por categorías (lo principal), en tandas para no hacer URLs gigantes
    for i in range(0, len(ids), 20):
        for p in traer_proyectos([("jobs[]", j) for j in ids[i:i + 20]]):
            crudos[p["id"]] = p
    # Refuerzo: proyectos en español por palabra clave
    for q in BUSQUEDAS:
        for p in traer_proyectos([("query", q)]):
            crudos[p["id"]] = p
    print(f"Proyectos nuevos vistos: {len(crudos)}")
    ESTADISTICAS["vistos"] = len(crudos)
    motivos = {"ya_enviado": 0, "muchas_ofertas": 0, "poca_plata": 0,
               "prohibida": 0, "no_programacion": 0}

    proyectos = []
    for p in crudos.values():
        if (p.get("language") or "en") not in ("en", "es"):
            motivos["otro_idioma"] = motivos.get("otro_idioma", 0) + 1
            continue
        if p["id"] in enviados:
            motivos["ya_enviado"] += 1
            continue
        texto = f"{p.get('title', '')} {p.get('preview_description', '')}".lower()
        if (p.get("bid_stats") or {}).get("bid_count", 0) >= MAX_OFERTAS_RIVALES:
            motivos["muchas_ofertas"] += 1
            continue
        if presupuesto_usd(p) < MIN_USD:
            motivos["poca_plata"] += 1
            continue
        if any(w in texto for w in PROHIBIDAS):
            motivos["prohibida"] += 1
            continue
        if not es_de_programacion(p):
            motivos["no_programacion"] += 1
            continue
        proyectos.append(p)

    ESTADISTICAS["descartados"] = motivos
    ESTADISTICAS["pasaron"] = len(proyectos)
    # Mejores primero: en español, menos competencia, más plata
    orden = sorted(proyectos, key=lambda p: (
        0 if (p.get("language") or "") == "es" else 1,
        (p.get("bid_stats") or {}).get("bid_count", 0),
        -presupuesto_usd(p),
    ))
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
    enviados = cargar_enviados()
    proyectos, total = buscar_proyectos(enviados)
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
        enviados.add(p["id"])
    guardar_enviados(enviados)
    ESTADISTICAS["hora"] = time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime())
    with open("estadisticas.json", "w") as f:
        json.dump(ESTADISTICAS, f, indent=1)
    if not proyectos and os.environ.get("GITHUB_EVENT_NAME") in ("workflow_dispatch", "push"):
        enviar("✅ Bot funcionando. Esta vez no hubo proyectos que pasen el filtro.")


if __name__ == "__main__":
    main()
