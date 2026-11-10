# Fábrica de videos de tendencia (TikTok · Reels · YouTube Shorts)

Cada noche, GitHub Actions:

1. **Busca tendencias**: Google Trends de MX/US/ES y, si hay `YT_API_KEY`, lo más popular de YouTube. Se guardan en `trends/`.
2. **Escribe guiones** con Claude cuando la cola tiene menos de 4 (necesita `ANTHROPIC_API_KEY`).
3. **Renderiza** un video vertical 1080x1920 pensado para que la gente se quede:
   - **Voz IA "Adam" de ElevenLabs**, la voz narradora que más se oye en Shorts y TikTok. Si no hay llave, usa una voz gratuita de Microsoft.
   - **Subtítulos tipo karaoke**: 1 a 3 palabras a la vez, y la que se está diciendo se ilumina.
   - **Animación hipnótica**: una pelota rebota dentro de un aro, crece con cada rebote y suena una nota. Al final casi llena el aro, así que la gente se queda a ver si lo logra.
   - Barra de progreso, encabezado que aparece con efecto "pop" en cada punto y un *whoosh* en cada transición.
   - Todo es generado, sin música ni imágenes con copyright.
4. **Publica** en YouTube Shorts, Instagram Reels y TikTok, con **hashtags por plataforma**:
   - TikTok: 5 en total (2 de tendencia, 2 del nicho y `#parati`).
   - Instagram: máximo 5, que es el límite actual.
   - YouTube: 3, que son los que se muestran arriba del título, incluido `#shorts`.

   Los hashtags generales se ajustan en `config.json` → `hashtags`.
5. Mueve el guion a `content/published/` con los links de cada plataforma.

Horario: 1:00, 3:00 y 5:00 hora de Ciudad de México, un video por corrida. Puedes cambiarlo en `.github/workflows/nightly.yml`.

## Configuración (una sola vez)

Agrega cada secret en GitHub → repo → **Settings → Secrets and variables → Actions**.

| Secret | Para qué | Cómo conseguirlo |
|---|---|---|
| `ELEVENLABS_API_KEY` | voz IA viral (Adam) | elevenlabs.io → Profile → API Keys. Con 3 videos por noche necesitas más o menos 45k caracteres al mes (plan Creator) |
| `ANTHROPIC_API_KEY` | escribir guiones nuevos de forma automática | console.anthropic.com |
| `YT_CLIENT_ID`, `YT_CLIENT_SECRET`, `YT_REFRESH_TOKEN` | subir a YouTube | ejecuta `python src/get_youtube_token.py`; los pasos están dentro del archivo |
| `YT_API_KEY` *(opcional)* | leer tendencias de YouTube | Google Cloud → Credenciales → Clave de API |
| `IG_USER_ID`, `IG_ACCESS_TOKEN` | publicar Reels | cuenta Instagram **Profesional** vinculada a una página de Facebook, más una app de Meta con permiso `instagram_content_publish`; usa un token de larga duración (60 días) |
| `TIKTOK_CLIENT_KEY`, `TIKTOK_CLIENT_SECRET`, `TIKTOK_REFRESH_TOKEN` | TikTok | developers.tiktok.com → app con *Content Posting API* (scope `video.upload`) |

### Límites de las plataformas (importante)

- **YouTube**: los proyectos de API sin verificar suben los videos como **privados**. Pide la auditoría de la API en Google Cloud; mientras tanto, los videos quedan privados y puedes hacerlos públicos desde YouTube Studio.
- **TikTok**: el modo `inbox` (predeterminado) manda el video a tus borradores, pero la API no permite ponerle texto. El texto con hashtags listo para copiar queda en el resumen de cada corrida en GitHub Actions. Por la mañana le agregas el **sonido en tendencia** y tocas Publicar. La API no permite poner sonidos de la biblioteca de TikTok. El modo `direct` publica solo, pero hasta que TikTok audite tu app los videos quedan visibles solo para ti.
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
