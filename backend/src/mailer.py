"""Envío del reporte ejecutivo por email vía Resend (https://resend.com).

Se eligió Resend en lugar de SMTP para que el caso no dependa de configurar un
servidor de correo: una API key gratuita (3k emails/mes) y el remitente de
pruebas onboarding@resend.dev funcionan sin verificar dominio. Si no hay
RESEND_API_KEY, el endpoint degrada con un mensaje claro (no rompe).

Para cambiar a SMTP en producción, basta reemplazar send_report_email().
"""
from __future__ import annotations

import os
import re
from pathlib import Path

import httpx
import markdown as md
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
RESEND_ENDPOINT = "https://api.resend.com/emails"

# Plantilla HTML del email — estilos inline-friendly para clientes de correo.
_TEMPLATE = """\
<!doctype html><html><head><meta charset="utf-8"></head>
<body style="margin:0;background:#f4f4f5;font-family:-apple-system,Segoe UI,Roboto,Helvetica,Arial,sans-serif;color:#18181b">
  <div style="max-width:680px;margin:0 auto;padding:24px">
    <div style="background:#0f0f10;border-radius:14px;padding:18px 22px;margin-bottom:16px">
      <span style="display:inline-block;width:30px;height:30px;line-height:30px;text-align:center;
        background:#ff441f;color:#fff;font-weight:800;border-radius:8px;vertical-align:middle">R</span>
      <span style="color:#fafafa;font-weight:600;margin-left:8px;font-size:16px;vertical-align:middle">SAIOR</span>
      <span style="color:#a1a1aa;font-size:12px;margin-left:6px">· Insights de Operaciones Rappi</span>
    </div>
    <div style="background:#fff;border:1px solid #e4e4e7;border-radius:14px;padding:8px 26px 26px">
      {body}
    </div>
    <p style="color:#a1a1aa;font-size:11px;text-align:center;margin-top:18px">
      Generado automáticamente por SAIOR · detección estadística determinista, sin LLM en el cálculo
    </p>
  </div>
</body></html>"""

# CSS aplicado al cuerpo convertido desde Markdown.
_BODY_CSS = """
<style>
  h1{font-size:20px;margin:18px 0 4px} h2{font-size:16px;margin:18px 0 6px;color:#27272a}
  h3{font-size:14px;margin:14px 0 4px;color:#3f3f46} p,li{font-size:13px;line-height:1.6;color:#3f3f46}
  table{border-collapse:collapse;width:100%;margin:8px 0;font-size:12px}
  th,td{border:1px solid #e4e4e7;padding:5px 8px;text-align:left} th{background:#fafafa}
  code{background:#f4f4f5;border-radius:4px;padding:1px 4px;font-size:12px}
  strong{color:#18181b} em{color:#52525b} hr{border:0;border-top:1px solid #e4e4e7;margin:14px 0}
  a{color:#ff441f}
</style>
"""


def is_valid_email(addr: str) -> bool:
    return bool(EMAIL_RE.match((addr or "").strip()))


def render_html(markdown_text: str) -> str:
    body = md.markdown(markdown_text, extensions=["tables", "sane_lists"])
    return _TEMPLATE.format(body=_BODY_CSS + body)


def send_report_email(to: str, subject: str, markdown_text: str) -> dict:
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        return {"available": False, "sent": False,
                "message": "Email no configurado: agrega RESEND_API_KEY en backend/.env "
                           "(clave gratuita en https://resend.com)."}
    if not is_valid_email(to):
        return {"available": True, "sent": False, "message": "Dirección de email inválida."}

    sender = os.environ.get("RESEND_FROM", "SAIOR <onboarding@resend.dev>")
    try:
        r = httpx.post(
            RESEND_ENDPOINT,
            headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
            json={"from": sender, "to": [to], "subject": subject, "html": render_html(markdown_text)},
            timeout=20,
        )
    except httpx.HTTPError as e:
        return {"available": True, "sent": False, "message": f"No se pudo contactar a Resend: {e}"}

    if r.status_code in (200, 201):
        return {"available": True, "sent": True, "id": r.json().get("id"), "to": to}
    return {"available": True, "sent": False,
            "message": f"Resend respondió {r.status_code}: {r.text[:160]}"}
