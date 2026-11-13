from pathlib import Path

import pytest

from omarchy_manager.services import caminhos


def test_recusa_usr_share_omarchy():
    with pytest.raises(caminhos.CaminhoProibido):
        caminhos.garantir_gravavel(Path("/usr/share/omarchy/themes/x/colors.toml"))


def test_recusa_omarchy_path_do_ambiente(monkeypatch, tmp_path):
    monkeypatch.setenv("OMARCHY_PATH", str(tmp_path / "omarchy"))
    (tmp_path / "omarchy").mkdir()
    with pytest.raises(caminhos.CaminhoProibido):
        caminhos.garantir_gravavel(tmp_path / "omarchy" / "x")


def test_aceita_config_do_usuario(tmp_path):
    assert caminhos.garantir_gravavel(tmp_path / "a.lua") == (tmp_path / "a.lua").resolve()
