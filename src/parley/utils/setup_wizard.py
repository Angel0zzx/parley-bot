"""
Interactive Zero-Config Setup Wizard for Parley Bot.
"""

import os
import time
import webbrowser
import requests
from pathlib import Path
from dotenv import load_dotenv


def run_setup_wizard(env_path: Path) -> None:
    """Run interactive setup wizard to configure .env credentials step by step."""
    print("\n==============================================================")
    print("      ¡BIENVENIDO AL ASISTENTE DE CONFIGURACIÓN DE PARLEY-BOT!  ")
    print("==============================================================")
    print("Este asistente te guiará en 3 sencillos pasos para configurar")
    print("tus credenciales y dejar el bot listo para funcionar.\n")

    # Paso 1: Datos de fútbol
    print("--- PASO 1/3: Proveedores de Datos de Fútbol ---")
    configure_fd = input("¿Deseas configurar Football-Data.org (Recomendado, Plan Gratuito)? [S/n]: ").strip().lower()
    fd_key = ""
    if configure_fd != "n":
        print("Abriendo sitio de registro de Football-Data.org...")
        try:
            webbrowser.open("https://www.football-data.org/client/register")
        except Exception:
            pass
        print("🔗 Enlace: https://www.football-data.org/client/register")
        fd_key = input("Pega tu API Key de Football-Data.org (o presiona Enter para omitir): ").strip()

    configure_bzzoiro = input("\n¿Deseas configurar Bzzoiro Sports Data (Opcional, Sudamérica/Argentina)? [s/N]: ").strip().lower()
    bzz_key = ""
    if configure_bzzoiro == "s":
        print("Abriendo sitio de Bzzoiro Sports Data...")
        try:
            webbrowser.open("https://sports.bzzoiro.com/")
        except Exception:
            pass
        print("🔗 Enlace: https://sports.bzzoiro.com/")
        bzz_key = input("Pega tu API Key de Bzzoiro (o presiona Enter para omitir): ").strip()

    # Paso 2: Telegram
    print("\n--- PASO 2/3: Notificaciones de Telegram (Opcional) ---")
    configure_telegram = input("¿Deseas recibir los parleys por Telegram? [S/n]: ").strip().lower()
    tg_token = ""
    tg_chat_id = ""
    if configure_telegram != "n":
        print("1. Abre Telegram y busca a @BotFather (https://t.me/BotFather) para crear tu bot (/newbot).")
        try:
            webbrowser.open("https://t.me/BotFather")
        except Exception:
            pass
        tg_token = input("Pega el TELEGRAM_BOT_TOKEN proporcionado por BotFather: ").strip()

        if tg_token:
            print("\n2. Ahora abre tu nuevo bot en Telegram, envíale el mensaje /start")
            input("Una vez enviado /start a tu bot, presiona Enter aquí para detectar tu Chat ID automáticamente...")

            print("Consultando actualizaciones de Telegram para obtener el Chat ID...")
            chat_id_detected = ""
            for _ in range(3):
                try:
                    r = requests.get(f"https://api.telegram.org/bot{tg_token}/getUpdates", timeout=10)
                    if r.ok:
                        data = r.json()
                        results = data.get("result", [])
                        if results:
                            # Buscar en mensajes o my_chat_member
                            for update in reversed(results):
                                message = update.get("message") or update.get("edited_message") or update.get("channel_post")
                                if message and "chat" in message:
                                    chat_id_detected = str(message["chat"]["id"])
                                    break
                                my_chat = update.get("my_chat_member")
                                if my_chat and "chat" in my_chat:
                                    chat_id_detected = str(my_chat["chat"]["id"])
                                    break
                        if chat_id_detected:
                            break
                except Exception:
                    pass
                time.sleep(2)

            if chat_id_detected:
                print(f"✅ ¡Chat ID detectado con éxito: {chat_id_detected}!")
                tg_chat_id = chat_id_detected
            else:
                print("⚠️ No se pudo detectar automáticamente el Chat ID (asegúrate de haberle escrito /start al bot).")
                tg_chat_id = input("Ingresa tu TELEGRAM_CHAT_ID manualmente: ").strip()

    # Paso 3: Zona horaria
    print("\n--- PASO 3/3: Zona Horaria ---")
    print("Zonas horarias comunes:")
    print("  [1] America/Guayaquil (Ecuador)")
    print("  [2] America/Bogota (Colombia)")
    print("  [3] America/Lima (Perú)")
    print("  [4] America/Argentina/Buenos_Aires")
    tz_choice = input("Elige una opción [1-4] o escribe tu zona horaria (por defecto America/Guayaquil): ").strip()
    tz_map = {
        "1": "America/Guayaquil",
        "2": "America/Bogota",
        "3": "America/Lima",
        "4": "America/Argentina/Buenos_Aires",
    }
    tz_local = tz_map.get(tz_choice, tz_choice if tz_choice else "America/Guayaquil")

    # Guardar en .env
    env_content = (
        f"FOOTBALL_DATA_KEY={fd_key}\n"
        f"BZZOIRO_API_KEY={bzz_key}\n"
        f"TELEGRAM_BOT_TOKEN={tg_token}\n"
        f"TELEGRAM_CHAT_ID={tg_chat_id}\n"
        f"TZ_LOCAL={tz_local}\n"
    )
    try:
        env_path.write_text(env_content, encoding="utf-8")
        print(f"\n✅ ¡Configuración guardada exitosamente en {env_path}!")
    except Exception as e:
        print(f"\n❌ Error al guardar el archivo .env: {e}")

    load_dotenv(env_path, override=True)
    print("==============================================================\n")
