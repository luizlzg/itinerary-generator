"""
Email client for sending itinerary documents.

This module provides a simple SMTP-based email client for sending
the generated itinerary documents to users.

Configuration via environment variables:
- SMTP_HOST: SMTP server host (e.g., smtp.gmail.com, smtp-mail.outlook.com)
- SMTP_PORT: SMTP server port (default: 587)
- SMTP_USER: SMTP username/email
- SMTP_PASS: SMTP password or app password
- SMTP_FROM: Sender email address (defaults to SMTP_USER)

Supported providers (any SMTP server works):
- Gmail: smtp.gmail.com:587 (requires App Password)
- Outlook/Hotmail: smtp-mail.outlook.com:587
- Yahoo: smtp.mail.yahoo.com:587
- Others: Use your provider's SMTP settings
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from pathlib import Path
from typing import Dict, Any, List, Union
from src.utils.logger import LOGGER


def check_email_config() -> Dict[str, Any]:
    """
    Check if email configuration is valid.

    Returns:
        Dictionary with configuration status and details
    """
    smtp_host = os.getenv("SMTP_HOST")
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")

    missing = []
    if not smtp_host:
        missing.append("SMTP_HOST")
    if not smtp_user:
        missing.append("SMTP_USER")
    if not smtp_pass:
        missing.append("SMTP_PASS")

    if missing:
        return {
            "configured": False,
            "missing": missing,
            "message": f"Missing environment variables: {', '.join(missing)}",
            "help": """
To configure email sending, add these to your .env file:

# For Gmail (requires App Password):
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=your-email@gmail.com
SMTP_PASS=your-app-password

# For Outlook/Hotmail:
SMTP_HOST=smtp-mail.outlook.com
SMTP_PORT=587
SMTP_USER=your-email@outlook.com
SMTP_PASS=your-password

# For Yahoo:
SMTP_HOST=smtp.mail.yahoo.com
SMTP_PORT=587
SMTP_USER=your-email@yahoo.com
SMTP_PASS=your-app-password

For Gmail, create an App Password at:
https://myaccount.google.com/apppasswords
(Requires 2FA enabled)
            """.strip()
        }

    return {
        "configured": True
    }


def send_itinerary_email_sync(
    document_path: str,
    to_emails: List[str],
    destination: str,
    num_days: int,
    language: str = "en",
) -> Dict[str, Any]:
    """
    Send an itinerary document via email to one or more recipients.

    Args:
        document_path: Path to the itinerary document (DOCX)
        to_emails: Recipient email address(es) - list of strings
        destination: Trip destination name
        num_days: Number of days in the itinerary
        language: Language for email content (en, pt-br, es, fr)

    Returns:
        Result dictionary with success status
    """
    if not to_emails:
        return {
            "success": False,
            "error": "No valid email addresses provided",
        }
    
    # Check configuration
    config = check_email_config()
    if not config["configured"]:
        return {
            "success": False,
            "error": config["message"],
            "help": config.get("help", ""),
        }

    # Verify document exists
    doc_path = Path(document_path)
    if not doc_path.exists():
        return {
            "success": False,
            "error": f"Document not found: {document_path}",
        }

    # Get SMTP settings
    smtp_host = os.getenv("SMTP_HOST")
    smtp_port = int(os.getenv("SMTP_PORT", "587"))
    smtp_user = os.getenv("SMTP_USER")
    smtp_pass = os.getenv("SMTP_PASS")
    smtp_from = os.getenv("SMTP_FROM", smtp_user)

    # Email templates by language
    templates = {
        "en": {
            "subject": f"Your {num_days}-Day {destination} Travel Itinerary",
            "body": f"""Hello!

Your personalized {num_days}-day travel itinerary for {destination} is ready!

Please find the document attached to this email. It includes:
- Day-by-day attractions and activities
- Useful information and tips
- Estimated costs
- A map with all locations

Have a wonderful trip!

Best regards,
Itinerary Generator
""",
        },
        "pt-br": {
            "subject": f"Seu Roteiro de {num_days} Dias em {destination}",
            "body": f"""Olá!

Seu roteiro personalizado de {num_days} dias para {destination} está pronto!

Você encontrará o documento em anexo neste e-mail. Ele inclui:
- Atrações e atividades dia a dia
- Informações úteis e dicas
- Custos estimados
- Um mapa com todas as localizações

Tenha uma ótima viagem!

Atenciosamente,
Gerador de Roteiros
""",
        },
        "es": {
            "subject": f"Tu Itinerario de {num_days} Días en {destination}",
            "body": f"""¡Hola!

¡Tu itinerario personalizado de {num_days} días para {destination} está listo!

Encontrarás el documento adjunto en este correo. Incluye:
- Atracciones y actividades día a día
- Información útil y consejos
- Costos estimados
- Un mapa con todas las ubicaciones

¡Que tengas un excelente viaje!

Saludos,
Generador de Itinerarios
""",
        },
        "fr": {
            "subject": f"Votre Itinéraire de {num_days} Jours à {destination}",
            "body": f"""Bonjour!

Votre itinéraire personnalisé de {num_days} jours pour {destination} est prêt!

Vous trouverez le document en pièce jointe. Il comprend:
- Attractions et activités jour par jour
- Informations utiles et conseils
- Coûts estimés
- Une carte avec tous les emplacements

Bon voyage!

Cordialement,
Générateur d'Itinéraires
""",
        },
    }

    template = templates.get(language.lower(), templates["en"])

    try:
        # Create message
        msg = MIMEMultipart()
        msg["Subject"] = template["subject"]
        msg["From"] = smtp_from
        msg["To"] = ", ".join(to_emails)

        # Add body
        msg.attach(MIMEText(template["body"], "plain", "utf-8"))

        # Add attachment - use proper MIME type for DOCX
        with open(doc_path, "rb") as f:
            part = MIMEBase(
                "application",
                "vnd.openxmlformats-officedocument.wordprocessingml.document"
            )
            part.set_payload(f.read())

        encoders.encode_base64(part)
        filename = doc_path.name
        part.add_header(
            "Content-Disposition",
            "attachment",
            filename=filename
        )
        part.add_header(
            "Content-Type",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            name=filename
        )
        msg.attach(part)

        # Send email
        LOGGER.info(f"Connecting to {smtp_host}:{smtp_port}")

        with smtplib.SMTP(smtp_host, smtp_port) as server:
            server.ehlo()
            server.starttls()
            server.ehlo()
            server.login(smtp_user, smtp_pass)
            server.sendmail(smtp_from, to_emails, msg.as_string())

        recipients_str = ", ".join(to_emails)
        LOGGER.info(f"Email sent successfully to {recipients_str}")
        return {
            "success": True,
            "message": f"Email sent to {recipients_str}",
            "recipients": to_emails,
        }

    except smtplib.SMTPAuthenticationError as e:
        LOGGER.error(f"SMTP authentication failed: {e}")
        return {
            "success": False,
            "error": "Authentication failed. Check your email/password. For Gmail, use an App Password.",
        }

    except smtplib.SMTPException as e:
        LOGGER.error(f"SMTP error: {e}")
        return {
            "success": False,
            "error": f"SMTP error: {str(e)}",
        }

    except Exception as e:
        LOGGER.error(f"Error sending email: {e}")
        return {
            "success": False,
            "error": str(e),
        }
