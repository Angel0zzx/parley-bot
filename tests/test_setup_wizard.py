"""
Unit tests for setup wizard functionality.
"""

import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path
from parley.utils.setup_wizard import run_setup_wizard


@patch("parley.utils.setup_wizard.webbrowser.open", return_value=True)
@patch("parley.utils.setup_wizard.requests.get")
@patch("builtins.input", side_effect=[
    "s",            # configurar fd
    "fake_fd_key",  # api key fd
    "n",            # configurar bzzoiro
    "s",            # configurar telegram
    "fake_tg_token",# token telegram
    "",             # enter tras /start
    "1"             # opcion timezone (Guayaquil)
])
def test_run_setup_wizard(mock_input, mock_requests_get, mock_webbrowser, tmp_path):
    env_file = tmp_path / ".env"

    mock_resp = MagicMock()
    mock_resp.ok = True
    mock_resp.json.return_value = {
        "result": [
            {
                "message": {
                    "chat": {"id": 12345678}
                }
            }
        ]
    }
    mock_requests_get.return_value = mock_resp

    run_setup_wizard(env_file)

    assert env_file.exists()
    content = env_file.read_text(encoding="utf-8")
    assert "FOOTBALL_DATA_KEY=fake_fd_key" in content
    assert "TELEGRAM_BOT_TOKEN=fake_tg_token" in content
    assert "TELEGRAM_CHAT_ID=12345678" in content
    assert "TZ_LOCAL=America/Guayaquil" in content
