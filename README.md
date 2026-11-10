# Fábrica de videos de tendencia (TikTok · Reels · YouTube Shorts)

Cada noche, GitHub Actions:

1. **Busca tendencias**: Google Trends de MX/US/ES y, si hay `YT_API_KEY`, lo más popular de YouTube. Se guardan en `trends/`.
2. **Escribe guiones** con Claude cuando la cola tiene menos de 4 (necesita `ANTHROPIC_API_KEY`).
3. **Renderiza** un video vertical 1080x1920 con texto animado, voz en español (edge-tts) y una música de fondo sintetizada, libre de derechos.
4. **Publica** en YouTube Shorts, Instagram Reels y TikTok, en cada plataforma que tenga credenciales.
5. Mueve el guion a `content/published/` con los links de cada plataforma.

Horario: 1:00, 3:00 y 5:00 hora de Ciudad de México, un video por corrida. Puedes cambiarlo en `.github/workflows/nightly.yml`.

## Configuración (una sola vez)

Agrega cada secret en GitHub → repo → **Settings → Secrets and variables → Actions**.

| Secret | Para qué | Cómo conseguirlo |
|---|---|---|
| `ANTHROPIC_API_KEY` | escribir guiones nuevos de forma automática | console.anthropic.com |
| `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` | subir a YouTube | ejecuta `python src/get_youtube_token.py`; los pasos están dentro del archivo |
| `YT_API_KEY` *(opcional)* | leer tendencias de YouTube | Google Cloud → Credenciales → Clave de API |
| `IG_USER_ID`, `IG_ACCESS_TOKEN` | publicar Reels | cuenta Instagram **Profesional** vinculada a una página de Facebook, más una app de Meta con permiso `instagram_content_publish`; usa un token de larga duración (60 días) |
| `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN` | TikTok | developers.tiktok.com → app con *Content Posting API* (scope `video.upload`) |

### Límites de las plataformas (importante)

- **YouTube**: los proyectos de API sin verificar suben los videos como **privados**. Pide la auditoría de la API en Google Cloud; mientras tanto, los videos quedan privados y puedes hacerlos públicos desde YouTube Studio.
- **TikTok**: el modo `inbox` (predeterminado) manda el video a tus borradores. Por la mañana le agregas el **sonido en tendencia** y tocas Publicar. La API no permite poner sonidos de la biblioteca de TikTok. El modo `direct` publica solo, pero hasta que TikTok audite tu app los videos quedan visibles solo para ti.
- **Instagram**: publica directo como Reel. El token vence a los 60 días, así que hay que renovarlo.
- **Música en tendencia** (Mariah Carey, Tate McRae, etc.): tiene copyright. No la incrustamos en el video. Agrégala dentro de cada app.

## Uso manual

```bash
pip install -r requirements.txt            # también necesitas ffmpeg
python src/run_nightly.py --dry-run        # solo renderiza en out/
python src/render.py content/queue/<id>.json out/prueba.mp4
python src/write_scripts.py 5              # 5 guiones nuevos con Claude
```

En GitHub → **Actions → "Publicar videos (noche)" → Run workflow** lo corres ahora mismo. Con *dry run* solo genera los videos y los deja descargables como artifact.

## Agregar guiones a mano

Crea un JSON en `content/queue/` con el formato de los que ya existen. `priority` es opcional: el número menor sale primero. Ajustes generales como voz, idioma, nicho, países y videos por corrida están en `config.json`.
